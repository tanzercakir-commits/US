#!/usr/bin/env python3
"""Deterministic evaluator for the frozen US Language Gate A pilot.

Not model-facing. Run outside the trial workspace:

    python evaluator.py --solution /path/to/trial --stage initial
    python evaluator.py --solution /path/to/trial --stage csv
    python evaluator.py --solution /path/to/trial --stage cache
"""

from __future__ import annotations

import argparse
import ast
import copy
import csv
import importlib
import io
import json
from pathlib import Path
import sys
from typing import Any


NETWORK_MODULES = {
    "socket",
    "ftplib",
    "smtplib",
    "telnetlib",
    "http.client",
    "urllib.request",
    "xmlrpc.client",
}


class StubReader:
    def __init__(self, rows: list[dict[str, Any]] | None = None, *, fail: bool = False):
        self.rows = rows if rows is not None else []
        self.fail = fail
        self.calls = 0

    def read(self, query: Any) -> list[dict[str, Any]]:
        self.calls += 1
        if self.fail:
            raise OSError("frozen trial read failure")
        return self.rows


class StubRenderer:
    def __init__(self):
        self.calls = 0
        self.last_rows: Any = None

    def render(self, rows: Any) -> str:
        self.calls += 1
        self.last_rows = copy.deepcopy(rows)
        return "RENDERED"


class StubService:
    def __init__(self):
        self.calls: list[Any] = []

    def build_report(self, query: Any) -> str:
        self.calls.append(query)
        return "UI_OK"


def _clear_candidate_modules() -> None:
    for name in list(sys.modules):
        if name == "report_builder" or name.startswith("report_builder."):
            del sys.modules[name]


def load_api(solution: Path) -> dict[str, Any]:
    _clear_candidate_modules()
    sys.path.insert(0, str(solution))
    try:
        modules = {
            "ui": importlib.import_module("report_builder.ui"),
            "service": importlib.import_module("report_builder.service"),
            "data": importlib.import_module("report_builder.data"),
            "render": importlib.import_module("report_builder.render"),
            "results": importlib.import_module("report_builder.results"),
        }
    finally:
        try:
            sys.path.remove(str(solution))
        except ValueError:
            pass

    return {
        "UI": getattr(modules["ui"], "UI"),
        "ReportService": getattr(modules["service"], "ReportService"),
        "DataReader": getattr(modules["data"], "DataReader"),
        "Renderer": getattr(modules["render"], "Renderer"),
        "ReadFailure": getattr(modules["results"], "ReadFailure"),
        "EmptyReport": getattr(modules["results"], "EmptyReport"),
    }


