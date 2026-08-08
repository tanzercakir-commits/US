"""Append-only benchmark run evidence with isolated operational timing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

from .benchmark_corpus import (
    CASE_COUNT,
    STATUSES,
    BenchmarkCorpus,
    BenchmarkCorpusCheck,
    BenchmarkCorpusError,
    BenchmarkStatus,
    observe_benchmark_corpus,
)


BENCHMARK_RUN_SCHEMA = "codeskeptic.benchmark-run/v1"
BENCHMARK_SUMMARY_SCHEMA = "codeskeptic.benchmark-run-summary/v1"
BENCHMARK_RUN_IDENTITY_SCHEMA = "codeskeptic.benchmark-run-identity/v1"
REFERENCE_CONFIGURATION = {
    "checker": "codeskeptic.affine/v1",
    "execution": "combined-translation-unit/v1",
    "frontend": "clang-json/20.1.8",
    "timing": "informational-monotonic-nanoseconds",
}
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")
_OBSERVATION_RE = re.compile(
    r"(?:f1-calibration-[0-9]{3}|A[0-9]+(?:\.[0-9]+)?-[a-z0-9][a-z0-9-]*)\Z"
)


class BenchmarkResultError(ValueError):
    """Raised when run evidence or an append-only ledger fails closed."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _canonical_line(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": BENCHMARK_RUN_IDENTITY_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


