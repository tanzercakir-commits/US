"""Runtime guard generation for the final enforcement-ladder rung."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .enforcement_ladder import (
    PropertySkeletonBundle,
    _SCALAR_CPP_TYPES,
    _canonical_json,
    _contract_expression,
    _sha256_bytes,
    _sha256_json,
    build_property_skeleton,
)
from .model import FunctionIR, VerificationReport


RUNTIME_SCHEMA = "codeskeptic.runtime-assertions/v1"
RUNTIME_SOURCE_SCHEMA = "codeskeptic.runtime-wrapper/v1"
DEMO_SCHEMA = "codeskeptic.enforcement-ladder-demo/v1"


@dataclass(frozen=True, slots=True)
class RuntimeAssertionsBundle:
    property: PropertySkeletonBundle
    wrapper: str
    manifest: Mapping[str, Any]
    demo_manifest: Mapping[str, Any]

    def manifest_json(self) -> str:
        return _canonical_json(self.manifest)

    def demo_manifest_json(self) -> str:
        return _canonical_json(self.demo_manifest)


def _cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _function_declaration(function: FunctionIR) -> tuple[str, str, str]:
    return_type = _SCALAR_CPP_TYPES[function.return_type]
    parameters = [
        (
            _SCALAR_CPP_TYPES[parameter.type],
            parameter.source_name or parameter.name,
        )
        for parameter in function.parameters
    ]
    declaration = ", ".join(
        f"{type_name} {name}" for type_name, name in parameters
    )
    arguments = ", ".join(name for _, name in parameters)
    return return_type, declaration, arguments


def _failure_lines(
    target_id: str,
    kind: str,
    expression: str,
) -> list[str]:
    return [
        f"    if (!({expression})) {{",
        "        codeskeptic_contract_failure(",
        f"            {_cpp_string(target_id)},",
        f"            {_cpp_string(kind)},",
        f"            {_cpp_string(expression)}",
        "        );",
        "    }",
    ]


def _render_runtime_target(
    function: FunctionIR,
    target: Mapping[str, Any],
) -> tuple[str, str]:
    return_type, declaration, arguments = _function_declaration(function)
    symbol = str(target["symbol"])
    wrapper_name = f"codeskeptic_checked_{symbol}"
    target_id = str(target["target_id"])
    lines = [
        f"// target: {target_id}",
        f"{return_type} {function.name}({declaration});",
        "",
        f"{return_type} {wrapper_name}({declaration}) {{",
    ]
    for contract in function.contracts:
        if contract.kind == "requires":
            lines.extend(
                _failure_lines(
                    target_id,
                    "requires",
                    _contract_expression(contract),
                )
            )
    lines.append(
        f"    const {return_type} result = {function.name}({arguments});"
    )
    for contract in function.contracts:
        if contract.kind == "ensures":
            lines.extend(
                _failure_lines(
                    target_id,
                    "ensures",
                    _contract_expression(contract),
                )
            )
    lines.extend(["    return result;", "}", ""])
    return "\n".join(lines), wrapper_name


def _render_wrapper(
    functions: Mapping[str, FunctionIR],
    targets: list[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        f"// {RUNTIME_SOURCE_SCHEMA}",
        "// Generated deterministically; state: runtime_guarded, not verified.",
        "[[noreturn]] void codeskeptic_contract_failure(",
        "    const char* target_id,",
        "    const char* kind,",
        "    const char* expression",
        ");",
        "",
    ]
    runtime_targets: list[dict[str, Any]] = []
    for target in sorted(targets, key=lambda item: (item["function"], item["target_id"])):
        function = functions[str(target["function"])]
        rendered, wrapper_name = _render_runtime_target(function, target)
        lines.append(rendered.rstrip())
        lines.append("")
        runtime_targets.append(
            {
                "contract_set_sha256": target["contract_set_sha256"],
                "function": target["function"],
                "property_state": target["state"],
                "state": "runtime_guarded",
                "target_id": target["target_id"],
                "wrapper": wrapper_name,
            }
        )
    return "\n".join(lines).rstrip() + "\n", runtime_targets


def build_runtime_assertions(
    source: str,
    report: VerificationReport,
    *,
    display_path: str | None = None,
) -> RuntimeAssertionsBundle:
    """Generate exact runtime wrappers and a combined three-rung manifest."""

    property_bundle = build_property_skeleton(
        source,
        report,
        display_path=display_path,
    )
    functions: dict[str, FunctionIR] = {}
    for function in report.module.functions:
        if function.name in functions:
            continue
        functions[function.name] = function
    targets = list(property_bundle.manifest["property_targets"])
    if any(str(target["function"]) not in functions for target in targets):
        raise ValueError("property target has no unique runtime function")
    wrapper, runtime_targets = _render_wrapper(functions, targets)
    routes: list[dict[str, Any]] = []
    target_ids = {str(target["target_id"]) for target in targets}
    for property_route in property_bundle.manifest["routes"]:
        route = dict(property_route)
        target_id = route.get("target_id")
        if target_id in target_ids:
            route["runtime_fallback"] = "runtime_guard"
            route["runtime_state"] = "runtime_guarded"
        else:
            route["runtime_fallback"] = "none"
            route["runtime_state"] = route["state"]
        routes.append(route)

    wrapper_sha256 = _sha256_bytes(wrapper.encode("utf-8"))
    manifest: dict[str, Any] = {
        "property_skeleton_sha256": property_bundle.manifest["skeleton_sha256"],
        "property_workflow_id": property_bundle.manifest["workflow_id"],
        "report_sha256": property_bundle.manifest["report_sha256"],
        "routes": routes,
        "runtime_targets": runtime_targets,
        "schema": RUNTIME_SCHEMA,
        "source_sha256": property_bundle.manifest["source_sha256"],
        "state": "runtime_guarded" if runtime_targets else "no_runtime_target",
        "wrapper_schema": RUNTIME_SOURCE_SCHEMA,
        "wrapper_sha256": wrapper_sha256,
    }
    manifest["workflow_id"] = _sha256_json(manifest)

    demo_manifest: dict[str, Any] = {
        "contract_targets": [
            {
                "contract_set_sha256": target["contract_set_sha256"],
                "function": target["function"],
                "target_id": target["target_id"],
            }
            for target in runtime_targets
        ],
        "routes": routes,
        "rungs": {
            "property": {
                "skeleton_sha256": property_bundle.manifest["skeleton_sha256"],
                "state": property_bundle.manifest["state"],
                "workflow_id": property_bundle.manifest["workflow_id"],
            },
            "runtime": {
                "state": manifest["state"],
                "workflow_id": manifest["workflow_id"],
                "wrapper_sha256": wrapper_sha256,
            },
            "static": {
                "report_sha256": property_bundle.manifest["report_sha256"],
                "state": "referee_complete",
                "summary": report.summary(),
            },
        },
        "schema": DEMO_SCHEMA,
        "source_sha256": property_bundle.manifest["source_sha256"],
    }
    demo_manifest["workflow_id"] = _sha256_json(demo_manifest)
    return RuntimeAssertionsBundle(
        property=property_bundle,
        wrapper=wrapper,
        manifest=manifest,
        demo_manifest=demo_manifest,
    )