def static_scan(solution: Path) -> dict[str, Any]:
    package = solution / "report_builder"
    details: list[str] = []
    architecture_ok = True
    network_ok = True
    direct_datareader_dependency = False
    network_surface_detected = False

    if not package.is_dir():
        return {
            "architecture_ok": False,
            "network_ok": False,
            "direct_datareader_dependency": False,
            "network_surface_detected": False,
            "details": ["missing report_builder package"],
        }

    for path in sorted(package.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            details.append(f"{path.name}: parse/read error: {exc}")
            architecture_ok = False
            network_ok = False
            continue

        is_ui = path.name == "ui.py"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name in NETWORK_MODULES:
                        network_ok = False
                        network_surface_detected = True
                        details.append(f"{path.name}: network import {name}")
                    if is_ui and (
                        name == "report_builder.data" or name.endswith(".data")
                    ):
                        architecture_ok = False
                        direct_datareader_dependency = True
                        details.append(f"{path.name}: direct DataReader module import")

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = {alias.name for alias in node.names}
                if module in NETWORK_MODULES:
                    network_ok = False
                    network_surface_detected = True
                    details.append(f"{path.name}: network import-from {module}")
                if module == "urllib" and "request" in imported:
                    network_ok = False
                    network_surface_detected = True
                    details.append(f"{path.name}: network import urllib.request")
                if module == "http" and "client" in imported:
                    network_ok = False
                    network_surface_detected = True
                    details.append(f"{path.name}: network import http.client")
                if is_ui and (
                    module == "report_builder.data"
                    or module.endswith(".data")
                    or "DataReader" in imported
                ):
                    architecture_ok = False
                    direct_datareader_dependency = True
                    details.append(f"{path.name}: direct DataReader dependency")

            elif is_ui and isinstance(node, ast.Name) and node.id == "DataReader":
                architecture_ok = False
                direct_datareader_dependency = True
                details.append(f"{path.name}: DataReader name reference")

            elif is_ui and isinstance(node, ast.Attribute) and node.attr == "DataReader":
                architecture_ok = False
                direct_datareader_dependency = True
                details.append(f"{path.name}: DataReader attribute reference")

            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                if "http://" in lowered or "https://" in lowered:
                    network_ok = False
                    network_surface_detected = True
                    details.append(f"{path.name}: URL literal")

    return {
        "architecture_ok": architecture_ok,
        "network_ok": network_ok,
        "direct_datareader_dependency": direct_datareader_dependency,
        "network_surface_detected": network_surface_detected,
        "details": details,
    }


def api_check(api: dict[str, Any]) -> tuple[bool, list[str]]:
    try:
        service = StubService()
        ui = api["UI"](service)
        result = ui.build_report("q")
        ok = result == "UI_OK" and service.calls == ["q"]
        return (
            ok,
            [] if ok else ["UI does not delegate build_report(query) through service"],
        )
    except Exception as exc:
        return False, [f"UI/API error: {type(exc).__name__}: {exc}"]


def baseline_behavior(api: dict[str, Any]) -> dict[str, Any]:
    details: list[str] = []
    immutable_ok = True
    flow_ok = True
    failure_empty_distinct = True
    source_mutated = False
    collapse_observed = False

    rows = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]
    before = copy.deepcopy(rows)
    try:
        reader = StubReader(rows)
        renderer = StubRenderer()
        service = api["ReportService"](reader, renderer)
        result = service.build_report("q")
        if result != "RENDERED":
            flow_ok = False
            details.append("non-empty path did not return Renderer output")
        if reader.calls != 1 or renderer.calls != 1:
            flow_ok = False
            details.append("non-empty path did not perform one read and one render")
        if rows != before:
            immutable_ok = False
            source_mutated = True
            details.append("source rows mutated on non-empty path")
    except Exception as exc:
        immutable_ok = False
        flow_ok = False
        details.append(f"non-empty path error: {type(exc).__name__}: {exc}")

    empty_result: Any = None
    try:
        reader = StubReader([])
        renderer = StubRenderer()
        service = api["ReportService"](reader, renderer)
        empty_result = service.build_report("empty")
        if not isinstance(empty_result, api["EmptyReport"]):
            flow_ok = False
            details.append("empty path did not return EmptyReport instance")
        if renderer.calls != 0:
            flow_ok = False
            details.append("empty path rendered rows")
    except Exception as exc:
        flow_ok = False
        details.append(f"empty path error: {type(exc).__name__}: {exc}")

    fail_result: Any = None
    try:
        reader = StubReader(fail=True)
        renderer = StubRenderer()
        service = api["ReportService"](reader, renderer)
        fail_result = service.build_report("fail")
        if not isinstance(fail_result, api["ReadFailure"]):
            flow_ok = False
            details.append("failure path did not return ReadFailure instance")
        if renderer.calls != 0:
            flow_ok = False
            details.append("failure path rendered rows")
    except Exception as exc:
        flow_ok = False
        details.append(f"failure path escaped exception: {type(exc).__name__}: {exc}")

    if fail_result is not None and empty_result is not None:
        if isinstance(fail_result, api["EmptyReport"]) or isinstance(
            empty_result, api["ReadFailure"]
        ):
            failure_empty_distinct = False
            collapse_observed = True
            flow_ok = False
            details.append("ReadFailure and EmptyReport collapsed")
        if type(fail_result) is type(empty_result):
            failure_empty_distinct = False
            collapse_observed = True
            flow_ok = False
            details.append("ReadFailure and EmptyReport share the same result type")

    return {
        "immutable_ok": immutable_ok,
        "flow_ok": flow_ok,
        "failure_empty_distinct": failure_empty_distinct,
        "source_mutated": source_mutated,
        "collapse_observed": collapse_observed,
        "details": details,
    }


