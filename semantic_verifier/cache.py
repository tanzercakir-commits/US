"""Deterministic persistent cache for exact obligation results."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .backend import CheckerBackend
from .integer_types import parse_canonical_decimal
from .model import (
    Obligation,
    SCHEMA,
    TraceStep,
    TraceTemplate,
    VerificationResult,
    VerificationStatus,
    serialize_evidence_value,
)


CACHE_SCHEMA = "codeskeptic.obligation-result-cache/v1"
KEY_SCHEMA = "codeskeptic.obligation-semantic-key/v1"


def obligation_semantic_payload(
    obligation: Obligation,
    backend: CheckerBackend,
) -> dict[str, Any]:
    """Return the canonical logical query and referee policy identity."""

    assumptions = sorted(_canonical(item.to_dict()) for item in obligation.assumptions)
    return {
        "backend": dict(backend.cache_identity()),
        "key_schema": KEY_SCHEMA,
        "obligation": {
            "assumptions": assumptions,
            "conclusion": (
                obligation.conclusion.to_dict()
                if obligation.conclusion is not None
                else None
            ),
            "mode": obligation.mode,
            "unsupported_reason": obligation.unsupported_reason,
        },
        "report_schema": SCHEMA,
    }


def obligation_semantic_key(
    obligation: Obligation,
    backend: CheckerBackend,
) -> str:
    """Hash exact query semantics without IDs or source metadata."""

    payload = obligation_semantic_payload(obligation, backend)
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class CachedCheckerBackend(CheckerBackend):
    """Reuse only exact, schema-matching results from a deterministic JSON file."""

    def __init__(self, backend: CheckerBackend, path: str | Path) -> None:
        self.backend = backend
        self.name = backend.name
        self.path = Path(path)
        self._entries = self._load_entries()

    def cache_identity(self) -> Mapping[str, Any]:
        return self.backend.cache_identity()

    def check(self, obligation: Obligation) -> VerificationResult:
        result, changed = self._check(obligation)
        if changed:
            self._persist()
        return result

    def check_all(
        self, obligations: Iterable[Obligation]
    ) -> tuple[VerificationResult, ...]:
        results: list[VerificationResult] = []
        changed = False
        for obligation in obligations:
            result, obligation_changed = self._check(obligation)
            results.append(result)
            changed = changed or obligation_changed
        if changed:
            self._persist()
        return tuple(results)

    def _check(self, obligation: Obligation) -> tuple[VerificationResult, bool]:
        try:
            payload = obligation_semantic_payload(obligation, self.backend)
            digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
            cached = self._decode_entry(obligation, payload, self._entries.get(digest))
        except (OSError, TypeError, ValueError):
            return self.backend.check(obligation), False
        if cached is not None:
            return cached, False

        result = self.backend.check(obligation)
        try:
            encoded = _encode_entry(obligation, payload, result)
        except (TypeError, ValueError):
            return result, False
        if encoded is None:
            return result, False
        self._entries[digest] = encoded
        return result, True

    def _decode_entry(
        self,
        obligation: Obligation,
        payload: Mapping[str, Any],
        raw_entry: object,
    ) -> VerificationResult | None:
        if not isinstance(raw_entry, Mapping) or raw_entry.get("key") != payload:
            return None
        if raw_entry.get("trace_templates") != _trace_signature(
            obligation.trace_templates
        ):
            return None
        raw_result = raw_entry.get("result")
        if not isinstance(raw_result, Mapping):
            return None
        raw_status = raw_result.get("status")
        raw_message = raw_result.get("message")
        if not isinstance(raw_status, str) or not isinstance(raw_message, str):
            return None
        try:
            status = VerificationStatus(raw_status)
        except ValueError:
            return None
        if status == VerificationStatus.SOLVER_ERROR:
            return None

        valid, counterexample = _decode_counterexample(raw_result)
        if not valid:
            return None
        trace = _decode_trace(obligation.trace_templates, raw_result.get("trace"))
        if trace is None:
            return None
        if status != VerificationStatus.VIOLATED and (
            counterexample is not None or trace
        ):
            return None
        if (
            status == VerificationStatus.VIOLATED
            and obligation.mode == "validity"
            and counterexample is None
        ):
            return None
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=status,
            location=obligation.location,
            message=raw_message,
            counterexample=counterexample,
            trace=trace,
        )

    def _load_entries(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, Mapping) or payload.get("schema") != CACHE_SCHEMA:
            return {}
        entries = payload.get("entries")
        if not isinstance(entries, Mapping):
            return {}
        return {
            key: value
            for key, value in entries.items()
            if isinstance(key, str) and len(key) == 64
        }

    def _persist(self) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            rendered = (
                json.dumps(
                    {"entries": self._entries, "schema": CACHE_SCHEMA},
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
            os.replace(temporary, self.path)
        except (OSError, TypeError, ValueError):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _encode_entry(
    obligation: Obligation,
    payload: Mapping[str, Any],
    result: VerificationResult,
) -> dict[str, Any] | None:
    if result.status == VerificationStatus.SOLVER_ERROR:
        return None
    trace = _encode_trace(obligation.trace_templates, result.trace)
    if trace is None:
        return None
    encoded_result: dict[str, Any] = {
        "message": result.message,
        "status": result.status.value,
        "trace": trace,
    }
    if result.counterexample is not None:
        encoded_result["counterexample"] = {
            key: serialize_evidence_value(result.counterexample[key])
            for key in sorted(result.counterexample)
        }
    return {
        "key": dict(payload),
        "result": encoded_result,
        "trace_templates": _trace_signature(obligation.trace_templates),
    }


def _decode_counterexample(
    raw_result: Mapping[str, Any],
) -> tuple[bool, Mapping[str, int | bool | tuple[int, ...]] | None]:
    if "counterexample" not in raw_result:
        return True, None
    raw = raw_result["counterexample"]
    if not isinstance(raw, Mapping):
        return False, None
    decoded: dict[str, int | bool | tuple[int, ...]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return False, None
        if type(value) is bool:
            decoded[key] = value
            continue
        if isinstance(value, list):
            try:
                decoded[key] = tuple(
                    parse_canonical_decimal(item) for item in value
                )
            except ValueError:
                return False, None
            continue
        try:
            decoded[key] = parse_canonical_decimal(value)
        except ValueError:
            return False, None
    return True, {key: decoded[key] for key in sorted(decoded)}


def _trace_signature(templates: tuple[TraceTemplate, ...]) -> list[dict[str, Any]]:
    return [
        {
            "condition": template.condition.to_dict(),
            "guard": [item.to_dict() for item in template.guard],
            "kind": template.kind,
        }
        for template in templates
    ]


def _encode_trace(
    templates: tuple[TraceTemplate, ...],
    trace: tuple[TraceStep, ...],
) -> list[dict[str, Any]] | None:
    encoded: list[dict[str, Any]] = []
    next_index = 0
    for step in trace:
        if type(step.taken) is not bool:
            return None
        matched = None
        for index in range(next_index, len(templates)):
            template = templates[index]
            if (
                template.kind == step.kind
                and template.condition == step.condition
                and template.location == step.location
            ):
                matched = index
                break
        if matched is None:
            return None
        encoded.append({"taken": step.taken, "template": matched})
        next_index = matched + 1
    return encoded


def _decode_trace(
    templates: tuple[TraceTemplate, ...], raw: object
) -> tuple[TraceStep, ...] | None:
    if not isinstance(raw, list):
        return None
    decoded: list[TraceStep] = []
    previous = -1
    for item in raw:
        if not isinstance(item, Mapping):
            return None
        index = item.get("template")
        taken = item.get("taken")
        if type(index) is not int or type(taken) is not bool:
            return None
        if index <= previous or not 0 <= index < len(templates):
            return None
        template = templates[index]
        decoded.append(
            TraceStep(template.kind, template.condition, taken, template.location)
        )
        previous = index
    return tuple(decoded)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
