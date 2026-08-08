"""Exact honest report for the bounded E2 paired experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any

from .experiment_e2 import (
    ARM_COMPILER,
    ARM_SEMANTIC,
    ARMS,
    EVIDENCE_SCOPE,
    MAX_PROPOSALS,
    PROPOSER,
    ExperimentTrials,
)


EXPERIMENT_REPORT_SCHEMA = "codeskeptic.experiment-report/v1"
EXPERIMENT_REPORT_ID_SCHEMA = "codeskeptic.experiment-report-identity/v1"
HYPOTHESIS_METRIC = "median-censored-repair-score"
LIMITATIONS = (
    "This recorded-scripted-proxy pilot does not measure an independently sampled AI model.",
    "The result does not establish consciousness, general model behavior, or causality.",
    "Only the frozen twenty-case corpus and exact proposal transcripts are in scope.",
)
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ExperimentReportError(ValueError):
    """Raised when an E2 report is incomplete, stale, or dishonest."""


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


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


def _content_id(value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": "experiment-report",
        "schema": EXPERIMENT_REPORT_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ExperimentReportError(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    field_name: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise ExperimentReportError(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise ExperimentReportError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class ExactRational:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.numerator, bool)
            or isinstance(self.denominator, bool)
            or not isinstance(self.numerator, int)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
            or math.gcd(abs(self.numerator), self.denominator) != 1
        ):
            raise ExperimentReportError(
                "rational must be reduced integers with positive denominator"
            )

    @classmethod
    def create(cls, value: Fraction) -> "ExactRational":
        return cls(value.numerator, value.denominator)

    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def to_dict(self) -> dict[str, int]:
        return {
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


def exact_median(values: Sequence[int]) -> ExactRational:
    ordered = sorted(values)
    if not ordered:
        raise ExperimentReportError("median requires at least one score")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in ordered
    ):
        raise ExperimentReportError("median scores must be integers")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        value = Fraction(ordered[middle], 1)
    else:
        value = Fraction(
            ordered[middle - 1] + ordered[middle],
            2,
        )
    return ExactRational.create(value)


@dataclass(frozen=True, slots=True)
class ArmReport:
    arm: str
    succeeded: int
    exhausted: int
    scores: tuple[int, ...]
    median: ExactRational

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ExperimentReportError("arm report has unsupported arm")
        if (
            isinstance(self.succeeded, bool)
            or isinstance(self.exhausted, bool)
            or not isinstance(self.succeeded, int)
            or not isinstance(self.exhausted, int)
            or self.succeeded < 0
            or self.exhausted < 0
            or self.succeeded + self.exhausted != 20
        ):
            raise ExperimentReportError("arm report counts are invalid")
        normalized = tuple(self.scores)
        if len(normalized) != 20 or any(
            isinstance(score, bool)
            or not isinstance(score, int)
            or not 1 <= score <= MAX_PROPOSALS + 1
            for score in normalized
        ):
            raise ExperimentReportError("arm report scores are invalid")
        if self.exhausted != sum(
            score == MAX_PROPOSALS + 1 for score in normalized
        ):
            raise ExperimentReportError(
                "arm exhaustion count disagrees with censored scores"
            )
        if self.median != exact_median(normalized):
            raise ExperimentReportError("arm median is not exact")
        object.__setattr__(self, "scores", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "exhausted": self.exhausted,
            "median": self.median.to_dict(),
            "scores": list(self.scores),
            "succeeded": self.succeeded,
        }


@dataclass(frozen=True, slots=True)
class PairedReport:
    case: str
    compiler_score: int
    semantic_score: int
    delta: int
    compiler_trial: str
    semantic_trial: str
    compiler_loop: str
    semantic_loop: str

    def __post_init__(self) -> None:
        if not isinstance(self.case, str) or not self.case:
            raise ExperimentReportError("paired case must be text")
        for score, name in (
            (self.compiler_score, "compiler_score"),
            (self.semantic_score, "semantic_score"),
        ):
            if (
                isinstance(score, bool)
                or not isinstance(score, int)
                or not 1 <= score <= MAX_PROPOSALS + 1
            ):
                raise ExperimentReportError(f"paired {name} is invalid")
        if self.delta != self.compiler_score - self.semantic_score:
            raise ExperimentReportError("paired delta is not exact")
        for value, name in (
            (self.compiler_trial, "compiler_trial"),
            (self.semantic_trial, "semantic_trial"),
            (self.compiler_loop, "compiler_loop"),
            (self.semantic_loop, "semantic_loop"),
        ):
            _require_hash(value, f"pair.{name}")

    def to_dict(self) -> dict[str, object]:
        return {
            "case": self.case,
            "compiler_loop": self.compiler_loop,
            "compiler_score": self.compiler_score,
            "compiler_trial": self.compiler_trial,
            "delta": self.delta,
            "semantic_loop": self.semantic_loop,
            "semantic_score": self.semantic_score,
            "semantic_trial": self.semantic_trial,
        }


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    id: str
    corpus: str
    trials: str
    proposer: str
    evidence_scope: str
    threshold: ExactRational
    improvement: ExactRational
    outcome: str
    arms: tuple[ArmReport, ...]
    pairs: tuple[PairedReport, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_hash(self.corpus, "report.corpus")
        _require_hash(self.trials, "report.trials")
        if self.proposer != PROPOSER:
            raise ExperimentReportError("report proposer is unsupported")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise ExperimentReportError("report evidence scope is unsupported")
        if self.threshold != ExactRational(2, 5):
            raise ExperimentReportError("report threshold is not 40 percent")
        if tuple(arm.arm for arm in self.arms) != ARMS:
            raise ExperimentReportError("report arms are incomplete or unordered")
        normalized_pairs = tuple(self.pairs)
        if (
            len(normalized_pairs) != 20
            or tuple(pair.case for pair in normalized_pairs)
            != tuple(sorted(pair.case for pair in normalized_pairs))
            or len({pair.case for pair in normalized_pairs}) != 20
        ):
            raise ExperimentReportError("report pairs are incomplete or unordered")
        compiler = self.arms[0]
        semantic = self.arms[1]
        if tuple(pair.compiler_score for pair in normalized_pairs) != compiler.scores:
            raise ExperimentReportError("compiler score vector drops or changes a pair")
        if tuple(pair.semantic_score for pair in normalized_pairs) != semantic.scores:
            raise ExperimentReportError("semantic score vector drops or changes a pair")
        compiler_median = compiler.median.fraction()
        expected_improvement = ExactRational.create(
            (compiler_median - semantic.median.fraction())
            / compiler_median
        )
        if self.improvement != expected_improvement:
            raise ExperimentReportError("report improvement is not exact")
        expected_outcome = (
            "passed"
            if self.improvement.fraction() >= self.threshold.fraction()
            else "failed"
        )
        if self.outcome != expected_outcome:
            raise ExperimentReportError("report outcome disagrees with threshold")
        if tuple(self.limitations) != LIMITATIONS:
            raise ExperimentReportError("report limitations are incomplete")
        object.__setattr__(self, "pairs", normalized_pairs)
        object.__setattr__(self, "limitations", tuple(self.limitations))
        expected = _content_id(self.content_dict())
        if _require_hash(self.id, "report.id") != expected:
            raise ExperimentReportError("report.id does not match canonical content")

    @classmethod
    def create(cls, trials: ExperimentTrials) -> "ExperimentReport":
        rows = {(row.case, row.arm): row for row in trials.trials}
        cases = sorted({row.case for row in trials.trials})
        pairs: list[PairedReport] = []
        for case in cases:
            compiler = rows[(case, ARM_COMPILER)]
            semantic = rows[(case, ARM_SEMANTIC)]
            pairs.append(
                PairedReport(
                    case,
                    compiler.score,
                    semantic.score,
                    compiler.score - semantic.score,
                    compiler.id,
                    semantic.id,
                    compiler.loop.id,
                    semantic.loop.id,
                )
            )
        arms: list[ArmReport] = []
        for arm in ARMS:
            arm_rows = [row for row in trials.trials if row.arm == arm]
            scores = tuple(row.score for row in arm_rows)
            arms.append(
                ArmReport(
                    arm,
                    sum(row.status == "verified" for row in arm_rows),
                    sum(row.status == "exhausted" for row in arm_rows),
                    scores,
                    exact_median(scores),
                )
            )
        threshold = ExactRational(2, 5)
        compiler_median = arms[0].median.fraction()
        improvement = ExactRational.create(
            (compiler_median - arms[1].median.fraction())
            / compiler_median
        )
        outcome = (
            "passed"
            if improvement.fraction() >= threshold.fraction()
            else "failed"
        )
        content = _report_content(
            trials,
            tuple(arms),
            tuple(pairs),
            threshold,
            improvement,
            outcome,
        )
        return cls(
            _content_id(content),
            trials.corpus,
            trials.id,
            trials.proposer,
            trials.evidence_scope,
            threshold,
            improvement,
            outcome,
            tuple(arms),
            tuple(pairs),
            LIMITATIONS,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "arms": {arm.arm: arm.to_dict() for arm in self.arms},
            "corpus": self.corpus,
            "evidence_scope": self.evidence_scope,
            "hypothesis": {
                "metric": HYPOTHESIS_METRIC,
                "semantic_bundle_reduction_threshold": self.threshold.to_dict(),
            },
            "improvement": self.improvement.to_dict(),
            "limitations": list(self.limitations),
            "outcome": self.outcome,
            "pairs": [pair.to_dict() for pair in self.pairs],
            "proposer": self.proposer,
            "schema": EXPERIMENT_REPORT_SCHEMA,
            "trials": self.trials,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _report_content(
    trials: ExperimentTrials,
    arms: tuple[ArmReport, ...],
    pairs: tuple[PairedReport, ...],
    threshold: ExactRational,
    improvement: ExactRational,
    outcome: str,
) -> dict[str, object]:
    return {
        "arms": {arm.arm: arm.to_dict() for arm in arms},
        "corpus": trials.corpus,
        "evidence_scope": trials.evidence_scope,
        "hypothesis": {
            "metric": HYPOTHESIS_METRIC,
            "semantic_bundle_reduction_threshold": threshold.to_dict(),
        },
        "improvement": improvement.to_dict(),
        "limitations": list(LIMITATIONS),
        "outcome": outcome,
        "pairs": [pair.to_dict() for pair in pairs],
        "proposer": trials.proposer,
        "schema": EXPERIMENT_REPORT_SCHEMA,
        "trials": trials.id,
    }


def build_experiment_report(trials: ExperimentTrials) -> ExperimentReport:
    return ExperimentReport.create(trials)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentReportError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ExperimentReportError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def load_experiment_report_json(
    text: str,
    trials: ExperimentTrials,
) -> ExperimentReport:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ExperimentReportError(
            f"invalid experiment report JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise ExperimentReportError("experiment report must be an object")
    _exact_keys(
        payload,
        {
            "arms",
            "corpus",
            "evidence_scope",
            "hypothesis",
            "id",
            "improvement",
            "limitations",
            "outcome",
            "pairs",
            "proposer",
            "schema",
            "trials",
        },
        "report",
    )
    if payload["schema"] != EXPERIMENT_REPORT_SCHEMA:
        raise ExperimentReportError("unsupported experiment report schema")
    expected = build_experiment_report(trials)
    if _identity_bytes(payload) != _identity_bytes(expected.to_dict()):
        raise ExperimentReportError(
            "experiment report differs from exact complete recomputation"
        )
    return expected