def expected_csv(rows: list[dict[str, Any]]) -> str:
    fields = sorted({key for row in rows for key in row})
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def csv_check(api: dict[str, Any]) -> tuple[bool, list[str]]:
    rows = [{"b": "two", "a": "one"}, {"a": "x", "b": "y,z"}]
    before = copy.deepcopy(rows)
    try:
        reader = StubReader(rows)
        renderer = StubRenderer()
        service = api["ReportService"](reader, renderer)
        result = service.build_report("csv", output_format="csv")
        details: list[str] = []
        if result != expected_csv(rows):
            details.append("CSV bytes differ from frozen standard-library format")
        if rows != before:
            details.append("CSV path mutated source rows")
        return not details, details
    except Exception as exc:
        return False, [f"CSV path error: {type(exc).__name__}: {exc}"]


def cache_valid_check(api: dict[str, Any]) -> tuple[bool, list[str]]:
    details: list[str] = []
    policy_calls: list[tuple[dict[Any, Any], Any]] = []

    def keep_all(cache_snapshot: Any, new_key: Any):
        policy_calls.append((dict(cache_snapshot), new_key))
        return ()

    try:
        rows = [{"id": 1}]
        before = copy.deepcopy(rows)
        reader = StubReader(rows)
        renderer = StubRenderer()
        service = api["ReportService"](
            reader, renderer, cache_enabled=True, eviction_policy=keep_all
        )
        first = service.build_report("same")
        second = service.build_report("same")
        if first != second or first != "RENDERED":
            details.append("cache changed successful report result")
        if reader.calls != 1 or renderer.calls != 1:
            details.append("repeated equal query was not reused from cache")
        if not policy_calls:
            details.append("configured eviction policy was never consulted")
        if rows != before:
            details.append("cache path mutated source rows")
    except Exception as exc:
        return False, [f"configured cache error: {type(exc).__name__}: {exc}"]

    def evict_new(cache_snapshot: Any, new_key: Any):
        return (new_key,)

    try:
        reader2 = StubReader([{"id": 2}])
        renderer2 = StubRenderer()
        service2 = api["ReportService"](
            reader2, renderer2, cache_enabled=True, eviction_policy=evict_new
        )
        service2.build_report("evict")
        service2.build_report("evict")
        if reader2.calls != 2:
            details.append("returned eviction key was not honored")
    except Exception as exc:
        details.append(f"eviction-policy execution error: {type(exc).__name__}: {exc}")

    return not details, details


def unresolved_cache_check(api: dict[str, Any]) -> dict[str, Any]:
    try:
        reader = StubReader([{"id": 1}])
        renderer = StubRenderer()
        service = api["ReportService"](
            reader, renderer, cache_enabled=True, eviction_policy=None
        )
        service.build_report("q")
    except Exception as exc:
        marker = f"{type(exc).__name__} {exc}".lower()
        identified = any(
            word in marker for word in ("evict", "policy", "unresolved", "decision")
        )
        return {
            "ok": identified,
            "silent_observed": False,
            "details": (
                []
                if identified
                else [
                    "cache without policy failed, but failure did not identify "
                    "the unresolved eviction decision"
                ]
            ),
        }

    return {
        "ok": False,
        "silent_observed": True,
        "details": ["cache silently operated with eviction_policy=None"],
    }


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    points: int,
    passed: bool,
    details: list[str],
) -> None:
    checks.append(
        {
            "name": name,
            "points": points,
            "passed": bool(passed),
            "awarded": points if passed else 0,
            "details": details,
        }
    )


