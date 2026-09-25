#!/usr/bin/env python3
"""Deterministic hidden evaluator for the frozen US Language Gate A2 pilot."""

from __future__ import annotations

import argparse
import ast
import copy
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable


NETWORK_MODULES = {
    "socket",
    "ftplib",
    "smtplib",
    "telnetlib",
    "http.client",
    "urllib.request",
    "xmlrpc.client",
}

STAGE_MAX = {
    "initial": 50,
    "batch": 25,
    "multi_export": 35,
    "retry": 40,
}


class StubService:
    def __init__(self) -> None:
        self.run_calls: list[Any] = []
        self.batch_calls: list[list[Any]] = []

    def run(self, job_id: Any) -> str:
        self.run_calls.append(job_id)
        return "RUN_OK"

    def run_many(self, job_ids: Any) -> list[Any]:
        values = list(job_ids)
        self.batch_calls.append(values)
        return [f"BATCH:{value}" for value in values]


class CountingProcessor:
    def __init__(
        self,
        api: dict[str, Any],
        *,
        fail_times: int = 0,
        mutate: bool = False,
        result_factory: Callable[[], Any] | None = None,
        trace: list[str] | None = None,
    ) -> None:
        self.api = api
        self.fail_times = fail_times
        self.mutate = mutate
        self.result_factory = result_factory or (
            lambda: {"computed": {"items": [1, 2]}}
        )
        self.trace = trace
        self.calls = 0
        self.clean_result: Any = None

    def process(self, payload: Any) -> Any:
        self.calls += 1
        if self.trace is not None:
            self.trace.append("process")
        if self.mutate:
            try:
                payload["meta"]["tags"].append("processor-mutated")
            except Exception:
                try:
                    payload["mutated"] = True
                except Exception:
                    pass
        if self.calls <= self.fail_times:
            raise self.api["ProcessingError"]("planned processing failure")
        result = self.result_factory()
        self.clean_result = copy.deepcopy(result)
        return result


class CountingExporter:
    def __init__(
        self,
        api: dict[str, Any],
        name: str,
        *,
        fail_times: int = 0,
        mutate: bool = False,
        receipt: Any | None = None,
        trace: list[str] | None = None,
    ) -> None:
        self.api = api
        self.name = name
        self.fail_times = fail_times
        self.mutate = mutate
        self.receipt = receipt if receipt is not None else f"receipt:{name}"
        self.trace = trace
        self.calls = 0

    def export(self, job_id: Any, result: Any) -> Any:
        self.calls += 1
        if self.trace is not None:
            self.trace.append(f"export:{self.name}")
        if self.mutate:
            try:
                result["computed"]["items"].append(999)
            except Exception:
                try:
                    result["mutated"] = True
                except Exception:
                    pass
        if self.calls <= self.fail_times:
            raise self.api["ExportError"](f"planned export failure: {self.name}")
        return copy.deepcopy(self.receipt)


class TraceStore:
    """Protocol-conforming evaluator store used to inspect operation ordering."""

    def __init__(self, initial_jobs: dict[Any, Any], trace: list[str]) -> None:
        self.trace = trace
        self.records = {
            key: {
                "payload": copy.deepcopy(payload),
                "state": "PENDING",
                "result": None,
                "export_receipts": {},
            }
            for key, payload in initial_jobs.items()
        }

    def load(self, job_id: Any) -> Any:
        record = self.records.get(job_id)
        return None if record is None else copy.deepcopy(record)

    def commit(self, job_id: Any, result: Any) -> None:
        self.trace.append("commit")
        self.records[job_id]["result"] = copy.deepcopy(result)
        self.records[job_id]["state"] = "COMMITTED"

    def record_export(self, job_id: Any, exporter_name: str, receipt: Any) -> None:
        self.trace.append(f"record:{exporter_name}")
        self.records[job_id]["export_receipts"][exporter_name] = copy.deepcopy(receipt)

    def mark_exported(self, job_id: Any) -> None:
        self.trace.append("mark_exported")
        self.records[job_id]["state"] = "EXPORTED"


class TraceAudit:
    def __init__(self) -> None:
        self._entries: list[Any] = []

    def append(self, event: Any) -> None:
        self._entries.append(copy.deepcopy(event))

    def entries(self) -> list[Any]:
        return copy.deepcopy(self._entries)


def _clear_candidate_modules() -> None:
    for name in list(sys.modules):
        if name == "workflow_relay" or name.startswith("workflow_relay."):
            del sys.modules[name]


