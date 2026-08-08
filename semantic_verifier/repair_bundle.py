"""Strict replay-attested repair bundle for one violated obligation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .backend import (
    CheckerBackend,
    CrossCheckBackend,
    Z3Checker,
)
from .checker import AffineChecker
from .model import (
    Contract,
    FrameContract,
    Obligation,
    SourceLocation,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
)
from .pipeline import VerificationPipeline


REPAIR_BUNDLE_SCHEMA = "codeskeptic.repair-bundle/v1"
REPAIR_BUNDLE_ID_SCHEMA = "codeskeptic.repair-bundle-identity/v1"
REFEREE_IDS = frozenset(
    {
        "codeskeptic.affine/v1",
        "codeskeptic.both/v1",
        "codeskeptic.z3/v1",
    }
)
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBLIGATION_PATTERN = re.compile(r"ob[0-9]{5,}\Z")


class RepairBundleError(ValueError):
    """Raised when repair evidence violates the E1.1 contract."""


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


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _content_id(kind: str, payload: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": REPAIR_BUNDLE_ID_SCHEMA,
        "value": payload,
    }
    return _sha256(_identity_bytes(envelope))


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RepairBundleError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_PATTERN.fullmatch(text) is None:
        raise RepairBundleError(
            f"{field} must be a lowercase sha256 identity"
        )
    return text


def _exact_keys(
    value: Mapping[str, Any],
    required: set[str],
    optional: set[str],
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required - optional)
    if missing:
        raise RepairBundleError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise RepairBundleError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


def _location(value: object, field: str) -> SourceLocation:
    if not isinstance(value, Mapping):
        raise RepairBundleError(f"{field} must be an object")
    _exact_keys(
        value,
        {"column", "file", "line"},
        set(),
        field,
    )
    line = value["line"]
    column = value["column"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise RepairBundleError(
            f"{field}.line must be a positive integer"
        )
    if (
        isinstance(column, bool)
        or not isinstance(column, int)
        or column < 1
    ):
        raise RepairBundleError(
            f"{field}.column must be a positive integer"
        )
    return SourceLocation(
        _require_text(value["file"], f"{field}.file"),
        line,
        column,
    )


def _validate_expr(value: object, field: str) -> None:
    if not isinstance(value, Mapping):
        raise RepairBundleError(f"{field} must be an object")
    _exact_keys(
        value,
        {"kind", "type"},
        {"args", "op", "value"},
        field,
    )
    _require_text(value["kind"], f"{field}.kind")
    _require_text(value["type"], f"{field}.type")
    if "op" in value:
        _require_text(value["op"], f"{field}.op")
    if "args" in value:
        arguments = value["args"]
        if not isinstance(arguments, list) or not arguments:
            raise RepairBundleError(
                f"{field}.args must be a non-empty array"
            )
        for index, argument in enumerate(arguments):
            _validate_expr(argument, f"{field}.args[{index}]")
    if "value" in value:
        raw = value["value"]
        if not isinstance(raw, (str, bool)):
            raise RepairBundleError(
                f"{field}.value must be canonical text or bool"
            )


def _validate_obligation(
    value: object,
    field: str = "bundle.obligation",
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RepairBundleError(f"{field} must be an object")
    _exact_keys(
        value,
        {
            "assumptions",
            "conclusion",
            "description",
            "function",
            "id",
            "kind",
            "location",
            "mode",
        },
        set(),
        field,
    )
    identity = _require_text(value["id"], f"{field}.id")
    if _OBLIGATION_PATTERN.fullmatch(identity) is None:
        raise RepairBundleError(
            f"{field}.id must match ob[0-9]{{5,}}"
        )
    _require_text(value["function"], f"{field}.function")
    _require_text(value["kind"], f"{field}.kind")
    _require_text(value["description"], f"{field}.description")
    if value["mode"] != "validity":
        raise RepairBundleError(
            "repair bundle requires a validity obligation"
        )
    _location(value["location"], f"{field}.location")
    assumptions = value["assumptions"]
    if not isinstance(assumptions, list):
        raise RepairBundleError(
            f"{field}.assumptions must be an array"
        )
    for index, assumption in enumerate(assumptions):
        _validate_expr(
            assumption,
            f"{field}.assumptions[{index}]",
        )
    _validate_expr(value["conclusion"], f"{field}.conclusion")
    return value


def _validate_evidence_value(value: object, field: str) -> None:
    if isinstance(value, (str, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_evidence_value(item, f"{field}[{index}]")
        return
    if isinstance(value, Mapping):
        for key in sorted(value):
            _require_text(key, f"{field}.key")
            _validate_evidence_value(
                value[key],
                f"{field}.{key}",
            )
        return
    raise RepairBundleError(
        f"{field} has unsupported counterexample value"
    )


def _validate_result(
    value: object,
    field: str = "bundle.result",
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RepairBundleError(f"{field} must be an object")
    _exact_keys(
        value,
        {
            "counterexample",
            "function",
            "kind",
            "location",
            "message",
            "obligation",
            "status",
        },
        {"trace"},
        field,
    )
    if value["status"] != "violated":
        raise RepairBundleError(
            "repair bundle requires a violated result"
        )
    for name in ("function", "kind", "message"):
        _require_text(value[name], f"{field}.{name}")
    obligation = _require_text(
        value["obligation"],
        f"{field}.obligation",
    )
    if _OBLIGATION_PATTERN.fullmatch(obligation) is None:
        raise RepairBundleError(
            f"{field}.obligation has invalid format"
        )
    _location(value["location"], f"{field}.location")
    counterexample = value["counterexample"]
    if not isinstance(counterexample, Mapping) or not counterexample:
        raise RepairBundleError(
            "violated result requires a concrete counterexample"
        )
    for key in sorted(counterexample):
        _require_text(key, f"{field}.counterexample key")
        _validate_evidence_value(
            counterexample[key],
            f"{field}.counterexample.{key}",
        )
    trace = value.get("trace")
    if trace is not None and not isinstance(trace, list):
        raise RepairBundleError(f"{field}.trace must be an array")
    return value


@dataclass(frozen=True, order=True, slots=True)
class SourceLine:
    number: int
    text: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.number, bool)
            or not isinstance(self.number, int)
            or self.number < 1
        ):
            raise RepairBundleError(
                "source line number must be positive"
            )
        if not isinstance(self.text, str) or "\x00" in self.text:
            raise RepairBundleError(
                "source line text must be text without NUL"
            )

    def to_dict(self) -> dict[str, object]:
        return {"number": self.number, "text": self.text}


@dataclass(frozen=True, slots=True)
class SourceSlice:
    start_line: int
    end_line: int
    lines: tuple[SourceLine, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_line, bool)
            or isinstance(self.end_line, bool)
            or not isinstance(self.start_line, int)
            or not isinstance(self.end_line, int)
            or self.start_line < 1
            or self.end_line < self.start_line
        ):
            raise RepairBundleError(
                "source slice bounds are invalid"
            )
        expected = tuple(
            range(self.start_line, self.end_line + 1)
        )
        if tuple(line.number for line in self.lines) != expected:
            raise RepairBundleError(
                "source slice lines must exactly cover its bounds"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "end_line": self.end_line,
            "lines": [line.to_dict() for line in self.lines],
            "start_line": self.start_line,
        }


@dataclass(frozen=True, order=True, slots=True)
class RelatedContract:
    kind: str
    text: str
    location: SourceLocation
    machine_proposed: bool

    def __post_init__(self) -> None:
        if self.kind not in {"ensures", "modifies", "requires"}:
            raise RepairBundleError(
                f"unsupported related contract kind {self.kind!r}"
            )
        _require_text(self.text, "contract.text")
        if not isinstance(self.machine_proposed, bool):
            raise RepairBundleError(
                "contract.machine_proposed must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "location": self.location.to_dict(),
            "machine_proposed": self.machine_proposed,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class RepairBundle:
    id: str
    source_file: str
    source_sha256: str
    verification_schema: str
    verification_sha256: str
    referee: str
    obligation: Mapping[str, Any]
    result: Mapping[str, Any]
    source_slice: SourceSlice
    contracts: tuple[RelatedContract, ...]

    def __post_init__(self) -> None:
        _require_text(self.source_file, "bundle.source.file")
        _require_hash(
            self.source_sha256,
            "bundle.source.sha256",
        )
        _require_text(
            self.verification_schema,
            "bundle.verification.schema",
        )
        _require_hash(
            self.verification_sha256,
            "bundle.verification.sha256",
        )
        if self.referee not in REFEREE_IDS:
            raise RepairBundleError(
                "bundle verification referee is unsupported"
            )
        obligation = dict(
            _validate_obligation(self.obligation)
        )
        result = dict(_validate_result(self.result))
        if result["obligation"] != obligation["id"]:
            raise RepairBundleError(
                "result does not reference bundled obligation"
            )
        for field in ("function", "kind"):
            if result[field] != obligation[field]:
                raise RepairBundleError(
                    f"result {field} does not match obligation"
                )
        obligation_location = _location(
            obligation["location"],
            "bundle.obligation.location",
        )
        result_location = _location(
            result["location"],
            "bundle.result.location",
        )
        if (
            obligation_location.file != self.source_file
            or result_location.file != self.source_file
        ):
            raise RepairBundleError(
                "bundle evidence must belong to source.file"
            )
        contracts = tuple(
            sorted(
                self.contracts,
                key=lambda item: (
                    item.location.line,
                    item.location.column,
                    item.kind,
                    item.text,
                ),
            )
        )
        if len(contracts) != len(set(contracts)):
            raise RepairBundleError(
                "bundle contracts must not contain duplicates"
            )
        if any(
            contract.location.file != self.source_file
            for contract in contracts
        ):
            raise RepairBundleError(
                "bundle contracts must belong to source.file"
            )
        object.__setattr__(self, "obligation", obligation)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "contracts", contracts)
        expected = _content_id("repair-bundle", self.content_dict())
        if _require_hash(self.id, "bundle.id") != expected:
            raise RepairBundleError(
                "bundle.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        source_file: str,
        source_sha256: str,
        verification_schema: str,
        verification_sha256: str,
        referee: str,
        obligation: Mapping[str, Any],
        result: Mapping[str, Any],
        source_slice: SourceSlice,
        contracts: Sequence[RelatedContract],
    ) -> "RepairBundle":
        ordered = tuple(
            sorted(
                contracts,
                key=lambda item: (
                    item.location.line,
                    item.location.column,
                    item.kind,
                    item.text,
                ),
            )
        )
        content = {
            "contracts": [
                contract.to_dict() for contract in ordered
            ],
            "obligation": dict(obligation),
            "referee": referee,
            "result": dict(result),
            "schema": REPAIR_BUNDLE_SCHEMA,
            "source": {
                "file": source_file,
                "sha256": source_sha256,
            },
            "source_slice": source_slice.to_dict(),
            "verification": {
                "schema": verification_schema,
                "sha256": verification_sha256,
            },
        }
        return cls(
            _content_id("repair-bundle", content),
            source_file,
            source_sha256,
            verification_schema,
            verification_sha256,
            referee,
            obligation,
            result,
            source_slice,
            ordered,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "contracts": [
                contract.to_dict()
                for contract in self.contracts
            ],
            "obligation": dict(self.obligation),
            "referee": self.referee,
            "result": dict(self.result),
            "schema": REPAIR_BUNDLE_SCHEMA,
            "source": {
                "file": self.source_file,
                "sha256": self.source_sha256,
            },
            "source_slice": self.source_slice.to_dict(),
            "verification": {
                "schema": self.verification_schema,
                "sha256": self.verification_sha256,
            },
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


class RepairBundleBuilder:
    """Reproduce and recheck one violated obligation before bundling it."""

    def __init__(
        self,
        clang: str | None = None,
        *,
        checker: CheckerBackend | None = None,
        referee: str = "codeskeptic.affine/v1",
        context_lines: int = 4,
    ) -> None:
        selected = checker or AffineChecker()
        expected = self._referee_for_checker(selected)
        if referee != expected:
            raise RepairBundleError(
                "referee ID does not match exact checker implementation"
            )
        if (
            isinstance(context_lines, bool)
            or not isinstance(context_lines, int)
            or not 0 <= context_lines <= 20
        ):
            raise RepairBundleError(
                "context_lines must be an integer from 0 to 20"
            )
        self.pipeline = VerificationPipeline(
            clang,
            checker=selected,
        )
        self.checker = selected
        self.referee = expected
        self.context_lines = context_lines

    @staticmethod
    def _referee_for_checker(checker: CheckerBackend) -> str:
        exact = {
            AffineChecker: "codeskeptic.affine/v1",
            Z3Checker: "codeskeptic.z3/v1",
            CrossCheckBackend: "codeskeptic.both/v1",
        }
        result = exact.get(type(checker))
        if result is None:
            raise RepairBundleError(
                "checker implementation is not an admitted bundle referee"
            )
        return result

    def build(
        self,
        source: str,
        display_path: str,
        report: VerificationReport,
        obligation_id: str,
    ) -> RepairBundle:
        if not isinstance(source, str):
            raise RepairBundleError("source must be UTF-8 text")
        source_bytes = source.encode("utf-8")
        reproduced = self.pipeline.verify_source(
            source,
            display_path,
        )
        if reproduced.to_json() != report.to_json():
            raise RepairBundleError(
                "source/report reproduction mismatch"
            )
        obligations = [
            obligation
            for obligation in report.obligations
            if obligation.id == obligation_id
        ]
        results = [
            result
            for result in report.results
            if result.obligation_id == obligation_id
        ]
        if len(obligations) != 1 or len(results) != 1:
            raise RepairBundleError(
                "target requires one obligation and one result"
            )
        obligation = obligations[0]
        result = results[0]
        if (
            obligation.mode != "validity"
            or obligation.conclusion is None
            or result.status != VerificationStatus.VIOLATED
            or not result.counterexample
        ):
            raise RepairBundleError(
                "target must be a violated validity obligation with counterexample"
            )
        replay = self.checker.check(obligation)
        if (
            replay.status != VerificationStatus.VIOLATED
            or not replay.counterexample
            or replay.to_dict() != result.to_dict()
        ):
            raise RepairBundleError(
                "independent obligation replay did not reproduce violation"
            )
        source_slice = self._source_slice(
            source,
            result.location,
        )
        contracts = self._contracts(report, obligation.function)
        return RepairBundle.create(
            source_file=display_path,
            source_sha256=_sha256(source_bytes),
            verification_schema=report.module.schema,
            verification_sha256=_sha256(
                report.to_json().encode("utf-8")
            ),
            referee=self.referee,
            obligation=obligation.to_dict(),
            result=result.to_dict(),
            source_slice=source_slice,
            contracts=contracts,
        )

    def _source_slice(
        self,
        source: str,
        location: SourceLocation,
    ) -> SourceSlice:
        lines = source.splitlines()
        if not lines:
            raise RepairBundleError("source must contain at least one line")
        if not 1 <= location.line <= len(lines):
            raise RepairBundleError(
                "result location is outside source text"
            )
        start = max(1, location.line - self.context_lines)
        end = min(
            len(lines),
            location.line + self.context_lines,
        )
        return SourceSlice(
            start,
            end,
            tuple(
                SourceLine(number, lines[number - 1])
                for number in range(start, end + 1)
            ),
        )

    @staticmethod
    def _contracts(
        report: VerificationReport,
        function_name: str,
    ) -> tuple[RelatedContract, ...]:
        functions = [
            function
            for function in report.module.functions
            if function.name == function_name
            and function.has_body
        ]
        if len(functions) != 1:
            raise RepairBundleError(
                "target function must have one exact IR definition"
            )
        function = functions[0]
        contracts = [
            RelatedContract(
                contract.kind,
                contract.text,
                contract.location,
                contract.machine_proposed,
            )
            for contract in function.contracts
        ]
        if function.frame is not None:
            frame: FrameContract = function.frame
            contracts.append(
                RelatedContract(
                    "modifies",
                    frame.text,
                    frame.location,
                    frame.machine_proposed,
                )
            )
        return tuple(contracts)


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RepairBundleError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RepairBundleError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def load_repair_bundle_json(
    text: str,
    *,
    source: str,
    report: VerificationReport,
) -> RepairBundle:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise RepairBundleError(
            f"invalid repair-bundle JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise RepairBundleError(
            "repair bundle must be a JSON object"
        )
    _exact_keys(
        payload,
        {
            "contracts",
            "id",
            "obligation",
            "referee",
            "result",
            "schema",
            "source",
            "source_slice",
            "verification",
        },
        set(),
        "bundle",
    )
    if payload["schema"] != REPAIR_BUNDLE_SCHEMA:
        raise RepairBundleError(
            "unsupported repair-bundle schema"
        )
    source_payload = payload["source"]
    verification = payload["verification"]
    if not isinstance(source_payload, Mapping):
        raise RepairBundleError("bundle.source must be an object")
    if not isinstance(verification, Mapping):
        raise RepairBundleError(
            "bundle.verification must be an object"
        )
    _exact_keys(
        source_payload,
        {"file", "sha256"},
        set(),
        "bundle.source",
    )
    _exact_keys(
        verification,
        {"schema", "sha256"},
        set(),
        "bundle.verification",
    )
    slice_payload = payload["source_slice"]
    if not isinstance(slice_payload, Mapping):
        raise RepairBundleError(
            "bundle.source_slice must be an object"
        )
    _exact_keys(
        slice_payload,
        {"end_line", "lines", "start_line"},
        set(),
        "bundle.source_slice",
    )
    raw_lines = slice_payload["lines"]
    if not isinstance(raw_lines, list):
        raise RepairBundleError(
            "bundle.source_slice.lines must be an array"
        )
    lines: list[SourceLine] = []
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, Mapping):
            raise RepairBundleError(
                f"bundle.source_slice.lines[{index}] must be an object"
            )
        _exact_keys(
            raw,
            {"number", "text"},
            set(),
            f"bundle.source_slice.lines[{index}]",
        )
        lines.append(SourceLine(raw["number"], raw["text"]))
    source_slice = SourceSlice(
        slice_payload["start_line"],
        slice_payload["end_line"],
        tuple(lines),
    )
    raw_contracts = payload["contracts"]
    if not isinstance(raw_contracts, list):
        raise RepairBundleError(
            "bundle.contracts must be an array"
        )
    contracts: list[RelatedContract] = []
    for index, raw in enumerate(raw_contracts):
        field = f"bundle.contracts[{index}]"
        if not isinstance(raw, Mapping):
            raise RepairBundleError(f"{field} must be an object")
        _exact_keys(
            raw,
            {"kind", "location", "machine_proposed", "text"},
            set(),
            field,
        )
        contracts.append(
            RelatedContract(
                raw["kind"],
                raw["text"],
                _location(raw["location"], f"{field}.location"),
                raw["machine_proposed"],
            )
        )
    bundle = RepairBundle(
        _require_hash(payload["id"], "bundle.id"),
        _require_text(
            source_payload["file"],
            "bundle.source.file",
        ),
        _require_hash(
            source_payload["sha256"],
            "bundle.source.sha256",
        ),
        _require_text(
            verification["schema"],
            "bundle.verification.schema",
        ),
        _require_hash(
            verification["sha256"],
            "bundle.verification.sha256",
        ),
        _require_text(payload["referee"], "bundle.referee"),
        payload["obligation"],
        payload["result"],
        source_slice,
        tuple(contracts),
    )
    source_bytes = source.encode("utf-8")
    if bundle.source_sha256 != _sha256(source_bytes):
        raise RepairBundleError(
            "bundle source hash does not match supplied source"
        )
    if bundle.source_file != report.module.source:
        raise RepairBundleError(
            "bundle source file does not match report"
        )
    if (
        bundle.verification_schema != report.module.schema
        or bundle.verification_sha256
        != _sha256(report.to_json().encode("utf-8"))
    ):
        raise RepairBundleError(
            "bundle verification does not match supplied report"
        )
    obligations = [
        obligation
        for obligation in report.obligations
        if obligation.id == bundle.obligation["id"]
    ]
    results = [
        result
        for result in report.results
        if result.obligation_id == bundle.result["obligation"]
    ]
    if (
        len(obligations) != 1
        or len(results) != 1
        or obligations[0].to_dict() != bundle.obligation
        or results[0].to_dict() != bundle.result
    ):
        raise RepairBundleError(
            "bundle obligation/result does not match report"
        )
    expected_lines = source.splitlines()
    for line in bundle.source_slice.lines:
        if (
            line.number > len(expected_lines)
            or expected_lines[line.number - 1] != line.text
        ):
            raise RepairBundleError(
                "bundle source slice does not match source"
            )
    return bundle