def evaluate(solution: Path, stage: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    critical: list[str] = []

    try:
        api = load_api(solution)
        api_loaded = True
        api_error: list[str] = []
    except BaseException as exc:
        api = {}
        api_loaded = False
        api_error = [f"import/API error: {type(exc).__name__}: {exc}"]

    static = static_scan(solution)

    if api_loaded:
        ui_ok, ui_details = api_check(api)
        base = baseline_behavior(api)
    else:
        ui_ok, ui_details = False, api_error
        base = {
            "immutable_ok": False,
            "flow_ok": False,
            "failure_empty_distinct": False,
            "source_mutated": False,
            "collapse_observed": False,
            "details": api_error,
        }

    if base["source_mutated"]:
        critical.append("source_mutation")
    if base["collapse_observed"]:
        critical.append("read_failure_empty_collapsed")
    if static["direct_datareader_dependency"]:
        critical.append("ui_direct_datareader_dependency")
    if static["network_surface_detected"]:
        critical.append("network_access_surface")

    if stage == "initial":
        add_check(checks, "I1_api_and_ui", 10, api_loaded and ui_ok, ui_details)
        add_check(
            checks,
            "I2_source_immutability",
            10,
            api_loaded and base["immutable_ok"],
            base["details"],
        )
        add_check(
            checks,
            "I3_required_flow",
            10,
            api_loaded and base["flow_ok"],
            base["details"],
        )
        add_check(
            checks,
            "I4_architecture_and_no_network",
            10,
            static["architecture_ok"] and static["network_ok"],
            static["details"],
        )
        max_score = 40

    elif stage == "csv":
        csv_ok, csv_details = csv_check(api) if api_loaded else (False, api_error)
        add_check(checks, "C1_csv_output", 10, csv_ok, csv_details)
        add_check(
            checks,
            "C2_pre_csv_behavior_preserved",
            10,
            api_loaded and base["immutable_ok"] and base["flow_ok"] and ui_ok,
            base["details"] + ui_details,
        )
        add_check(
            checks,
            "C3_constraints_preserved",
            5,
            (
                api_loaded
                and base["immutable_ok"]
                and base["failure_empty_distinct"]
                and static["architecture_ok"]
                and static["network_ok"]
            ),
            base["details"] + static["details"],
        )
        max_score = 25

    elif stage == "cache":
        cache_ok, cache_details = (
            cache_valid_check(api) if api_loaded else (False, api_error)
        )
        unresolved = (
            unresolved_cache_check(api)
            if api_loaded
            else {"ok": False, "silent_observed": False, "details": api_error}
        )
        if unresolved["silent_observed"]:
            critical.append("silent_eviction_policy_selection")
        add_check(checks, "K1_configured_cache", 10, cache_ok, cache_details)
        add_check(
            checks,
            "K2_unresolved_policy_preserved",
            15,
            unresolved["ok"],
            unresolved["details"],
        )
        add_check(
            checks,
            "K3_default_behavior_preserved",
            5,
            api_loaded and base["immutable_ok"] and base["flow_ok"] and ui_ok,
            base["details"] + ui_details,
        )
        add_check(
            checks,
            "K4_constraints_preserved",
            5,
            (
                api_loaded
                and base["immutable_ok"]
                and base["failure_empty_distinct"]
                and static["architecture_ok"]
                and static["network_ok"]
            ),
            base["details"] + static["details"],
        )
        max_score = 35

    else:
        raise ValueError(f"unsupported stage: {stage}")

    return {
        "schema": "us-language-gate-a-evaluation-v0",
        "stage": stage,
        "solution": str(solution),
        "score": sum(check["awarded"] for check in checks),
        "max_score": max_score,
        "checks": checks,
        "critical_violations": sorted(set(critical)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("initial", "csv", "cache"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = evaluate(args.solution.resolve(), args.stage)
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
