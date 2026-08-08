"""Deterministic enforcement-ladder routing and property skeleton generation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .cpp26_contracts import normalize_result_binding
from .model import (
    Contract,
    FunctionIR,
    VerificationReport,
    VerificationStatus,
)


MANIFEST_SCHEMA = "codeskeptic.enforcement-ladder/v1"
SKELETON_SCHEMA = "codeskeptic.property-skeleton/v1"
_SCALAR_CPP_TYPES = {
    "bool": "bool",
    "i32": "int",
    "u32": "unsigned int",
    "i64": "long long",
    "u64": "unsigned long long",
}


class EnforcementLadderInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PropertySkeletonBundle:
    skeleton: str
    manifest: Mapping[str, Any]

    def manifest_json(self) -> str:
        return _canonical_json(self.manifest)


@dataclass(frozen=True, slots=True)
class _Target:
    function: FunctionIR
    target_id: str
    contract_set_sha256: str
    contributing_obligations: tuple[str, ...]
    statuses: tuple[str, ...]
    symbol: str


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _logical_report(
    report: VerificationReport, display_path: str
) -> Mapping[str, Any]:
    variants = {
        display_path,
        display_path.replace("\\", "/"),
        display_path.replace("/", "\\"),
        report.module.source,
        report.module.source.replace("\\", "/"),
        report.module.source.replace("/", "\\"),
    }

    def normalize(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                item_key: normalize(item_value, item_key)
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str):
            if key in {"file", "source"}:
                return "<source>"
            result = value
            for variant in sorted(variants, key=len, reverse=True):
                if variant:
                    result = result.replace(variant, "<source>")
            return result
        return value

    return normalize(report.to_dict())


def _validate_report(report: VerificationReport) -> None:
    obligation_by_id = {item.id: item for item in report.obligations}
    if len(obligation_by_id) != len(report.obligations):
        raise EnforcementLadderInputError("report has duplicate obligation ids")
    result_ids = [item.obligation_id for item in report.results]
    if len(set(result_ids)) != len(result_ids):
        raise EnforcementLadderInputError("report has duplicate result ids")
    if set(result_ids) != set(obligation_by_id):
        raise EnforcementLadderInputError(
            "report results do not cover every obligation exactly once"
        )
    for result in report.results:
        obligation = obligation_by_id[result.obligation_id]
        if result.function != obligation.function or result.kind != obligation.kind:
            raise EnforcementLadderInputError(
                f"result {result.obligation_id} does not match its obligation"
            )
        if (
            result.status == VerificationStatus.VIOLATED
            and result.counterexample is None
        ):
            raise EnforcementLadderInputError(
                f"violated result {result.obligation_id} lacks replay evidence"
            )


def _contract_payload(function: FunctionIR) -> Mapping[str, Any]:
    return {
        "contracts": [
            {
                "kind": contract.kind,
                "machine_proposed": contract.machine_proposed,
                "text": contract.text,
            }
            for contract in function.contracts
        ],
        "function": function.name,
        "parameters": [
            {
                "name": parameter.source_name or parameter.name,
                "passing": parameter.passing,
                "type": parameter.type,
            }
            for parameter in function.parameters
        ],
        "return_type": function.return_type,
    }


def _accepted_cs_contracts_are_current(
    source: str, function: FunctionIR
) -> bool:
    lines = source.splitlines()
    for contract in function.contracts:
        if contract.machine_proposed:
            return False
        index = contract.location.line - 1
        if index < 0 or index >= len(lines):
            return False
        pattern = (
            r"^[ \t]*//[ \t]*cs:[ \t]*"
            + re.escape(contract.text)
            + r"[ \t]*$"
        )
        line = lines[index].removeprefix("\ufeff") if index == 0 else lines[index]
        if re.fullmatch(pattern, line) is None:
            return False
    return True


def _eligibility_reason(source: str, function: FunctionIR) -> str | None:
    if function.return_type not in _SCALAR_CPP_TYPES:
        return "return type is outside the fixed scalar property subset"
    if not function.has_body:
        return "function has no owned definition"
    if function.frame is not None:
        return "frame contracts require manual enforcement"
    if any(
        parameter.passing != "value"
        or parameter.type not in _SCALAR_CPP_TYPES
        for parameter in function.parameters
    ):
        return "parameters are outside the fixed scalar by-value subset"
    if not any(contract.kind == "ensures" for contract in function.contracts):
        return "function has no postcondition"
    if any(
        contract.kind not in {"requires", "ensures"}
        for contract in function.contracts
    ):
        return "contract kind is outside the property subset"
    if not _accepted_cs_contracts_are_current(source, function):
        return "accepted cs: contract set is absent, proposed, or stale"
    return None


def _contract_expression(contract: Contract) -> str:
    prefix = contract.kind + " "
    if not contract.text.startswith(prefix):
        raise EnforcementLadderInputError(
            f"malformed canonical contract text: {contract.text!r}"
        )
    expression = contract.text[len(prefix):]
    if contract.kind == "ensures":
        expression = normalize_result_binding(expression, "return")
    return expression


def _safe_symbol(name: str, target_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not stem or stem[0].isdigit():
        stem = "_" + stem
    return f"{stem}_{target_id.removeprefix('sha256:')[:12]}"


def _render_target(target: _Target) -> str:
    function = target.function
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
    argument_names = ", ".join(name for _, name in parameters)
    case_name = f"codeskeptic_{target.symbol}_case"
    property_name = f"codeskeptic_property_{target.symbol}"
    lines = [
        f"// target: {target.target_id}",
        "// original referee statuses: " + ", ".join(target.statuses),
        f"{return_type} {function.name}({declaration});",
        "",
        f"struct {case_name} {{",
    ]
    lines.extend(f"    {type_name} {name};" for type_name, name in parameters)
    lines.extend(
        [
            "};",
            "",
            "template <std::size_t N>",
            f"void {property_name}(",
            f"    const {case_name} (&cases)[N]",
            ") {",
            "    for (const auto& test_case : cases) {",
        ]
    )
    lines.extend(
        f"        const {type_name} {name} = test_case.{name};"
        for type_name, name in parameters
    )
    requires = [
        _contract_expression(contract)
        for contract in function.contracts
        if contract.kind == "requires"
    ]
    if requires:
        condition = " && ".join(f"({item})" for item in requires)
        lines.extend(
            [
                f"        if (!({condition})) {{",
                "            continue;",
                "        }",
            ]
        )
    lines.append(
        f"        const {return_type} result = "
        f"{function.name}({argument_names});"
    )
    lines.extend(
        f"        assert(({_contract_expression(contract)}));"
        for contract in function.contracts
        if contract.kind == "ensures"
    )
    lines.extend(["    }", "}", ""])
    return "\n".join(lines)


def _render_skeleton(targets: tuple[_Target, ...]) -> str:
    lines = [
        f"// {SKELETON_SCHEMA}",
        "// Generated deterministically; state: property_generated_unexecuted.",
        "// Caller supplies cases. Passing finite cases is not static proof.",
        "#include <cassert>",
        "#include <cstddef>",
        "",
    ]
    for target in targets:
        lines.append(_render_target(target).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_property_skeleton(
    source: str,
    report: VerificationReport,
    *,
    display_path: str | None = None,
) -> PropertySkeletonBundle:
    """Route a fresh report and generate exact eligible property skeletons."""

    _validate_report(report)
    shown = (display_path or report.module.source).replace("\\", "/")
    if report.module.source.replace("\\", "/") != shown:
        raise EnforcementLadderInputError(
            "report source does not match the supplied display path"
        )

    functions_by_name: dict[str, list[FunctionIR]] = {}
    for function in report.module.functions:
        functions_by_name.setdefault(function.name, []).append(function)
    results_by_function: dict[str, list[Any]] = {}
    for result in report.results:
        results_by_function.setdefault(result.function, []).append(result)

    targets: list[_Target] = []
    target_by_function: dict[str, _Target] = {}
    manual_reasons: dict[str, str] = {}
    for function_name, results in sorted(results_by_function.items()):
        unproven = [
            result
            for result in results
            if result.status in {
                VerificationStatus.UNKNOWN,
                VerificationStatus.UNSUPPORTED,
            }
        ]
        if not unproven:
            continue
        blocking = [
            result
            for result in results
            if result.status in {
                VerificationStatus.VIOLATED,
                VerificationStatus.SOLVER_ERROR,
            }
        ]
        functions = functions_by_name.get(function_name, [])
        reason: str | None = None
        if blocking:
            reason = "function has a defect or infrastructure failure"
        elif len(functions) != 1:
            reason = "function identity is absent or overloaded"
        else:
            reason = _eligibility_reason(source, functions[0])
        if reason is not None:
            manual_reasons[function_name] = reason
            continue
        function = functions[0]
        contract_payload = _contract_payload(function)
        contract_set_sha256 = _sha256_json(contract_payload)
        target_payload = {
            "contract_set_sha256": contract_set_sha256,
            "function": function.name,
        }
        target_id = _sha256_json(target_payload)
        target = _Target(
            function=function,
            target_id=target_id,
            contract_set_sha256=contract_set_sha256,
            contributing_obligations=tuple(
                sorted(result.obligation_id for result in unproven)
            ),
            statuses=tuple(sorted({result.status.value for result in unproven})),
            symbol=_safe_symbol(function.name, target_id),
        )
        targets.append(target)
        target_by_function[function_name] = target

    targets.sort(key=lambda item: (item.function.name, item.target_id))
    target_tuple = tuple(targets)
    skeleton = _render_skeleton(target_tuple)
    routes: list[dict[str, Any]] = []
    for result in sorted(
        report.results,
        key=lambda item: (
            item.function,
            item.kind,
            item.obligation_id,
        ),
    ):
        route: dict[str, Any] = {
            "function": result.function,
            "kind": result.kind,
            "line": result.location.line,
            "message": result.message,
            "obligation": result.obligation_id,
            "original_status": result.status.value,
        }
        if result.status == VerificationStatus.VERIFIED:
            route.update({"fallback": "none", "state": "static_verified"})
        elif result.status == VerificationStatus.VIOLATED:
            route.update({"fallback": "none", "state": "defect_replayed"})
        elif result.status == VerificationStatus.SOLVER_ERROR:
            route.update({"fallback": "none", "state": "infrastructure_error"})
        elif result.function in target_by_function:
            route.update(
                {
                    "fallback": "property_test",
                    "state": "property_generated_unexecuted",
                    "target_id": target_by_function[result.function].target_id,
                }
            )
        else:
            route.update(
                {
                    "fallback": "manual_required",
                    "routing_reason": manual_reasons.get(
                        result.function,
                        "no exact callable contract surface",
                    ),
                    "state": "manual_required",
                }
            )
        routes.append(route)

    target_payloads = [
        {
            "contract_set_sha256": target.contract_set_sha256,
            "contributing_obligations": list(target.contributing_obligations),
            "function": target.function.name,
            "original_statuses": list(target.statuses),
            "state": "property_generated_unexecuted",
            "symbol": target.symbol,
            "target_id": target.target_id,
        }
        for target in target_tuple
    ]
    source_sha256 = _sha256_bytes(source.encode("utf-8"))
    report_sha256 = _sha256_json(_logical_report(report, shown))
    skeleton_sha256 = _sha256_bytes(skeleton.encode("utf-8"))
    manifest: dict[str, Any] = {
        "property_targets": target_payloads,
        "report_sha256": report_sha256,
        "routes": routes,
        "schema": MANIFEST_SCHEMA,
        "skeleton_schema": SKELETON_SCHEMA,
        "skeleton_sha256": skeleton_sha256,
        "source_sha256": source_sha256,
        "state": (
            "property_generated_unexecuted"
            if target_payloads
            else "no_property_target"
        ),
    }
    manifest["workflow_id"] = _sha256_json(manifest)
    return PropertySkeletonBundle(skeleton=skeleton, manifest=manifest)