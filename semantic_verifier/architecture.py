"""Fail-closed architectural enforcement over exact direct-call facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from . import __version__
from .architecture_policy import ArchitecturePolicy
from .facts import FactIndex, FactLocation, FactSymbol


ARCHITECTURE_RESULT_SCHEMA = "codeskeptic.architecture-result/v1"

FORBIDDEN_DEPENDENCY_RULE_ID = "CSARCH001"
INCOMPLETE_EVIDENCE_RULE_ID = "CSARCH002"
SARIF_SCHEMA = (
    "https://json.schemastore.org/sarif-2.1.0.json"
)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _compact_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _location_dict(
    location: FactLocation | None,
) -> dict[str, Any] | None:
    return (
        location.to_dict()
        if location is not None
        else None
    )


def _location_sort_key(
    location: Mapping[str, Any] | None,
) -> tuple[str, int, int]:
    if location is None:
        return ("", 0, 0)
    return (
        str(location["file"]),
        int(location["line"]),
        int(location["column"]),
    )


@dataclass(frozen=True, slots=True)
class ArchitectureDecision:
    call_id: str
    caller: Mapping[str, Any]
    callee: Mapping[str, Any]
    source_layer: str
    target_layer: str
    decision: str
    location: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "callee": dict(self.callee),
            "caller": dict(self.caller),
            "decision": self.decision,
            "from_layer": self.source_layer,
            "location": dict(self.location),
            "to_layer": self.target_layer,
        }

    def sort_key(self) -> tuple[Any, ...]:
        return (
            _location_sort_key(self.location),
            str(self.caller["qualified_name"]),
            str(self.callee["qualified_name"]),
            self.call_id,
        )


@dataclass(frozen=True, slots=True)
class ArchitectureUnknown:
    code: str
    message: str
    location: Mapping[str, Any] | None
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "evidence": dict(self.evidence),
            "location": (
                dict(self.location)
                if self.location is not None
                else None
            ),
            "message": self.message,
        }

    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.code,
            _location_sort_key(self.location),
            self.message,
            _compact_json(self.evidence),
        )


@dataclass(frozen=True, slots=True)
class ArchitectureReport:
    index_id: str
    policy_id: str
    call_count: int
    decisions: tuple[ArchitectureDecision, ...]
    unknowns: tuple[ArchitectureUnknown, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decisions",
            tuple(
                sorted(
                    self.decisions,
                    key=lambda decision: decision.sort_key(),
                )
            ),
        )
        object.__setattr__(
            self,
            "unknowns",
            tuple(
                sorted(
                    self.unknowns,
                    key=lambda unknown: unknown.sort_key(),
                )
            ),
        )

    @property
    def status(self) -> str:
        if self.unknowns:
            return "unknown"
        if any(
            decision.decision == "forbid"
            for decision in self.decisions
        ):
            return "violation"
        return "clean"

    @property
    def exit_code(self) -> int:
        return {
            "clean": 0,
            "violation": 1,
            "unknown": 2,
        }[self.status]

    def to_dict(self) -> dict[str, Any]:
        allowed = sum(
            decision.decision == "allow"
            for decision in self.decisions
        )
        forbidden = sum(
            decision.decision == "forbid"
            for decision in self.decisions
        )
        return {
            "decisions": [
                decision.to_dict()
                for decision in self.decisions
            ],
            "index_id": self.index_id,
            "policy_id": self.policy_id,
            "schema": ARCHITECTURE_RESULT_SCHEMA,
            "status": self.status,
            "summary": {
                "allowed": allowed,
                "calls": self.call_count,
                "decided": len(self.decisions),
                "forbidden": forbidden,
                "undecided_calls": (
                    self.call_count - len(self.decisions)
                ),
                "unknowns": len(self.unknowns),
            },
            "unknowns": [
                unknown.to_dict()
                for unknown in self.unknowns
            ],
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def to_text(self) -> str:
        payload = self.to_dict()
        summary = payload["summary"]
        lines = [
            f"architecture status: {self.status}",
            f"index: {self.index_id}",
            f"policy: {self.policy_id}",
            (
                f"calls: {summary['calls']} "
                f"(allowed={summary['allowed']}, "
                f"forbidden={summary['forbidden']}, "
                f"undecided={summary['undecided_calls']})"
            ),
            f"unknowns: {summary['unknowns']}",
        ]
        for decision in self.decisions:
            lines.append(
                (
                    f"- {decision.decision}: "
                    f"{decision.source_layer} -> "
                    f"{decision.target_layer}: "
                    f"{decision.caller['qualified_name']} calls "
                    f"{decision.callee['qualified_name']} at "
                    f"{decision.location['file']}:"
                    f"{decision.location['line']}:"
                    f"{decision.location['column']}"
                )
            )
        for unknown in self.unknowns:
            lines.append(
                f"- unknown {unknown.code}: {unknown.message}"
            )
        return "\n".join(lines) + "\n"

    def to_sarif_dict(self) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for decision in self.decisions:
            if decision.decision != "forbid":
                continue
            row = decision.to_dict()
            results.append(
                {
                    "level": "error",
                    "locations": [
                        _sarif_location(decision.location)
                    ],
                    "message": {
                        "text": (
                            "Forbidden dependency "
                            f"{decision.source_layer} -> "
                            f"{decision.target_layer}: "
                            f"{decision.caller['qualified_name']} "
                            "calls "
                            f"{decision.callee['qualified_name']}."
                        )
                    },
                    "partialFingerprints": {
                        "callFactId": decision.call_id,
                    },
                    "properties": {
                        "evidence": row,
                    },
                    "ruleId": FORBIDDEN_DEPENDENCY_RULE_ID,
                }
            )

        for unknown in self.unknowns:
            row = unknown.to_dict()
            result: dict[str, Any] = {
                "level": "warning",
                "message": {
                    "text": unknown.message,
                },
                "partialFingerprints": {
                    "evidenceId": _unknown_fingerprint(row),
                },
                "properties": {
                    "evidence": row,
                },
                "ruleId": INCOMPLETE_EVIDENCE_RULE_ID,
            }
            if unknown.location is not None:
                result["locations"] = [
                    _sarif_location(unknown.location)
                ]
            results.append(result)

        return {
            "$schema": SARIF_SCHEMA,
            "runs": [
                {
                    "properties": {
                        "indexId": self.index_id,
                        "policyId": self.policy_id,
                        "status": self.status,
                    },
                    "results": results,
                    "tool": {
                        "driver": {
                            "name": "CodeSkeptic",
                            "rules": _sarif_rules(),
                            "semanticVersion": __version__,
                        }
                    },
                }
            ],
            "version": "2.1.0",
        }

    def to_sarif(self) -> str:
        return _canonical_json(self.to_sarif_dict())


def _sarif_rules() -> list[dict[str, Any]]:
    return [
        {
            "defaultConfiguration": {
                "level": "error",
            },
            "fullDescription": {
                "text": (
                    "A resolved direct call crosses a layer pair "
                    "declared forbidden by the architecture policy."
                )
            },
            "id": FORBIDDEN_DEPENDENCY_RULE_ID,
            "name": "ForbiddenDependency",
            "shortDescription": {
                "text": "Forbidden architectural dependency",
            },
        },
        {
            "defaultConfiguration": {
                "level": "warning",
            },
            "fullDescription": {
                "text": (
                    "A fact limitation or incomplete layer "
                    "classification prevents a clean decision."
                )
            },
            "id": INCOMPLETE_EVIDENCE_RULE_ID,
            "name": "IncompleteArchitectureEvidence",
            "shortDescription": {
                "text": "Incomplete architecture evidence",
            },
        },
    ]


def _sarif_location(
    location: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "physicalLocation": {
            "artifactLocation": {
                "uri": str(location["file"]).replace(chr(92), "/"),
                "uriBaseId": "%SRCROOT%",
            },
            "region": {
                "startColumn": int(location["column"]),
                "startLine": int(location["line"]),
            },
        }
    }


def _unknown_fingerprint(
    payload: Mapping[str, Any],
) -> str:
    digest = hashlib.sha256(
        _compact_json(payload).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _endpoint_unknown(
    *,
    call_id: str,
    endpoint: str,
    layers: tuple[str, ...],
    symbol: FactSymbol,
    location: FactLocation,
) -> ArchitectureUnknown:
    if not layers:
        code = "unclassified_call_endpoint"
        message = (
            f"{endpoint} symbol {symbol.qualified_name!r} "
            "matches no architecture layer"
        )
    else:
        code = "ambiguous_call_endpoint"
        message = (
            f"{endpoint} symbol {symbol.qualified_name!r} "
            "matches multiple architecture layers: "
            f"{', '.join(layers)}"
        )
    return ArchitectureUnknown(
        code,
        message,
        location.to_dict(),
        {
            "call_id": call_id,
            "endpoint": endpoint,
            "layers": list(layers),
            "symbol": symbol.to_dict(),
        },
    )


def enforce_architecture(
    index: FactIndex,
    policy: ArchitecturePolicy,
) -> ArchitectureReport:
    """Apply one complete policy to exact direct-call facts."""

    symbols = {
        symbol.id: symbol
        for symbol in index.symbols
    }
    decisions: list[ArchitectureDecision] = []
    unknowns: list[ArchitectureUnknown] = []

    for limitation in index.limitations:
        unknowns.append(
            ArchitectureUnknown(
                "fact_index_limitation",
                (
                    f"fact-index limitation {limitation.code!r} "
                    "leaves the architecture graph incomplete: "
                    f"{limitation.message}"
                ),
                _location_dict(limitation.location),
                {
                    "limitation": limitation.to_dict(),
                },
            )
        )

    for call in index.calls:
        caller = symbols[call.caller]
        callee = symbols[call.callee]
        caller_layers = policy.classify(caller)
        callee_layers = policy.classify(callee)
        if len(caller_layers) != 1:
            unknowns.append(
                _endpoint_unknown(
                    call_id=call.id,
                    endpoint="caller",
                    layers=caller_layers,
                    symbol=caller,
                    location=call.location,
                )
            )
        if len(callee_layers) != 1:
            unknowns.append(
                _endpoint_unknown(
                    call_id=call.id,
                    endpoint="callee",
                    layers=callee_layers,
                    symbol=callee,
                    location=call.location,
                )
            )
        if len(caller_layers) != 1 or len(callee_layers) != 1:
            continue

        source_layer = caller_layers[0]
        target_layer = callee_layers[0]
        decisions.append(
            ArchitectureDecision(
                call.id,
                caller.to_dict(),
                callee.to_dict(),
                source_layer,
                target_layer,
                policy.decision(
                    source_layer,
                    target_layer,
                ),
                call.location.to_dict(),
            )
        )

    return ArchitectureReport(
        index.id,
        policy.id,
        len(index.calls),
        tuple(decisions),
        tuple(unknowns),
    )