CONFIGURATION_SHA256 = _content_id(
    "benchmark-configuration", REFERENCE_CONFIGURATION
)


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise BenchmarkResultError(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _require_int(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BenchmarkResultError(
            f"{field_name} must be an integer >= {minimum}"
        )
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], field_name: str
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise BenchmarkResultError(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise BenchmarkResultError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _fraction(numerator: int, denominator: int) -> dict[str, int]:
    value = Fraction(numerator, denominator)
    return {
        "denominator": value.denominator,
        "numerator": value.numerator,
    }


def _rates(counts: Mapping[str, int]) -> dict[str, dict[str, int]]:
    return {status: _fraction(counts[status], CASE_COUNT) for status in STATUSES}


def _logic_content(
    *, corpus: str, cases: Sequence[BenchmarkStatus]
) -> dict[str, object]:
    raw = Counter(item.status for item in cases)
    counts = {status: raw.get(status, 0) for status in STATUSES}
    return {
        "cases": [item.to_dict() for item in cases],
        "configuration": REFERENCE_CONFIGURATION,
        "configuration_sha256": CONFIGURATION_SHA256,
        "corpus": corpus,
        "counts": counts,
        "rates": _rates(counts),
    }


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    id: str
    logic_sha256: str
    observation: str
    recorded_on: str
    source_revision: str
    corpus: str
    duration_ns: int
    cases: tuple[BenchmarkStatus, ...]

    def __post_init__(self) -> None:
        _require_hash(self.corpus, "benchmark run corpus")
        _require_hash(self.logic_sha256, "benchmark run logic hash")
        if not isinstance(self.observation, str) or _OBSERVATION_RE.fullmatch(self.observation) is None:
            raise BenchmarkResultError("benchmark observation label is unsupported")
        if not isinstance(self.source_revision, str) or _REVISION_RE.fullmatch(self.source_revision) is None:
            raise BenchmarkResultError("benchmark source revision must be forty lowercase hex digits")
        if not isinstance(self.recorded_on, str):
            raise BenchmarkResultError("benchmark recorded_on must be an ISO date")
        try:
            parsed_date = date.fromisoformat(self.recorded_on)
        except ValueError as error:
            raise BenchmarkResultError("benchmark recorded_on must be an ISO date") from error
        if parsed_date.isoformat() != self.recorded_on:
            raise BenchmarkResultError("benchmark recorded_on is not canonical")
        _require_int(self.duration_ns, "benchmark duration_ns")
        cases = tuple(self.cases)
        if len(cases) != CASE_COUNT or cases != tuple(
            sorted(cases, key=lambda item: item.function)
        ):
            raise BenchmarkResultError("benchmark run cases are incomplete or unsorted")
        if len({item.function for item in cases}) != CASE_COUNT:
            raise BenchmarkResultError("benchmark run functions duplicate")
        object.__setattr__(self, "cases", cases)
        logic = _logic_content(corpus=self.corpus, cases=cases)
        if self.logic_sha256 != _content_id("benchmark-logic", logic):
            raise BenchmarkResultError("benchmark run logic identity is stale")
        expected_id = _content_id("benchmark-run", self.content_dict())
        if _require_hash(self.id, "benchmark run id") != expected_id:
            raise BenchmarkResultError("benchmark run identity is stale")

    @classmethod
    def create(
        cls,
        *,
        observation: str,
        recorded_on: str,
        source_revision: str,
        corpus: str,
        duration_ns: int,
        cases: Sequence[BenchmarkStatus],
    ) -> "BenchmarkRun":
        case_tuple = tuple(cases)
        logic = _logic_content(corpus=corpus, cases=case_tuple)
        logic_hash = _content_id("benchmark-logic", logic)
        content = {
            **logic,
            "duration_ns": duration_ns,
            "logic_sha256": logic_hash,
            "observation": observation,
            "recorded_on": recorded_on,
            "schema": BENCHMARK_RUN_SCHEMA,
            "source_revision": source_revision,
        }
        return cls(
            _content_id("benchmark-run", content),
            logic_hash,
            observation,
            recorded_on,
            source_revision,
            corpus,
            duration_ns,
            case_tuple,
        )

    @property
    def counts(self) -> dict[str, int]:
        return _logic_content(corpus=self.corpus, cases=self.cases)["counts"]

    @property
    def rates(self) -> dict[str, dict[str, int]]:
        return _logic_content(corpus=self.corpus, cases=self.cases)["rates"]

    def content_dict(self) -> dict[str, object]:
        return {
            **_logic_content(corpus=self.corpus, cases=self.cases),
            "duration_ns": self.duration_ns,
            "logic_sha256": self.logic_sha256,
            "observation": self.observation,
            "recorded_on": self.recorded_on,
            "schema": BENCHMARK_RUN_SCHEMA,
            "source_revision": self.source_revision,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json_line(self) -> str:
        return _canonical_line(self.to_dict())


def capture_benchmark_run(
    corpus: BenchmarkCorpus,
    *,
    observation: str,
    recorded_on: str,
    source_revision: str,
    timer_ns: Callable[[], int] = time.perf_counter_ns,
    observe: Callable[[BenchmarkCorpus], BenchmarkCorpusCheck] = observe_benchmark_corpus,
) -> BenchmarkRun:
    before = timer_ns()
    if isinstance(before, bool) or not isinstance(before, int):
        raise BenchmarkResultError("benchmark timer must return integer nanoseconds")
    checked = observe(corpus)
    after = timer_ns()
    if isinstance(after, bool) or not isinstance(after, int) or after < before:
        raise BenchmarkResultError("benchmark monotonic timer moved backwards")
    if checked.corpus != corpus.id:
        raise BenchmarkResultError("benchmark observation corpus link is stale")
    return BenchmarkRun.create(
        observation=observation,
        recorded_on=recorded_on,
        source_revision=source_revision,
        corpus=corpus.id,
        duration_ns=after - before,
        cases=checked.cases,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkResultError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BenchmarkResultError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def _parse_line(text: str, index: int) -> Mapping[str, Any]:
    if "\r" in text or "\x00" in text or text.startswith("\ufeff"):
        raise BenchmarkResultError("benchmark ledger must be BOM-free LF-only UTF-8")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise BenchmarkResultError(
            f"invalid benchmark ledger row {index}: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise BenchmarkResultError(f"benchmark ledger row {index} must be an object")
    return value


def _parse_fraction(value: object, field_name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise BenchmarkResultError(f"{field_name} must be an object")
    _exact_keys(value, {"denominator", "numerator"}, field_name)
    numerator = _require_int(value["numerator"], f"{field_name}.numerator")
    denominator = _require_int(
        value["denominator"], f"{field_name}.denominator", minimum=1
    )
    expected = _fraction(numerator, denominator)
    if dict(value) != expected:
        raise BenchmarkResultError(f"{field_name} must be a reduced fraction")
    return expected


def load_benchmark_run_json_line(text: str) -> BenchmarkRun:
    payload = _parse_line(text.rstrip("\n"), 1)
    expected_fields = {
        "cases",
        "configuration",
        "configuration_sha256",
        "corpus",
        "counts",
        "duration_ns",
        "id",
        "logic_sha256",
        "observation",
        "rates",
        "recorded_on",
        "schema",
        "source_revision",
    }
    _exact_keys(payload, expected_fields, "benchmark run")
    if payload["schema"] != BENCHMARK_RUN_SCHEMA:
        raise BenchmarkResultError("benchmark run schema is unsupported")
    if payload["configuration"] != REFERENCE_CONFIGURATION:
        raise BenchmarkResultError("benchmark run configuration is unsupported")
    if payload["configuration_sha256"] != CONFIGURATION_SHA256:
        raise BenchmarkResultError("benchmark run configuration identity is stale")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise BenchmarkResultError("benchmark run cases must be an array")
    cases: list[BenchmarkStatus] = []
    for index, raw in enumerate(raw_cases):
        field_name = f"benchmark run cases[{index}]"
        if not isinstance(raw, Mapping):
            raise BenchmarkResultError(f"{field_name} must be an object")
        _exact_keys(raw, {"function", "status"}, field_name)
        try:
            cases.append(BenchmarkStatus(raw["function"], raw["status"]))
        except BenchmarkCorpusError as error:
            raise BenchmarkResultError(f"invalid {field_name}: {error}") from error
    run = BenchmarkRun.create(
        observation=payload["observation"],
        recorded_on=payload["recorded_on"],
        source_revision=payload["source_revision"],
        corpus=payload["corpus"],
        duration_ns=payload["duration_ns"],
        cases=cases,
    )
    if payload["id"] != run.id or payload["logic_sha256"] != run.logic_sha256:
        raise BenchmarkResultError("benchmark run identity is stale")
    if not isinstance(payload["counts"], Mapping) or set(payload["counts"]) != set(STATUSES):
        raise BenchmarkResultError("benchmark run counts are incomplete")
    for status in STATUSES:
        _require_int(payload["counts"][status], f"benchmark count {status}")
    if dict(payload["counts"]) != run.counts:
        raise BenchmarkResultError("benchmark run counts are stale")
    if not isinstance(payload["rates"], Mapping) or set(payload["rates"]) != set(STATUSES):
        raise BenchmarkResultError("benchmark run rates are incomplete")
    for status in STATUSES:
        _parse_fraction(payload["rates"][status], f"benchmark rate {status}")
    if dict(payload["rates"]) != run.rates:
        raise BenchmarkResultError("benchmark run rates are stale")
    if run.to_json_line() != text:
        raise BenchmarkResultError("benchmark run JSON line is not canonical")
    return run


def load_benchmark_run_ledger(text: str) -> tuple[BenchmarkRun, ...]:
    if text.startswith("\ufeff") or "\r" in text or "\x00" in text:
        raise BenchmarkResultError("benchmark ledger must be BOM-free LF-only UTF-8")
    if text and not text.endswith("\n"):
        raise BenchmarkResultError("benchmark ledger must end with LF")
    lines = text.splitlines(keepends=True)
    if any(line == "\n" for line in lines):
        raise BenchmarkResultError("benchmark ledger must not contain blank rows")
    runs = tuple(load_benchmark_run_json_line(line) for line in lines)
    identities = [run.id for run in runs]
    observations = [run.observation for run in runs]
    if len(identities) != len(set(identities)):
        raise BenchmarkResultError("benchmark ledger run identities duplicate")
    if len(observations) != len(set(observations)):
        raise BenchmarkResultError("benchmark ledger observation labels duplicate")
    if len({run.corpus for run in runs}) > 1:
        raise BenchmarkResultError("benchmark ledger mixes corpus identities")
    return runs


def append_benchmark_run(path: str | Path, run: BenchmarkRun) -> None:
    ledger_path = Path(path)
    try:
        prior_bytes = ledger_path.read_bytes() if ledger_path.exists() else b""
        prior_text = prior_bytes.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise BenchmarkResultError(f"cannot read benchmark ledger: {error}") from error
    prior = load_benchmark_run_ledger(prior_text)
    if any(item.id == run.id for item in prior):
        raise BenchmarkResultError("benchmark run identity already exists")
    if any(item.observation == run.observation for item in prior):
        raise BenchmarkResultError("benchmark observation label already exists")
    if prior and prior[0].corpus != run.corpus:
        raise BenchmarkResultError("benchmark run corpus differs from ledger")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ledger_path.open("ab") as stream:
            stream.write(run.to_json_line().encode("utf-8"))
        if not ledger_path.read_bytes().startswith(prior_bytes):
            raise BenchmarkResultError("benchmark append did not preserve prior bytes")
    except OSError as error:
        raise BenchmarkResultError(f"cannot append benchmark ledger: {error}") from error


def summarize_benchmark_runs(runs: Sequence[BenchmarkRun]) -> dict[str, object]:
    rows = tuple(runs)
    return {
        "corpus": rows[0].corpus if rows else None,
        "logical_points": [
            {
                "counts": run.counts,
                "logic_sha256": run.logic_sha256,
                "observation": run.observation,
                "rates": run.rates,
                "source_revision": run.source_revision,
            }
            for run in rows
        ],
        "run_count": len(rows),
        "schema": BENCHMARK_SUMMARY_SCHEMA,
        "timing_ns": [
            {"duration_ns": run.duration_ns, "observation": run.observation}
            for run in rows
        ],
    }


def summary_json(runs: Sequence[BenchmarkRun]) -> str:
    return _canonical_json(summarize_benchmark_runs(runs))