def load_api(solution: Path) -> dict[str, Any]:
    _clear_candidate_modules()
    sys.path.insert(0, str(solution))
    try:
        modules = {
            "api": importlib.import_module("workflow_relay.api"),
            "service": importlib.import_module("workflow_relay.service"),
            "store": importlib.import_module("workflow_relay.store"),
            "processor": importlib.import_module("workflow_relay.processor"),
            "export": importlib.import_module("workflow_relay.export"),
            "audit": importlib.import_module("workflow_relay.audit"),
            "results": importlib.import_module("workflow_relay.results"),
        }
    finally:
        try:
            sys.path.remove(str(solution))
        except ValueError:
            pass

    results = modules["results"]
    return {
        "API": getattr(modules["api"], "API"),
        "WorkflowService": getattr(modules["service"], "WorkflowService"),
        "JobStore": getattr(modules["store"], "JobStore"),
        "Processor": getattr(modules["processor"], "Processor"),
        "Exporter": getattr(modules["export"], "Exporter"),
        "AuditLog": getattr(modules["audit"], "AuditLog"),
        "NotFound": getattr(results, "NotFound"),
        "ProcessingFailure": getattr(results, "ProcessingFailure"),
        "ExportFailure": getattr(results, "ExportFailure"),
        "Completed": getattr(results, "Completed"),
        "UnresolvedDecision": getattr(results, "UnresolvedDecision"),
        "ProcessingError": getattr(results, "ProcessingError"),
        "ExportError": getattr(results, "ExportError"),
    }


