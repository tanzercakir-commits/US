"""Deterministic logical trend derived from complete benchmark ledgers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .benchmark_corpus import CASE_COUNT
from .benchmark_results import BenchmarkRun


BENCHMARK_TREND_SCHEMA = "codeskeptic.benchmark-trend/v1"
BENCHMARK_TREND_IDENTITY_SCHEMA = "codeskeptic.benchmark-trend-identity/v1"
INITIAL_CALIBRATION_LABELS = (
    "f1-calibration-001",
    "f1-calibration-002",
    "f1-calibration-003",
)
TREND_POLICY = {
    "baseline_change": "future-explicit-reviewed-plan-stage-only",
    "future_phase_gate": "append-one-real-observation-before-completion",
    "initial_points": "current-version-calibration-not-historical-phase-gates",
    "point_selection": "all-ledger-rows-in-append-order",
    "timing": "informational-only-never-gates",
}


class BenchmarkTrendError(ValueError):
    """Raised when a trend input or derived artifact fails closed."""


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


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": BENCHMARK_TREND_IDENTITY_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


@dataclass(frozen=True, slots=True)
class TrendRegression:
    code: str
    observation: str
    function: str | None = None
    prior_status: str | None = None
    current_status: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"code": self.code, "observation": self.observation}
        if self.function is not None:
            result["function"] = self.function
        if self.prior_status is not None:
            result["prior_status"] = self.prior_status
        if self.current_status is not None:
            result["current_status"] = self.current_status
        return result


@dataclass(frozen=True, slots=True)
class BenchmarkTrend:
    id: str
    logic_sha256: str
    corpus: str
    baseline: BenchmarkRun
    points: tuple[BenchmarkRun, ...]
    regressions: tuple[TrendRegression, ...]

    @property
    def status(self) -> str:
        return "red" if self.regressions else "green"

    @staticmethod
    def _counts(run: BenchmarkRun) -> dict[str, int]:
        return {**run.counts, "solver_error": 0}

    @staticmethod
    def _point(run: BenchmarkRun) -> dict[str, object]:
        return {
            "counts": BenchmarkTrend._counts(run),
            "duration_ns": run.duration_ns,
            "logic_sha256": run.logic_sha256,
            "observation": run.observation,
            "run": run.id,
            "source_revision": run.source_revision,
        }

    def logic_dict(self) -> dict[str, object]:
        return {
            "baseline": {
                "logic_sha256": self.baseline.logic_sha256,
                "observation": self.baseline.observation,
            },
            "corpus": self.corpus,
            "point_count": len(self.points),
            "points": [
                {
                    "counts": self._counts(run),
                    "logic_sha256": run.logic_sha256,
                    "observation": run.observation,
                }
                for run in self.points
            ],
            "policy": TREND_POLICY,
            "regressions": [item.to_dict() for item in self.regressions],
            "status": self.status,
        }

    def content_dict(self) -> dict[str, object]:
        return {
            "baseline": {
                "logic_sha256": self.baseline.logic_sha256,
                "observation": self.baseline.observation,
                "run": self.baseline.id,
            },
            "corpus": self.corpus,
            "logic_sha256": self.logic_sha256,
            "point_count": len(self.points),
            "points": [self._point(run) for run in self.points],
            "policy": TREND_POLICY,
            "regressions": [item.to_dict() for item in self.regressions],
            "schema": BENCHMARK_TREND_SCHEMA,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _validate_point_sequence(runs: tuple[BenchmarkRun, ...]) -> None:
    if len(runs) < len(INITIAL_CALIBRATION_LABELS):
        raise BenchmarkTrendError("benchmark trend requires at least three points")
    actual = tuple(run.observation for run in runs[:3])
    if actual != INITIAL_CALIBRATION_LABELS:
        raise BenchmarkTrendError(
            "initial trend points must be the three ordered F1 calibrations"
        )
    if any(run.observation.startswith("f1-calibration-") for run in runs[3:]):
        raise BenchmarkTrendError(
            "F1 calibration labels are reserved for the initial three points"
        )
    if len({run.id for run in runs}) != len(runs):
        raise BenchmarkTrendError("benchmark trend run identities duplicate")
    if len({run.observation for run in runs}) != len(runs):
        raise BenchmarkTrendError("benchmark trend observation labels duplicate")
    if len({run.corpus for run in runs}) != 1:
        raise BenchmarkTrendError("benchmark trend mixes corpus identities")
    initial_logic = {run.logic_sha256 for run in runs[:3]}
    if len(initial_logic) != 1:
        raise BenchmarkTrendError(
            "initial F1 calibrations do not represent one current logical version"
        )


def _regressions(runs: tuple[BenchmarkRun, ...]) -> tuple[TrendRegression, ...]:
    baseline = runs[0]
    baseline_by_function = {
        item.function: item.status for item in baseline.cases
    }
    results: list[TrendRegression] = []
    if baseline.counts["unsupported"]:
        results.append(
            TrendRegression("baseline-unsupported", baseline.observation)
        )
    for run in runs[1:]:
        current_by_function = {item.function: item.status for item in run.cases}
        if len(current_by_function) != CASE_COUNT or set(current_by_function) != set(
            baseline_by_function
        ):
            results.append(TrendRegression("function-coverage-changed", run.observation))
            continue
        if run.counts["unknown"] > baseline.counts["unknown"]:
            results.append(TrendRegression("unknown-coverage-increased", run.observation))
        if run.counts["unsupported"] > baseline.counts["unsupported"]:
            results.append(
                TrendRegression("unsupported-coverage-increased", run.observation)
            )
        for function in sorted(baseline_by_function):
            prior = baseline_by_function[function]
            current = current_by_function[function]
            if prior == "verified" and current != "verified":
                results.append(
                    TrendRegression(
                        "verified-loss", run.observation, function, prior, current
                    )
                )
            elif prior == "violated" and current != "violated":
                results.append(
                    TrendRegression(
                        "violated-promotion", run.observation, function, prior, current
                    )
                )
            elif prior == "unknown" and current != "unknown":
                results.append(
                    TrendRegression(
                        "reviewed-baseline-required",
                        run.observation,
                        function,
                        prior,
                        current,
                    )
                )
            elif prior == "unsupported" and current != "unsupported":
                results.append(
                    TrendRegression(
                        "reviewed-baseline-required",
                        run.observation,
                        function,
                        prior,
                        current,
                    )
                )
    return tuple(results)


def derive_benchmark_trend(runs: Sequence[BenchmarkRun]) -> BenchmarkTrend:
    rows = tuple(runs)
    _validate_point_sequence(rows)
    regressions = _regressions(rows)
    provisional = BenchmarkTrend(
        id="",
        logic_sha256="",
        corpus=rows[0].corpus,
        baseline=rows[0],
        points=rows,
        regressions=regressions,
    )
    logic_sha256 = _content_id("benchmark-trend-logic", provisional.logic_dict())
    with_logic = BenchmarkTrend(
        id="",
        logic_sha256=logic_sha256,
        corpus=rows[0].corpus,
        baseline=rows[0],
        points=rows,
        regressions=regressions,
    )
    identity = _content_id("benchmark-trend", with_logic.content_dict())
    return BenchmarkTrend(
        identity,
        logic_sha256,
        rows[0].corpus,
        rows[0],
        rows,
        regressions,
    )


def trend_json(runs: Sequence[BenchmarkRun]) -> str:
    return derive_benchmark_trend(runs).to_json()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkTrendError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BenchmarkTrendError(f"non-finite JSON number {value!r} is not allowed")


def load_benchmark_trend_json(
    text: str, runs: Sequence[BenchmarkRun]
) -> BenchmarkTrend:
    if text.startswith("\ufeff") or "\r" in text or "\x00" in text:
        raise BenchmarkTrendError("benchmark trend must be BOM-free LF-only UTF-8")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise BenchmarkTrendError(f"invalid benchmark trend JSON: {error}") from error
    if not isinstance(payload, Mapping):
        raise BenchmarkTrendError("benchmark trend must be a JSON object")
    expected = derive_benchmark_trend(runs)
    if dict(payload) != expected.to_dict():
        raise BenchmarkTrendError(
            "benchmark trend does not match the complete ordered ledger"
        )
    if text != expected.to_json():
        raise BenchmarkTrendError("benchmark trend JSON is not canonical")
    return expected
