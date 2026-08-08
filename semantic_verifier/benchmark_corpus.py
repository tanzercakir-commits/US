"""Strict curated benchmark corpus and deterministic status observation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .checker import AffineChecker
from .model import VerificationStatus
from .pipeline import VerificationPipeline


BENCHMARK_CORPUS_SCHEMA = "codeskeptic.benchmark-corpus/v1"
BENCHMARK_CHECK_SCHEMA = "codeskeptic.benchmark-corpus-check/v1"
BENCHMARK_IDENTITY_SCHEMA = "codeskeptic.benchmark-corpus-identity/v1"
CASE_COUNT = 40
TIER_COUNT = 4
EXPECTED_COUNTS = {
    "unknown": 10,
    "unsupported": 0,
    "verified": 20,
    "violated": 10,
}
STATUSES = tuple(sorted(EXPECTED_COUNTS))
TIERS = (
    "affine-basic",
    "affine-counterexample",
    "deterministic-search-frontier",
    "path-sensitive",
)
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FUNCTION_RE = re.compile(
    r"bench_(affine_basic|affine_counterexample|path_sensitive|search_frontier)_(0[1-9]|10)\Z"
)


class BenchmarkCorpusError(ValueError):
    """Raised when corpus structure or semantic evidence fails closed."""


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


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_text(value: str) -> str:
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as error:
        raise BenchmarkCorpusError("benchmark text must be UTF-8") from error
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _content_id(value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": "benchmark-corpus",
        "schema": BENCHMARK_IDENTITY_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BenchmarkCorpusError(f"{field_name} must be non-empty text")
    return value


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise BenchmarkCorpusError(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _require_int(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BenchmarkCorpusError(
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
        raise BenchmarkCorpusError(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise BenchmarkCorpusError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkCorpusError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BenchmarkCorpusError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def _parse_json(text: str, field_name: str) -> Mapping[str, Any]:
    if text.startswith("\ufeff") or "\x00" in text or "\r" in text:
        raise BenchmarkCorpusError(
            f"{field_name} must be BOM-free LF-only UTF-8"
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise BenchmarkCorpusError(
            f"invalid {field_name} JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise BenchmarkCorpusError(f"{field_name} must be an object")
    return value


def _read_utf8(path: Path, field_name: str) -> str:
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise BenchmarkCorpusError(f"cannot read {field_name}: {error}") from error
    if text.startswith("\ufeff") or "\x00" in text or "\r" in text:
        raise BenchmarkCorpusError(
            f"{field_name} must be BOM-free LF-only UTF-8"
        )
    return text


@dataclass(frozen=True, order=True, slots=True)
class BenchmarkTier:
    name: str
    expected_status: str
    count: int

    def __post_init__(self) -> None:
        if self.name not in TIERS:
            raise BenchmarkCorpusError("benchmark tier is unsupported")
        if self.expected_status not in STATUSES:
            raise BenchmarkCorpusError("benchmark tier status is unsupported")
        if _require_int(self.count, "benchmark tier count", minimum=1) != 10:
            raise BenchmarkCorpusError("each benchmark tier must have ten cases")

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "expected_status": self.expected_status,
            "name": self.name,
        }


@dataclass(frozen=True, order=True, slots=True)
class BenchmarkCase:
    function: str
    tier: str
    expected_status: str

    def __post_init__(self) -> None:
        if not isinstance(self.function, str) or _FUNCTION_RE.fullmatch(self.function) is None:
            raise BenchmarkCorpusError("benchmark function name is unsupported")
        if self.tier not in TIERS:
            raise BenchmarkCorpusError("benchmark case tier is unsupported")
        if self.expected_status not in STATUSES:
            raise BenchmarkCorpusError("benchmark expected status is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {
            "expected_status": self.expected_status,
            "function": self.function,
            "tier": self.tier,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCorpus:
    id: str
    source: str
    source_sha256: str
    tiers: tuple[BenchmarkTier, ...]
    cases: tuple[BenchmarkCase, ...]
    source_text: str = field(repr=False, compare=False)
    root: Path = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.source != "corpus.cpp":
            raise BenchmarkCorpusError("benchmark source path is unsupported")
        _require_hash(self.source_sha256, "benchmark source hash")
        tiers = tuple(self.tiers)
        cases = tuple(self.cases)
        if tuple(item.name for item in tiers) != TIERS:
            raise BenchmarkCorpusError("benchmark tiers must be complete and sorted")
        if len(cases) != CASE_COUNT:
            raise BenchmarkCorpusError("benchmark corpus must have forty cases")
        if cases != tuple(sorted(cases, key=lambda item: item.function)):
            raise BenchmarkCorpusError("benchmark cases must be sorted")
        functions = [item.function for item in cases]
        if len(functions) != len(set(functions)):
            raise BenchmarkCorpusError("benchmark functions duplicate")
        tier_counts = Counter(item.tier for item in cases)
        expected_by_tier = {item.name: item.expected_status for item in tiers}
        for tier in tiers:
            if tier_counts[tier.name] != tier.count:
                raise BenchmarkCorpusError("benchmark tier case count is stale")
        if any(
            case.expected_status != expected_by_tier[case.tier]
            for case in cases
        ):
            raise BenchmarkCorpusError("benchmark case status differs from its tier")
        counts = Counter(item.expected_status for item in cases)
        if dict(sorted(counts.items())) != {
            key: value for key, value in EXPECTED_COUNTS.items() if value
        }:
            raise BenchmarkCorpusError("benchmark expected aggregate is stale")
        if not self.source_text.endswith("\n") or "\r" in self.source_text:
            raise BenchmarkCorpusError("benchmark source must be LF-only with final newline")
        if _sha256_text(self.source_text) != self.source_sha256:
            raise BenchmarkCorpusError("benchmark source hash is stale")
        object.__setattr__(self, "tiers", tiers)
        object.__setattr__(self, "cases", cases)
        expected_id = _content_id(self.content_dict())
        if _require_hash(self.id, "benchmark corpus id") != expected_id:
            raise BenchmarkCorpusError("benchmark corpus identity is stale")

    @classmethod
    def create(
        cls,
        *,
        source_text: str,
        tiers: Sequence[BenchmarkTier],
        cases: Sequence[BenchmarkCase],
        root: Path,
    ) -> "BenchmarkCorpus":
        tier_tuple = tuple(tiers)
        case_tuple = tuple(cases)
        source_hash = _sha256_text(source_text)
        content = {
            "cases": [item.to_dict() for item in case_tuple],
            "schema": BENCHMARK_CORPUS_SCHEMA,
            "source": "corpus.cpp",
            "source_sha256": source_hash,
            "tiers": [item.to_dict() for item in tier_tuple],
        }
        return cls(
            _content_id(content),
            "corpus.cpp",
            source_hash,
            tier_tuple,
            case_tuple,
            source_text,
            root,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "cases": [item.to_dict() for item in self.cases],
            "schema": BENCHMARK_CORPUS_SCHEMA,
            "source": self.source,
            "source_sha256": self.source_sha256,
            "tiers": [item.to_dict() for item in self.tiers],
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, order=True, slots=True)
class BenchmarkStatus:
    function: str
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.function, str) or _FUNCTION_RE.fullmatch(self.function) is None:
            raise BenchmarkCorpusError("benchmark result function is unsupported")
        if self.status not in STATUSES:
            raise BenchmarkCorpusError("benchmark result status is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {"function": self.function, "status": self.status}


@dataclass(frozen=True, slots=True)
class BenchmarkCorpusCheck:
    corpus: str
    cases: tuple[BenchmarkStatus, ...]

    def __post_init__(self) -> None:
        _require_hash(self.corpus, "benchmark check corpus")
        cases = tuple(self.cases)
        if len(cases) != CASE_COUNT or cases != tuple(
            sorted(cases, key=lambda item: item.function)
        ):
            raise BenchmarkCorpusError("benchmark check cases are incomplete or unsorted")
        object.__setattr__(self, "cases", cases)

    @property
    def counts(self) -> dict[str, int]:
        raw = Counter(item.status for item in self.cases)
        return {status: raw.get(status, 0) for status in STATUSES}

    def to_dict(self) -> dict[str, object]:
        return {
            "case_count": len(self.cases),
            "cases": [item.to_dict() for item in self.cases],
            "corpus": self.corpus,
            "counts": self.counts,
            "schema": BENCHMARK_CHECK_SCHEMA,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def load_benchmark_corpus(root: str | Path) -> BenchmarkCorpus:
    corpus_root = Path(root).resolve()
    manifest_text = _read_utf8(corpus_root / "manifest.json", "benchmark manifest")
    source_text = _read_utf8(corpus_root / "corpus.cpp", "benchmark source")
    payload = _parse_json(manifest_text, "benchmark manifest")
    _exact_keys(
        payload,
        {"cases", "id", "schema", "source", "source_sha256", "tiers"},
        "benchmark manifest",
    )
    if payload["schema"] != BENCHMARK_CORPUS_SCHEMA:
        raise BenchmarkCorpusError("benchmark manifest schema is unsupported")
    raw_tiers = payload["tiers"]
    raw_cases = payload["cases"]
    if not isinstance(raw_tiers, list) or not isinstance(raw_cases, list):
        raise BenchmarkCorpusError("benchmark tiers and cases must be arrays")
    tiers: list[BenchmarkTier] = []
    for index, raw in enumerate(raw_tiers):
        field_name = f"benchmark tiers[{index}]"
        if not isinstance(raw, Mapping):
            raise BenchmarkCorpusError(f"{field_name} must be an object")
        _exact_keys(raw, {"count", "expected_status", "name"}, field_name)
        tiers.append(
            BenchmarkTier(raw["name"], raw["expected_status"], raw["count"])
        )
    cases: list[BenchmarkCase] = []
    for index, raw in enumerate(raw_cases):
        field_name = f"benchmark cases[{index}]"
        if not isinstance(raw, Mapping):
            raise BenchmarkCorpusError(f"{field_name} must be an object")
        _exact_keys(raw, {"expected_status", "function", "tier"}, field_name)
        cases.append(
            BenchmarkCase(raw["function"], raw["tier"], raw["expected_status"])
        )
    corpus = BenchmarkCorpus.create(
        source_text=source_text,
        tiers=tiers,
        cases=cases,
        root=corpus_root,
    )
    if payload["id"] != corpus.id:
        raise BenchmarkCorpusError("benchmark manifest identity is stale")
    if payload["source"] != corpus.source or payload["source_sha256"] != corpus.source_sha256:
        raise BenchmarkCorpusError("benchmark manifest source link is stale")
    if corpus.to_json() != manifest_text:
        raise BenchmarkCorpusError("benchmark manifest JSON is not canonical")
    expected_files = {".gitattributes", "corpus.cpp", "manifest.json"}
    actual_files = {
        path.relative_to(corpus_root).as_posix()
        for path in corpus_root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise BenchmarkCorpusError(
            f"benchmark file set differs; missing={sorted(expected_files - actual_files)!r}, "
            f"extra={sorted(actual_files - expected_files)!r}"
        )
    return corpus


def _aggregate_status(statuses: Sequence[VerificationStatus]) -> str:
    if not statuses:
        raise BenchmarkCorpusError("benchmark function has no referee results")
    if VerificationStatus.SOLVER_ERROR in statuses:
        raise BenchmarkCorpusError("benchmark function has a solver/checker error")
    if VerificationStatus.UNSUPPORTED in statuses:
        return "unsupported"
    if VerificationStatus.VIOLATED in statuses:
        return "violated"
    if VerificationStatus.UNKNOWN in statuses:
        return "unknown"
    if all(status == VerificationStatus.VERIFIED for status in statuses):
        return "verified"
    raise BenchmarkCorpusError("benchmark function has an unclassified result set")


def observe_benchmark_corpus(corpus: BenchmarkCorpus) -> BenchmarkCorpusCheck:
    checker = AffineChecker()
    report = VerificationPipeline(checker=checker).verify_source(
        corpus.source_text,
        "benchmarks/corpus/corpus.cpp",
    )
    if report.module.unsupported:
        raise BenchmarkCorpusError(
            "benchmark source has unsupported lowering: "
            + "; ".join(node.reason for node in report.module.unsupported)
        )
    expected_functions = {case.function for case in corpus.cases}
    actual_functions = {
        function.name for function in report.module.functions if function.has_body
    }
    if actual_functions != expected_functions:
        raise BenchmarkCorpusError("benchmark function set differs from manifest")
    observations: list[BenchmarkStatus] = []
    for case in corpus.cases:
        results = [result for result in report.results if result.function == case.function]
        status = _aggregate_status([result.status for result in results])
        if status == "violated":
            violations = [
                result
                for result in results
                if result.status == VerificationStatus.VIOLATED
            ]
            if not violations or any(not result.counterexample for result in violations):
                raise BenchmarkCorpusError(
                    f"violated benchmark lacks concrete evidence: {case.function}"
                )
            obligations = {item.id: item for item in report.obligations}
            for violation in violations:
                replay = checker.check(obligations[violation.obligation_id])
                if replay.to_dict() != violation.to_dict():
                    raise BenchmarkCorpusError(
                        f"benchmark violation did not replay: {case.function}"
                    )
        observations.append(BenchmarkStatus(case.function, status))
    return BenchmarkCorpusCheck(corpus.id, tuple(observations))


def check_benchmark_corpus(corpus: BenchmarkCorpus) -> BenchmarkCorpusCheck:
    observed = observe_benchmark_corpus(corpus)
    expected = tuple(
        BenchmarkStatus(case.function, case.expected_status)
        for case in corpus.cases
    )
    if observed.cases != expected:
        differences = [
            f"{actual.function}: expected {wanted.status}, observed {actual.status}"
            for wanted, actual in zip(expected, observed.cases)
            if wanted != actual
        ]
        raise BenchmarkCorpusError(
            "benchmark expected statuses differ: " + "; ".join(differences)
        )
    if observed.counts != EXPECTED_COUNTS:
        raise BenchmarkCorpusError("benchmark aggregate counts differ")
    return observed