def static_scan(solution: Path) -> dict[str, Any]:
    package = solution / "workflow_relay"
    details: list[str] = []
    critical: list[str] = []
    architecture_ok = True
    network_ok = True

    if not package.is_dir():
        return {
            "architecture_ok": False,
            "network_ok": False,
            "details": ["missing workflow_relay package"],
            "critical": [],
        }

    forbidden_api_names = {"JobStore", "Processor", "Exporter", "AuditLog"}
    forbidden_api_modules = {
        "workflow_relay.store",
        "workflow_relay.processor",
        "workflow_relay.export",
        "workflow_relay.audit",
    }

    for path in sorted(package.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            architecture_ok = False
            network_ok = False
            details.append(f"{path.name}: parse/read error: {exc}")
            continue

        is_api = path.name == "api.py"
        is_store = path.name == "store.py"
        is_export = path.name == "export.py"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name in NETWORK_MODULES:
                        network_ok = False
                        critical.append("network_access_surface")
                        details.append(f"{path.name}: network import {name}")
                    if is_api and name in forbidden_api_modules:
                        architecture_ok = False
                        critical.append("api_forbidden_dependency")
                        details.append(f"api.py: forbidden import {name}")
                    if is_store and name == "workflow_relay.export":
                        architecture_ok = False
                        critical.append("jobstore_exporter_dependency")
                        details.append("store.py: forbidden Exporter module dependency")
                    if is_export and name == "workflow_relay.store":
                        architecture_ok = False
                        critical.append("exporter_jobstore_dependency")
                        details.append("export.py: forbidden JobStore module dependency")

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = {alias.name for alias in node.names}
                if module in NETWORK_MODULES:
                    network_ok = False
                    critical.append("network_access_surface")
                    details.append(f"{path.name}: network import-from {module}")
                if module == "urllib" and "request" in imported:
                    network_ok = False
                    critical.append("network_access_surface")
                    details.append(f"{path.name}: network import urllib.request")
                if module == "http" and "client" in imported:
                    network_ok = False
                    critical.append("network_access_surface")
                    details.append(f"{path.name}: network import http.client")
                normalized = module
                if module.startswith("workflow_relay."):
                    normalized = module
                elif module in {"store", "processor", "export", "audit"}:
                    normalized = "workflow_relay." + module
                if is_api and (
                    normalized in forbidden_api_modules
                    or bool(imported & forbidden_api_names)
                ):
                    architecture_ok = False
                    critical.append("api_forbidden_dependency")
                    details.append(f"api.py: forbidden dependency via {module}")
                if is_store and (
                    normalized == "workflow_relay.export" or "Exporter" in imported
                ):
                    architecture_ok = False
                    critical.append("jobstore_exporter_dependency")
                    details.append("store.py: forbidden Exporter dependency")
                if is_export and (
                    normalized == "workflow_relay.store" or "JobStore" in imported
                ):
                    architecture_ok = False
                    critical.append("exporter_jobstore_dependency")
                    details.append("export.py: forbidden JobStore dependency")

            elif is_api and isinstance(node, ast.Name) and node.id in forbidden_api_names:
                architecture_ok = False
                critical.append("api_forbidden_dependency")
                details.append(f"api.py: forbidden name reference {node.id}")

            elif is_store and isinstance(node, ast.Name) and node.id == "Exporter":
                architecture_ok = False
                critical.append("jobstore_exporter_dependency")
                details.append("store.py: forbidden Exporter name reference")

            elif is_export and isinstance(node, ast.Name) and node.id == "JobStore":
                architecture_ok = False
                critical.append("exporter_jobstore_dependency")
                details.append("export.py: forbidden JobStore name reference")

            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                if "http://" in lowered or "https://" in lowered:
                    network_ok = False
                    critical.append("network_access_surface")
                    details.append(f"{path.name}: URL literal")

    return {
        "architecture_ok": architecture_ok,
        "network_ok": network_ok,
        "details": details,
        "critical": sorted(set(critical)),
    }


def new_store(api: dict[str, Any], jobs: dict[Any, Any]) -> Any:
    return api["JobStore"](copy.deepcopy(jobs))


def new_audit(api: dict[str, Any]) -> Any:
    return api["AuditLog"]()


def kinds(audit: Any, job_id: Any | None = None) -> list[str]:
    values = []
    for event in audit.entries():
        try:
            if job_id is None or event.get("job_id") == job_id:
                values.append(event.get("kind"))
        except Exception:
            continue
    return values


def probe_api(api: dict[str, Any], *, batch: bool = False) -> tuple[bool, list[str]]:
    details: list[str] = []
    try:
        service = StubService()
        public = api["API"](service)
        if public.run("j") != "RUN_OK" or service.run_calls != ["j"]:
            details.append("API.run does not delegate exactly through service.run")
        if batch:
            result = public.run_many(["a", "b"])
            if result != ["BATCH:a", "BATCH:b"] or service.batch_calls != [["a", "b"]]:
                details.append("API.run_many does not delegate through service.run_many")
    except Exception as exc:
        details.append(f"API delegation error: {type(exc).__name__}: {exc}")
    return not details, details


def probe_flow(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    observed_types: list[type] = []

    try:
        store = new_store(api, {})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        result = api["WorkflowService"](store, processor, exporter, audit).run("missing")
        observed_types.append(type(result))
        if not isinstance(result, api["NotFound"]):
            details.append("missing job did not return NotFound")
        if processor.calls or exporter.calls:
            details.append("missing job called Processor or Exporter")
    except Exception as exc:
        details.append(f"missing-job flow error: {type(exc).__name__}: {exc}")

    try:
        store = new_store(api, {"p": {"meta": {"tags": []}}})
        processor = CountingProcessor(api, fail_times=1)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        result = api["WorkflowService"](store, processor, exporter, audit).run("p")
        observed_types.append(type(result))
        snapshot = store.load("p")
        if not isinstance(result, api["ProcessingFailure"]):
            details.append("processing failure did not return ProcessingFailure")
        if snapshot["state"] != "PENDING" or snapshot["result"] is not None:
            details.append("processing failure changed persisted commit state")
        if exporter.calls:
            details.append("processing failure called Exporter")
        if "processing_failed" not in kinds(audit, "p"):
            details.append("processing failure did not append processing_failed")
    except Exception as exc:
        details.append(f"processing-failure flow error: {type(exc).__name__}: {exc}")

    try:
        store = new_store(api, {"e": {"meta": {"tags": []}}})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default", fail_times=1)
        audit = new_audit(api)
        result = api["WorkflowService"](store, processor, exporter, audit).run("e")
        observed_types.append(type(result))
        snapshot = store.load("e")
        if not isinstance(result, api["ExportFailure"]):
            details.append("export failure did not return ExportFailure")
        if snapshot["state"] != "COMMITTED" or snapshot["result"] is None:
            details.append("export failure did not preserve COMMITTED result")
            critical.append("committed_state_rollback")
        event_kinds = kinds(audit, "e")
        if "committed" not in event_kinds or "export_failed" not in event_kinds:
            details.append("export failure missing committed/export_failed audit events")
    except Exception as exc:
        details.append(f"export-failure flow error: {type(exc).__name__}: {exc}")

    try:
        store = new_store(api, {"s": {"meta": {"tags": []}}})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        result = api["WorkflowService"](store, processor, exporter, audit).run("s")
        observed_types.append(type(result))
        snapshot = store.load("s")
        if not isinstance(result, api["Completed"]):
            details.append("success did not return Completed")
        if snapshot["state"] != "EXPORTED":
            details.append("success did not reach EXPORTED")
        if "default" not in snapshot["export_receipts"]:
            details.append("success did not persist default exporter receipt")
    except Exception as exc:
        details.append(f"success flow error: {type(exc).__name__}: {exc}")

    result_classes = [
        api["NotFound"],
        api["ProcessingFailure"],
        api["ExportFailure"],
        api["Completed"],
    ]
    try:
        collapsed = len(set(result_classes)) != 4 or any(
            left is not right and issubclass(left, right)
            for left in result_classes
            for right in result_classes
        )
    except TypeError:
        collapsed = True
    if collapsed or (len(observed_types) == 4 and len(set(observed_types)) != 4):
        details.append("required result categories are not pairwise distinct")
        critical.append("result_category_collapse")

    return not details, details, sorted(set(critical))


def probe_aliasing(api: dict[str, Any], *, use_batch: bool = False) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    payload = {"meta": {"tags": ["original"]}, "value": {"n": 1}}
    external_before = copy.deepcopy(payload)
    try:
        store = new_store(api, {"a": payload})
        processor = CountingProcessor(api, mutate=True)
        exporter = CountingExporter(api, "default", mutate=True)
        audit = new_audit(api)
        service = api["WorkflowService"](store, processor, exporter, audit)
        if use_batch:
            service.run_many(["a"])
        else:
            service.run("a")
        snapshot = store.load("a")
        if payload != external_before:
            details.append("JobStore construction/service mutated caller source payload")
            critical.append("canonical_payload_mutation")
        if snapshot["payload"] != external_before:
            details.append("Processor alias mutation changed canonical JobStore payload")
            critical.append("canonical_payload_mutation")
        if processor.clean_result is not None and snapshot["result"] != processor.clean_result:
            details.append("Exporter alias mutation changed committed JobStore result")
            critical.append("committed_result_mutation")
    except Exception as exc:
        details.append(f"alias-isolation error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def probe_state_order(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []

    trace: list[str] = []
    store = TraceStore({"j": {"meta": {"tags": []}}}, trace)
    processor = CountingProcessor(api, trace=trace)
    exporter = CountingExporter(api, "default", fail_times=1, trace=trace)
    audit = TraceAudit()
    try:
        result = api["WorkflowService"](store, processor, exporter, audit).run("j")
        if not isinstance(result, api["ExportFailure"]):
            details.append("planned export failure did not surface ExportFailure")
        if "commit" not in trace or "export:default" not in trace:
            details.append("commit/export trace incomplete")
        elif trace.index("commit") > trace.index("export:default"):
            details.append("export occurred before commit")
        if store.load("j")["state"] != "COMMITTED":
            details.append("failed export rolled back/changed COMMITTED state")
            critical.append("committed_state_rollback")
    except Exception as exc:
        details.append(f"commit/export order error: {type(exc).__name__}: {exc}")

    trace2: list[str] = []
    store2 = TraceStore({"k": {"meta": {"tags": []}}}, trace2)
    processor2 = CountingProcessor(api, trace=trace2)
    exporter2 = CountingExporter(api, "default", trace=trace2)
    audit2 = TraceAudit()
    try:
        service2 = api["WorkflowService"](store2, processor2, exporter2, audit2)
        first = service2.run("k")
        second = service2.run("k")
        if not isinstance(first, api["Completed"]) or not isinstance(second, api["Completed"]):
            details.append("successful/repeated execution did not return Completed")
        if processor2.calls != 1:
            details.append("already EXPORTED job recomputed Processor")
        if exporter2.calls != 1:
            details.append("already EXPORTED job repeated successful external effect")
            if exporter2.calls > 1:
                critical.append("duplicate_successful_external_effect")
        if store2.load("k")["state"] != "EXPORTED":
            details.append("successful job did not persist EXPORTED")
        elif "commit" not in trace2:
            details.append("job reached EXPORTED without a commit transition")
            critical.append("pending_to_exported_without_commit")
    except Exception as exc:
        details.append(f"repeat-success error: {type(exc).__name__}: {exc}")

    return not details, details, sorted(set(critical))


def probe_audit(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        audit = new_audit(api)
        first_event = {"job_id": "a", "kind": "committed", "nested": {"v": [1]}}
        audit.append(first_event)
        view = audit.entries()
        try:
            view[0]["kind"] = "corrupt"
            view[0]["nested"]["v"].append(2)
        except Exception:
            pass
        audit.append({"job_id": "a", "kind": "exported", "exporter": "default"})
        final = audit.entries()
        if len(final) != 2:
            details.append("AuditLog append did not preserve both entries")
            critical.append("audit_history_mutation")
        else:
            if final[0] != first_event:
                details.append("earlier AuditLog entry changed after returned-alias mutation")
                critical.append("audit_history_mutation")
            if final[1].get("kind") != "exported":
                details.append("later AuditLog append not retained in order")
                critical.append("audit_history_mutation")
    except Exception as exc:
        details.append(f"AuditLog append-only error: {type(exc).__name__}: {exc}")

    try:
        store = new_store(api, {"s": {"meta": {"tags": []}}})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        api["WorkflowService"](store, processor, exporter, audit).run("s")
        event_kinds = kinds(audit, "s")
        if "committed" not in event_kinds or "exported" not in event_kinds:
            details.append("success flow did not append committed/exported events")
        elif event_kinds.index("committed") > event_kinds.index("exported"):
            details.append("exported audit event precedes committed event")
    except Exception as exc:
        details.append(f"service audit-event error: {type(exc).__name__}: {exc}")

    return not details, details, sorted(set(critical))


def probe_batch(api: dict[str, Any]) -> tuple[bool, list[str]]:
    details: list[str] = []
    api_ok, api_details = probe_api(api, batch=True)
    if not api_ok:
        details.extend(api_details)
    try:
        store = new_store(api, {"a": {"meta": {"tags": []}}})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        service = api["WorkflowService"](store, processor, exporter, audit)
        result = service.run_many(["missing", "a"])
        if len(result) != 2:
            details.append("run_many did not return one result per input")
        else:
            if not isinstance(result[0], api["NotFound"]):
                details.append("run_many input order/result mapping is incorrect at index 0")
            if not isinstance(result[1], api["Completed"]):
                details.append("run_many input order/result mapping is incorrect at index 1")
    except Exception as exc:
        details.append(f"batch behavior error: {type(exc).__name__}: {exc}")
    return not details, details


def probe_batch_duplicates(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store = new_store(api, {"a": {"meta": {"tags": []}}})
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default")
        audit = new_audit(api)
        service = api["WorkflowService"](store, processor, exporter, audit)
        result = service.run_many(["a", "a", "a"])
        if len(result) != 3 or not all(isinstance(x, api["Completed"]) for x in result):
            details.append("duplicate-ID batch did not produce three Completed results")
        if exporter.calls != 1:
            details.append("duplicate-ID batch repeated successful external effect")
            if exporter.calls > 1:
                critical.append("duplicate_successful_external_effect")
        if processor.calls != 1:
            details.append("duplicate-ID batch recomputed an already EXPORTED job")
    except Exception as exc:
        details.append(f"duplicate-ID batch error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def make_multi_service(
    api: dict[str, Any],
    store: Any,
    audit: Any,
    processor: Any,
    exporters: dict[str, Any],
    policy: Any,
    **kwargs: Any,
) -> Any:
    return api["WorkflowService"](
        store,
        processor,
        None,
        audit,
        exporters=exporters,
        fanout_policy=policy,
        **kwargs,
    )


def probe_multi_unresolved(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    exporters = {
        "a": CountingExporter(api, "a"),
        "b": CountingExporter(api, "b"),
    }
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api)
        try:
            service = make_multi_service(api, store, audit, processor, exporters, None)
            service.run("j")
        except api["UnresolvedDecision"]:
            return True, [], []
        details.append("multiple exporters with no fanout policy operated silently")
        critical.append("silent_multi_export_policy_selection")
    except Exception as exc:
        details.append(
            "missing fanout policy failed with wrong exception: "
            f"{type(exc).__name__}: {exc}"
        )
    return False, details, critical


def probe_multi_explicit(api: dict[str, Any]) -> tuple[bool, list[str]]:
    details: list[str] = []
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api)
        a = CountingExporter(api, "a")
        b = CountingExporter(api, "b")
        policy_inputs: list[Any] = []

        def policy(names: Any) -> tuple[str, str]:
            policy_inputs.append(names)
            return ("a", "b")

        service = make_multi_service(
            api,
            store,
            audit,
            processor,
            {"b": b, "a": a},
            policy,
        )
        result = service.run("j")
        snapshot = store.load("j")
        if policy_inputs != [("a", "b")]:
            details.append("fanout_policy did not receive lexicographically sorted tuple")
        if not isinstance(result, api["Completed"]):
            details.append("explicit two-exporter policy did not complete")
        if a.calls != 1 or b.calls != 1:
            details.append("explicit policy did not invoke each required exporter once")
        if snapshot["state"] != "EXPORTED":
            details.append("explicit policy success did not persist EXPORTED")
        if set(snapshot["export_receipts"]) != {"a", "b"}:
            details.append("explicit policy did not persist both success receipts")
    except Exception as exc:
        details.append(f"explicit multi-export error: {type(exc).__name__}: {exc}")
    return not details, details


def partial_multi_fixture(api: dict[str, Any]) -> tuple[Any, ...]:
    """Create one success then one failure regardless of delegated exporter order."""

    shared = {"calls": 0, "failed_name": None}

    class PartialExporter:
        def __init__(self, name: str) -> None:
            self.name = name
            self.calls = 0

        def export(self, job_id: Any, result: Any) -> Any:
            self.calls += 1
            shared["calls"] += 1
            if shared["calls"] == 2:
                shared["failed_name"] = self.name
                raise api["ExportError"](f"planned second-exporter failure: {self.name}")
            return f"receipt:{self.name}"

    store = new_store(api, {"j": {"meta": {"tags": []}}})
    audit = new_audit(api)
    processor = CountingProcessor(api)
    a = PartialExporter("a")
    b = PartialExporter("b")
    service = make_multi_service(
        api,
        store,
        audit,
        processor,
        {"a": a, "b": b},
        lambda names: ("a", "b"),
    )
    result = service.run("j")
    snapshot = store.load("j")
    succeeded = set(snapshot["export_receipts"])
    return store, audit, processor, a, b, result, succeeded, shared["failed_name"]


def probe_multi_partial(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store, audit, processor, a, b, result, succeeded, failed_name = partial_multi_fixture(api)
        snapshot = store.load("j")
        if not isinstance(result, api["ExportFailure"]):
            details.append("partial exporter failure did not return ExportFailure")
        if snapshot["state"] != "COMMITTED":
            details.append("partial exporter failure did not remain COMMITTED")
            critical.append("committed_state_rollback")
        if snapshot["result"] is None:
            details.append("partial exporter failure lost committed result")
            critical.append("committed_state_rollback")
        if len(succeeded) != 1:
            details.append("partial exporter failure did not persist exactly one prior success")
        if failed_name is None:
            details.append("partial exporter fixture never reached its planned failure")
        elif failed_name in snapshot["export_receipts"]:
            details.append("failed exporter incorrectly received success receipt")
    except Exception as exc:
        details.append(f"partial multi-export error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def probe_multi_replacement(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store, audit, processor, a1, b1, first, succeeded, failed_name = partial_multi_fixture(api)
        if not isinstance(first, api["ExportFailure"]):
            details.append("fixture did not reach partial ExportFailure")
            return False, details, critical
        if len(succeeded) != 1 or failed_name not in {"a", "b"}:
            details.append("fixture did not produce one persisted success and one failure")
            return False, details, critical

        a2 = CountingExporter(api, "a")
        b2 = CountingExporter(api, "b")
        replacements = {"a": a2, "b": b2}
        replacement = make_multi_service(
            api,
            store,
            audit,
            CountingProcessor(api),
            replacements,
            lambda names: ("a", "b"),
        )
        second = replacement.run("j")
        snapshot = store.load("j")
        succeeded_name = next(iter(succeeded))
        if not isinstance(second, api["Completed"]):
            details.append("replacement WorkflowService did not complete pending exporter")
        if replacements[succeeded_name].calls != 0:
            details.append(
                "replacement service repeated exporter with persisted success receipt"
            )
            critical.append("duplicate_successful_external_effect")
        if replacements[failed_name].calls != 1:
            details.append("replacement service did not call pending exporter exactly once")
        if snapshot["state"] != "EXPORTED":
            details.append("replacement recovery did not reach EXPORTED")
        if set(snapshot["export_receipts"]) != {"a", "b"}:
            details.append("replacement recovery did not preserve/complete receipts")
    except Exception as exc:
        details.append(f"replacement-service recovery error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def probe_retry_unresolved(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api, fail_times=1)
        exporter = CountingExporter(api, "default")
        try:
            service = api["WorkflowService"](
                store,
                processor,
                exporter,
                audit,
                retry_enabled=True,
                retry_policy=None,
            )
            service.run("j")
        except api["UnresolvedDecision"]:
            return True, [], []
        details.append("retry_enabled=True with no policy operated silently")
        critical.append("silent_retry_policy_selection")
    except Exception as exc:
        details.append(
            "missing retry policy failed with wrong exception: "
            f"{type(exc).__name__}: {exc}"
        )
    return False, details, critical


def probe_retry_process(api: dict[str, Any]) -> tuple[bool, list[str]]:
    details: list[str] = []
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api, fail_times=1)
        exporter = CountingExporter(api, "default")
        policy_calls: list[tuple[str, int]] = []

        def policy(phase: str, error: Exception, attempt: int) -> bool:
            policy_calls.append((phase, attempt))
            return phase == "process" and attempt == 1

        service = api["WorkflowService"](
            store,
            processor,
            exporter,
            audit,
            retry_enabled=True,
            retry_policy=policy,
        )
        result = service.run("j")
        if not isinstance(result, api["Completed"]):
            details.append("processor retry did not complete")
        if processor.calls != 2:
            details.append("processor retry did not perform exactly two process calls")
        if exporter.calls != 1:
            details.append("processor retry did not export exactly once after success")
        if ("process", 1) not in policy_calls:
            details.append("retry policy did not receive process failure attempt 1")
    except Exception as exc:
        details.append(f"processor retry error: {type(exc).__name__}: {exc}")
    return not details, details


def probe_retry_export(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api)
        exporter = CountingExporter(api, "default", fail_times=1)

        def policy(phase: str, error: Exception, attempt: int) -> bool:
            return phase == "export:default" and attempt == 1

        service = api["WorkflowService"](
            store,
            processor,
            exporter,
            audit,
            retry_enabled=True,
            retry_policy=policy,
        )
        result = service.run("j")
        if not isinstance(result, api["Completed"]):
            details.append("export retry did not complete")
        if processor.calls != 1:
            details.append("export retry recomputed Processor after commit")
        if exporter.calls != 2:
            details.append("export retry did not perform fail-then-success exactly twice")
        if store.load("j")["state"] != "EXPORTED":
            details.append("export retry did not persist EXPORTED")
    except Exception as exc:
        details.append(f"export retry error: {type(exc).__name__}: {exc}")
    return not details, details, critical


def probe_retry_multi(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    try:
        store = new_store(api, {"j": {"meta": {"tags": []}}})
        audit = new_audit(api)
        processor = CountingProcessor(api)
        a = CountingExporter(api, "a")
        b = CountingExporter(api, "b", fail_times=1)

        def retry_policy(phase: str, error: Exception, attempt: int) -> bool:
            return phase == "export:b" and attempt == 1

        service = make_multi_service(
            api,
            store,
            audit,
            processor,
            {"a": a, "b": b},
            lambda names: ("a", "b"),
            retry_enabled=True,
            retry_policy=retry_policy,
        )
        result = service.run("j")
        if not isinstance(result, api["Completed"]):
            details.append("multi-export retry did not complete")
        if a.calls != 1:
            details.append("multi-export retry repeated already-successful exporter a")
            if a.calls > 1:
                critical.append("duplicate_successful_external_effect")
        if b.calls != 2:
            details.append("multi-export retry did not retry failing exporter b exactly once")
        if processor.calls != 1:
            details.append("multi-export retry recomputed Processor")
    except Exception as exc:
        details.append(f"multi-export retry error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def probe_retry_integrity(api: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    details: list[str] = []
    critical: list[str] = []
    payload = {"meta": {"tags": ["original"]}}
    original = copy.deepcopy(payload)
    try:
        store = new_store(api, {"j": payload})
        audit = new_audit(api)
        processor = CountingProcessor(api, mutate=True)
        exporter = CountingExporter(api, "default", fail_times=1, mutate=True)

        def policy(phase: str, error: Exception, attempt: int) -> bool:
            return phase == "export:default" and attempt == 1

        service = api["WorkflowService"](
            store,
            processor,
            exporter,
            audit,
            retry_enabled=True,
            retry_policy=policy,
        )
        audit.append({"job_id": "pre", "kind": "committed", "nested": {"v": [1]}})
        before_entries = copy.deepcopy(audit.entries())
        service.run("j")
        snapshot = store.load("j")
        after_entries = audit.entries()
        if snapshot["payload"] != original:
            details.append("retry path allowed canonical payload mutation")
            critical.append("canonical_payload_mutation")
        if processor.clean_result is not None and snapshot["result"] != processor.clean_result:
            details.append("retry path allowed committed-result mutation")
            critical.append("committed_result_mutation")
        if after_entries[: len(before_entries)] != before_entries:
            details.append("retry path rewrote prior audit history")
            critical.append("audit_history_mutation")
        if snapshot["state"] != "EXPORTED":
            details.append("retry integrity fixture did not finish EXPORTED")
    except Exception as exc:
        details.append(f"retry integrity error: {type(exc).__name__}: {exc}")
    return not details, details, sorted(set(critical))


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    points: int,
    family: str,
    passed: bool,
    details: list[str],
) -> None:
    checks.append(
        {
            "name": name,
            "points": points,
            "family": family,
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
    critical.extend(static["critical"])

    if stage == "initial":
        api_ok, api_details = probe_api(api) if api_loaded else (False, api_error)
        flow_ok, flow_details, flow_critical = (
            probe_flow(api) if api_loaded else (False, api_error, [])
        )
        alias_ok, alias_details, alias_critical = (
            probe_aliasing(api) if api_loaded else (False, api_error, [])
        )
        state_ok, state_details, state_critical = (
            probe_state_order(api) if api_loaded else (False, api_error, [])
        )
        audit_ok, audit_details, audit_critical = (
            probe_audit(api) if api_loaded else (False, api_error, [])
        )
        critical.extend(flow_critical + alias_critical + state_critical + audit_critical)

        add_check(checks, "I1_api_delegation", 5, "architecture", api_ok, api_details)
        add_check(
            checks,
            "I2_architecture_no_network",
            10,
            "architecture",
            static["architecture_ok"] and static["network_ok"],
            static["details"],
        )
        add_check(checks, "I3_required_flow", 10, "state_flow", flow_ok, flow_details)
        add_check(checks, "I4_alias_isolation", 10, "aliasing", alias_ok, alias_details)
        add_check(checks, "I5_commit_export_state", 10, "state_flow", state_ok, state_details)
        add_check(checks, "I6_append_only_audit", 5, "audit", audit_ok, audit_details)

    elif stage == "batch":
        batch_ok, batch_details = probe_batch(api) if api_loaded else (False, api_error)
        dup_ok, dup_details, dup_critical = (
            probe_batch_duplicates(api) if api_loaded else (False, api_error, [])
        )
        alias_ok, alias_details, alias_critical = (
            probe_aliasing(api, use_batch=True) if api_loaded else (False, api_error, [])
        )
        flow_ok, flow_details, flow_critical = (
            probe_flow(api) if api_loaded else (False, api_error, [])
        )
        audit_ok, audit_details, audit_critical = (
            probe_audit(api) if api_loaded else (False, api_error, [])
        )
        critical.extend(dup_critical + alias_critical + flow_critical + audit_critical)
        preserved = (
            api_loaded
            and static["architecture_ok"]
            and static["network_ok"]
            and flow_ok
            and audit_ok
        )
        preservation_details = static["details"] + flow_details + audit_details

        add_check(checks, "B1_batch_semantics", 5, "state_flow", batch_ok, batch_details)
        add_check(
            checks,
            "B2_duplicate_effect_protection",
            10,
            "external_effects",
            dup_ok,
            dup_details,
        )
        add_check(checks, "B3_batch_alias_isolation", 5, "aliasing", alias_ok, alias_details)
        add_check(
            checks,
            "B4_prior_constraints",
            5,
            "preservation",
            preserved,
            preservation_details,
        )

    elif stage == "multi_export":
        unresolved_ok, unresolved_details, unresolved_critical = (
            probe_multi_unresolved(api) if api_loaded else (False, api_error, [])
        )
        explicit_ok, explicit_details = (
            probe_multi_explicit(api) if api_loaded else (False, api_error)
        )
        partial_ok, partial_details, partial_critical = (
            probe_multi_partial(api) if api_loaded else (False, api_error, [])
        )
        replacement_ok, replacement_details, replacement_critical = (
            probe_multi_replacement(api) if api_loaded else (False, api_error, [])
        )
        flow_ok, flow_details, flow_critical = (
            probe_flow(api) if api_loaded else (False, api_error, [])
        )
        dup_ok, dup_details, dup_critical = (
            probe_batch_duplicates(api) if api_loaded else (False, api_error, [])
        )
        alias_ok, alias_details, alias_critical = (
            probe_aliasing(api, use_batch=True) if api_loaded else (False, api_error, [])
        )
        audit_ok, audit_details, audit_critical = (
            probe_audit(api) if api_loaded else (False, api_error, [])
        )
        critical.extend(
            unresolved_critical
            + partial_critical
            + replacement_critical
            + flow_critical
            + dup_critical
            + alias_critical
            + audit_critical
        )
        preserved = (
            api_loaded
            and static["architecture_ok"]
            and static["network_ok"]
            and flow_ok
            and dup_ok
            and alias_ok
            and audit_ok
        )

        add_check(
            checks,
            "M1_unresolved_fanout",
            10,
            "unresolved",
            unresolved_ok,
            unresolved_details,
        )
        add_check(
            checks,
            "M2_explicit_fanout_policy",
            5,
            "state_flow",
            explicit_ok,
            explicit_details,
        )
        add_check(
            checks,
            "M3_partial_receipt_persistence",
            5,
            "preservation",
            partial_ok,
            partial_details,
        )
        add_check(
            checks,
            "M4_replacement_resume",
            5,
            "external_effects",
            replacement_ok,
            replacement_details,
        )
        add_check(
            checks,
            "M5_committed_state_survives_partial_failure",
            5,
            "state_flow",
            partial_ok,
            partial_details,
        )
        add_check(
            checks,
            "M6_prior_constraints",
            5,
            "preservation",
            preserved,
            static["details"] + flow_details + dup_details + alias_details + audit_details,
        )

    elif stage == "retry":
        unresolved_ok, unresolved_details, unresolved_critical = (
            probe_retry_unresolved(api) if api_loaded else (False, api_error, [])
        )
        process_ok, process_details = (
            probe_retry_process(api) if api_loaded else (False, api_error)
        )
        export_ok, export_details, export_critical = (
            probe_retry_export(api) if api_loaded else (False, api_error, [])
        )
        multi_ok, multi_details, multi_critical = (
            probe_retry_multi(api) if api_loaded else (False, api_error, [])
        )
        integrity_ok, integrity_details, integrity_critical = (
            probe_retry_integrity(api) if api_loaded else (False, api_error, [])
        )
        explicit_multi_ok, explicit_multi_details = (
            probe_multi_explicit(api) if api_loaded else (False, api_error)
        )
        batch_ok, batch_details = probe_batch(api) if api_loaded else (False, api_error)
        flow_ok, flow_details, flow_critical = (
            probe_flow(api) if api_loaded else (False, api_error, [])
        )
        alias_ok, alias_details, alias_critical = (
            probe_aliasing(api, use_batch=True) if api_loaded else (False, api_error, [])
        )
        audit_ok, audit_details, audit_critical = (
            probe_audit(api) if api_loaded else (False, api_error, [])
        )
        replacement_ok, replacement_details, replacement_critical = (
            probe_multi_replacement(api) if api_loaded else (False, api_error, [])
        )
        fanout_unresolved_ok, fanout_unresolved_details, fanout_unresolved_critical = (
            probe_multi_unresolved(api) if api_loaded else (False, api_error, [])
        )
        critical.extend(
            unresolved_critical
            + export_critical
            + multi_critical
            + integrity_critical
            + flow_critical
            + alias_critical
            + audit_critical
            + replacement_critical
            + fanout_unresolved_critical
        )
        preserved = (
            api_loaded
            and static["architecture_ok"]
            and static["network_ok"]
            and explicit_multi_ok
            and batch_ok
            and flow_ok
            and alias_ok
            and audit_ok
            and replacement_ok
            and fanout_unresolved_ok
        )

        add_check(
            checks,
            "R1_unresolved_retry",
            10,
            "unresolved",
            unresolved_ok,
            unresolved_details,
        )
        add_check(
            checks,
            "R2_processing_retry",
            10,
            "state_flow",
            process_ok,
            process_details,
        )
        add_check(
            checks,
            "R3_export_retry_no_recompute",
            5,
            "state_flow",
            export_ok,
            export_details,
        )
        add_check(
            checks,
            "R4_retry_no_duplicate_export",
            5,
            "external_effects",
            multi_ok,
            multi_details,
        )
        add_check(
            checks,
            "R5_retry_integrity",
            5,
            "preservation",
            integrity_ok,
            integrity_details,
        )
        add_check(
            checks,
            "R6_prior_constraints",
            5,
            "preservation",
            preserved,
            static["details"]
            + explicit_multi_details
            + batch_details
            + flow_details
            + alias_details
            + audit_details
            + replacement_details
            + fanout_unresolved_details,
        )

    else:
        raise ValueError(f"unsupported stage: {stage}")

    return {
        "schema": "us-language-gate-a2-evaluation-v0",
        "stage": stage,
        "solution": str(solution),
        "score": sum(check["awarded"] for check in checks),
        "max_score": STAGE_MAX[stage],
        "family_scores": {
            family: sum(
                check["awarded"] for check in checks if check["family"] == family
            )
            for family in sorted({check["family"] for check in checks})
        },
        "checks": checks,
        "critical_violations": sorted(set(critical)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", required=True, type=Path)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("initial", "batch", "multi_export", "retry"),
    )
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
