"""Strict immutable trust overlay for D1 purity facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .facts import (
    FACT_SCHEMA,
    PURITY_STATUSES,
    FactIndex,
    FactLocation,
)
from .model import SCHEMA as VERIFICATION_SCHEMA


FACT_TRUST_SCHEMA = "codeskeptic.fact-trust/v1"
FACT_TRUST_ID_SCHEMA = "codeskeptic.fact-trust-identity/v1"
PROOF_METHOD = "empty-frame-full-vc/v1"
TRUST_LABELS = frozenset({"derived", "proved"})
REFEREE_IDS = frozenset(
    {
        "codeskeptic.affine/v1",
        "codeskeptic.both/v1",
        "codeskeptic.z3/v1",
    }
)

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBLIGATION_PATTERN = re.compile(r"ob[0-9]{5,}\Z")


class FactTrustError(ValueError):
    """Raised when a fact-trust overlay violates the v1 contract."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _identity_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, payload: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": FACT_TRUST_ID_SCHEMA,
        "value": payload,
    }
    return "sha256:" + hashlib.sha256(
        _identity_bytes(envelope)
    ).hexdigest()


def verification_sha256(data: bytes) -> str:
    """Return the canonical evidence hash shape used by proof records."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise FactTrustError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_PATTERN.fullmatch(text) is None:
        raise FactTrustError(
            f"{field} must be a lowercase sha256 identity"
        )
    return text


def _require_choice(
    value: object,
    choices: frozenset[str],
    field: str,
) -> str:
    text = _require_text(value, field)
    if text not in choices:
        raise FactTrustError(
            f"{field} has unsupported value {text!r}"
        )
    return text


def _require_exact_keys(
    payload: Mapping[str, Any],
    required: frozenset[str],
    field: str,
) -> None:
    keys = set(payload)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise FactTrustError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise FactTrustError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class ProofEvidence:
    source_sha256: str
    verification_sha256: str
    verification_schema: str
    referee: str
    obligations: tuple[str, ...]
    frame: FactLocation
    callees: tuple[str, ...] = ()
    method: str = PROOF_METHOD

    def __post_init__(self) -> None:
        _require_hash(self.source_sha256, "evidence.source_sha256")
        _require_hash(
            self.verification_sha256,
            "evidence.verification_sha256",
        )
        if self.verification_schema != VERIFICATION_SCHEMA:
            raise FactTrustError(
                "evidence.verification_schema is unsupported"
            )
        _require_choice(
            self.referee,
            REFEREE_IDS,
            "evidence.referee",
        )
        if self.method != PROOF_METHOD:
            raise FactTrustError("evidence.method is unsupported")
        if not isinstance(self.frame, FactLocation):
            raise FactTrustError(
                "evidence.frame must be a FactLocation"
            )
        obligations = tuple(sorted(self.obligations))
        if not obligations:
            raise FactTrustError(
                "proved evidence requires at least one obligation"
            )
        if len(obligations) != len(set(obligations)):
            raise FactTrustError(
                "evidence.obligations must not contain duplicates"
            )
        for obligation in obligations:
            if (
                not isinstance(obligation, str)
                or _OBLIGATION_PATTERN.fullmatch(obligation) is None
            ):
                raise FactTrustError(
                    "evidence obligation IDs must match ob[0-9]{5,}"
                )
        callees = tuple(sorted(self.callees))
        if len(callees) != len(set(callees)):
            raise FactTrustError(
                "evidence.callees must not contain duplicates"
            )
        for callee in callees:
            _require_hash(callee, "evidence.callee")
        object.__setattr__(self, "obligations", obligations)
        object.__setattr__(self, "callees", callees)

    def to_dict(self) -> dict[str, object]:
        return {
            "callees": list(self.callees),
            "frame": self.frame.to_dict(),
            "method": self.method,
            "obligations": list(self.obligations),
            "referee": self.referee,
            "source_sha256": self.source_sha256,
            "verification_schema": self.verification_schema,
            "verification_sha256": self.verification_sha256,
        }


@dataclass(frozen=True, slots=True)
class FactTrustClaim:
    id: str
    function: str
    value: str
    trust: str
    evidence: ProofEvidence | None = None

    def __post_init__(self) -> None:
        _require_hash(self.function, "claim.function")
        _require_choice(
            self.value,
            PURITY_STATUSES,
            "claim.value",
        )
        _require_choice(
            self.trust,
            TRUST_LABELS,
            "claim.trust",
        )
        if (
            self.evidence is not None
            and not isinstance(self.evidence, ProofEvidence)
        ):
            raise FactTrustError(
                "claim.evidence must be ProofEvidence or null"
            )
        if self.trust == "derived":
            if self.evidence is not None:
                raise FactTrustError(
                    "derived claims must not carry proof evidence"
                )
        else:
            if self.value != "pure":
                raise FactTrustError(
                    "only pure claims can carry proved trust"
                )
            if self.evidence is None:
                raise FactTrustError(
                    "proved pure claims require proof evidence"
                )
            if self.function in self.evidence.callees:
                raise FactTrustError(
                    "proved evidence cannot depend on its own claim"
                )
        expected = _content_id("fact-trust-claim", self.content_dict())
        if _require_hash(self.id, "claim.id") != expected:
            raise FactTrustError(
                "claim.id does not match canonical claim content"
            )

    @classmethod
    def create(
        cls,
        *,
        function: str,
        value: str,
        trust: str = "derived",
        evidence: ProofEvidence | None = None,
    ) -> "FactTrustClaim":
        content: dict[str, object] = {
            "evidence": (
                evidence.to_dict()
                if evidence is not None
                else None
            ),
            "function": function,
            "trust": trust,
            "value": value,
        }
        return cls(
            _content_id("fact-trust-claim", content),
            function,
            value,
            trust,
            evidence,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "evidence": (
                self.evidence.to_dict()
                if self.evidence is not None
                else None
            ),
            "function": self.function,
            "trust": self.trust,
            "value": self.value,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}


@dataclass(frozen=True, slots=True)
class FactTrustIndex:
    id: str
    fact_index: str
    source_sha256: str
    claims: tuple[FactTrustClaim, ...]

    def __post_init__(self) -> None:
        _require_hash(self.fact_index, "trust.fact_index")
        _require_hash(self.source_sha256, "trust.source_sha256")
        if any(
            not isinstance(claim, FactTrustClaim)
            for claim in self.claims
        ):
            raise FactTrustError(
                "trust.claims must contain FactTrustClaim values"
            )
        ordered = tuple(
            sorted(self.claims, key=lambda claim: claim.function)
        )
        functions = [claim.function for claim in ordered]
        identities = [claim.id for claim in ordered]
        if len(functions) != len(set(functions)):
            raise FactTrustError(
                "trust claims must not duplicate functions"
            )
        if len(identities) != len(set(identities)):
            raise FactTrustError(
                "trust claims must not duplicate identities"
            )
        object.__setattr__(self, "claims", ordered)
        expected = _content_id("fact-trust-index", self.content_dict())
        if _require_hash(self.id, "trust.id") != expected:
            raise FactTrustError(
                "trust.id does not match canonical trust content"
            )

    @classmethod
    def create(
        cls,
        fact_index: FactIndex,
        claims: Sequence[FactTrustClaim],
    ) -> "FactTrustIndex":
        ordered = tuple(
            sorted(claims, key=lambda claim: claim.function)
        )
        content: dict[str, object] = {
            "claims": [claim.to_dict() for claim in ordered],
            "fact_index": fact_index.id,
            "schema": FACT_TRUST_SCHEMA,
            "source_sha256": fact_index.source.content_sha256,
        }
        result = cls(
            _content_id("fact-trust-index", content),
            fact_index.id,
            fact_index.source.content_sha256,
            ordered,
        )
        result.validate_against(fact_index)
        return result

    @classmethod
    def derived(cls, fact_index: FactIndex) -> "FactTrustIndex":
        return cls.create(
            fact_index,
            tuple(
                FactTrustClaim.create(
                    function=row.function,
                    value=row.status,
                )
                for row in fact_index.purity
            ),
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "claims": [claim.to_dict() for claim in self.claims],
            "fact_index": self.fact_index,
            "schema": FACT_TRUST_SCHEMA,
            "source_sha256": self.source_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def validate_against(self, fact_index: FactIndex) -> None:
        if self.fact_index != fact_index.id:
            raise FactTrustError(
                "trust overlay names a different fact index"
            )
        if self.source_sha256 != fact_index.source.content_sha256:
            raise FactTrustError(
                "trust overlay source hash does not match fact index"
            )
        rows = {row.function: row for row in fact_index.purity}
        claims = {claim.function: claim for claim in self.claims}
        missing = sorted(set(rows) - set(claims))
        dangling = sorted(set(claims) - set(rows))
        if missing:
            raise FactTrustError(
                "trust overlay is missing purity claims: "
                + ", ".join(missing)
            )
        if dangling:
            raise FactTrustError(
                "trust overlay has dangling purity claims: "
                + ", ".join(dangling)
            )
        for function, row in rows.items():
            claim = claims[function]
            if claim.value != row.status:
                raise FactTrustError(
                    f"claim value does not match D1 purity for {function}"
                )
            if claim.evidence is not None:
                if (
                    claim.evidence.source_sha256
                    != fact_index.source.content_sha256
                ):
                    raise FactTrustError(
                        "proof evidence source hash does not match D1"
                    )
                if claim.evidence.frame.file != fact_index.source.file:
                    raise FactTrustError(
                        "proof frame location must belong to D1 source"
                    )

        direct_callees: dict[str, set[str]] = {
            function: set() for function in rows
        }
        for call in fact_index.calls:
            if call.caller in direct_callees:
                direct_callees[call.caller].add(call.callee)
        for claim in self.claims:
            if claim.trust != "proved":
                continue
            assert claim.evidence is not None
            expected = tuple(sorted(direct_callees[claim.function]))
            if claim.evidence.callees != expected:
                raise FactTrustError(
                    "proof evidence must name every exact direct callee"
                )
            for callee in expected:
                dependency = claims.get(callee)
                if dependency is None or dependency.trust != "proved":
                    raise FactTrustError(
                        "proved claims require proved direct callees"
                    )
        self._reject_proof_cycles()

    def _reject_proof_cycles(self) -> None:
        graph = {
            claim.function: set(
                claim.evidence.callees
                if claim.evidence is not None
                else ()
            )
            for claim in self.claims
            if claim.trust == "proved"
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(function: str) -> None:
            if function in visiting:
                raise FactTrustError(
                    "proved claim dependencies must be acyclic"
                )
            if function in visited:
                return
            visiting.add(function)
            for callee in sorted(graph.get(function, set())):
                if callee in graph:
                    visit(callee)
            visiting.remove(function)
            visited.add(function)

        for function in sorted(graph):
            visit(function)


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FactTrustError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FactTrustError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def _strict_json(text: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise FactTrustError(
            f"invalid fact-trust JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise FactTrustError(
            "fact-trust document must be a JSON object"
        )
    return payload


def _location(value: object, field: str) -> FactLocation:
    if not isinstance(value, Mapping):
        raise FactTrustError(f"{field} must be an object")
    _require_exact_keys(
        value,
        frozenset({"column", "file", "line"}),
        field,
    )
    line = value["line"]
    column = value["column"]
    if isinstance(line, bool) or not isinstance(line, int):
        raise FactTrustError(f"{field}.line must be an integer")
    if isinstance(column, bool) or not isinstance(column, int):
        raise FactTrustError(
            f"{field}.column must be an integer"
        )
    try:
        return FactLocation(
            _require_text(value["file"], f"{field}.file"),
            line,
            column,
        )
    except ValueError as error:
        raise FactTrustError(str(error)) from error


def _evidence(value: object, field: str) -> ProofEvidence:
    if not isinstance(value, Mapping):
        raise FactTrustError(f"{field} must be an object")
    _require_exact_keys(
        value,
        frozenset(
            {
                "callees",
                "frame",
                "method",
                "obligations",
                "referee",
                "source_sha256",
                "verification_schema",
                "verification_sha256",
            }
        ),
        field,
    )
    obligations = value["obligations"]
    callees = value["callees"]
    if not isinstance(obligations, list):
        raise FactTrustError(
            f"{field}.obligations must be an array"
        )
    if not isinstance(callees, list):
        raise FactTrustError(f"{field}.callees must be an array")
    return ProofEvidence(
        _require_hash(
            value["source_sha256"],
            f"{field}.source_sha256",
        ),
        _require_hash(
            value["verification_sha256"],
            f"{field}.verification_sha256",
        ),
        _require_text(
            value["verification_schema"],
            f"{field}.verification_schema",
        ),
        _require_text(value["referee"], f"{field}.referee"),
        tuple(
            _require_text(
                obligation,
                f"{field}.obligations[{index}]",
            )
            for index, obligation in enumerate(obligations)
        ),
        _location(value["frame"], f"{field}.frame"),
        tuple(
            _require_hash(
                callee,
                f"{field}.callees[{index}]",
            )
            for index, callee in enumerate(callees)
        ),
        _require_text(value["method"], f"{field}.method"),
    )


def load_fact_trust_json(
    text: str,
    fact_index: FactIndex,
) -> FactTrustIndex:
    """Load canonical trust JSON and cross-validate every D1 purity claim."""

    payload = _strict_json(text)
    _require_exact_keys(
        payload,
        frozenset(
            {
                "claims",
                "fact_index",
                "id",
                "schema",
                "source_sha256",
            }
        ),
        "trust",
    )
    if payload["schema"] != FACT_TRUST_SCHEMA:
        raise FactTrustError("unsupported fact-trust schema")
    raw_claims = payload["claims"]
    if not isinstance(raw_claims, list):
        raise FactTrustError("trust.claims must be an array")
    claims: list[FactTrustClaim] = []
    required = frozenset(
        {"evidence", "function", "id", "trust", "value"}
    )
    for index, raw in enumerate(raw_claims):
        field = f"trust.claims[{index}]"
        if not isinstance(raw, Mapping):
            raise FactTrustError(f"{field} must be an object")
        _require_exact_keys(raw, required, field)
        raw_evidence = raw["evidence"]
        claims.append(
            FactTrustClaim(
                _require_hash(raw["id"], f"{field}.id"),
                _require_hash(
                    raw["function"],
                    f"{field}.function",
                ),
                _require_text(raw["value"], f"{field}.value"),
                _require_text(raw["trust"], f"{field}.trust"),
                (
                    _evidence(raw_evidence, f"{field}.evidence")
                    if raw_evidence is not None
                    else None
                ),
            )
        )
    result = FactTrustIndex(
        _require_hash(payload["id"], "trust.id"),
        _require_hash(
            payload["fact_index"],
            "trust.fact_index",
        ),
        _require_hash(
            payload["source_sha256"],
            "trust.source_sha256",
        ),
        tuple(claims),
    )
    result.validate_against(fact_index)
    return result


def read_fact_trust(
    path: str,
    fact_index: FactIndex,
) -> FactTrustIndex:
    try:
        with open(path, "rb") as stream:
            text = stream.read().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise FactTrustError(
            f"cannot read fact-trust document: {error}"
        ) from error
    return load_fact_trust_json(text, fact_index)
