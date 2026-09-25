#!/usr/bin/env python3
"""Aggregate five paired Gate A2 repetitions under the frozen outcome rule."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
from typing import Any


CONDITIONS = ("us", "markdown")
STAGES = {
    "initial": 50,
    "batch": 25,
    "multi_export": 35,
    "retry": 40,
}
RUNS = range(1, 6)
EXPECTED_FAMILY_MAX = {
    "architecture": 15,
    "state_flow": 50,
    "aliasing": 15,
    "audit": 5,
    "external_effects": 20,
    "unresolved": 20,
    "preservation": 25,
}


def load_stage(path: Path, stage: str, expected_max: int) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "us-language-gate-a2-evaluation-v0":
        raise ValueError(f"{path}: unexpected schema")
    if data.get("stage") != stage:
        raise ValueError(f"{path}: stage mismatch")
    if data.get("max_score") != expected_max:
        raise ValueError(f"{path}: max_score must be {expected_max}")

    score = data.get("score")
    if not isinstance(score, int) or not 0 <= score <= expected_max:
        raise ValueError(f"{path}: invalid score {score!r}")

    checks = data.get("checks")
    if not isinstance(checks, list):
        raise ValueError(f"{path}: checks must be a list")
    awarded = sum(check.get("awarded", 0) for check in checks)
    if awarded != score:
        raise ValueError(f"{path}: check awarded sum {awarded} != score {score}")

    reconstructed: dict[str, int] = defaultdict(int)
    for check in checks:
        family = check.get("family")
        points = check.get("points")
        amount = check.get("awarded")
        if not isinstance(family, str):
            raise ValueError(f"{path}: invalid family")
        if not isinstance(points, int) or points < 0:
            raise ValueError(f"{path}: invalid check points")
        if amount not in (0, points):
            raise ValueError(f"{path}: awarded must be zero or full check points")
        reconstructed[family] += amount

    if dict(sorted(reconstructed.items())) != dict(
        sorted(data.get("family_scores", {}).items())
    ):
        raise ValueError(f"{path}: family_scores do not match checks")

    critical = data.get("critical_violations", [])
    if not isinstance(critical, list) or any(not isinstance(x, str) for x in critical):
        raise ValueError(f"{path}: invalid critical_violations")

    return data


def load_run(root: Path, condition: str, run: int) -> dict[str, Any]:
    total = 0
    family_scores: dict[str, int] = defaultdict(int)
    critical_events: list[tuple[int, str, str]] = []

    for stage, expected_max in STAGES.items():
        path = root / condition / f"run_{run}" / f"{stage}.json"
        data = load_stage(path, stage, expected_max)
        total += data["score"]
        for family, score in data["family_scores"].items():
            family_scores[family] += score
        for critical in data["critical_violations"]:
            critical_events.append((run, stage, critical))

    if total > 150:
        raise ValueError(f"{condition} run {run}: score exceeds 150")

    for family, score in family_scores.items():
        maximum = EXPECTED_FAMILY_MAX.get(family)
        if maximum is None:
            raise ValueError(f"{condition} run {run}: unknown family {family}")
        if not 0 <= score <= maximum:
            raise ValueError(
                f"{condition} run {run}: invalid {family} family score {score}"
            )

    return {
        "score": total,
        "family_scores": dict(family_scores),
        "critical_events": critical_events,
    }


def family_medians(runs: list[dict[str, Any]]) -> dict[str, float]:
    return {
        family: statistics.median(
            run["family_scores"].get(family, 0) for run in runs
        )
        for family in EXPECTED_FAMILY_MAX
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    root = args.results.resolve()

    runs: dict[str, list[dict[str, Any]]] = {condition: [] for condition in CONDITIONS}
    for condition in CONDITIONS:
        for run in RUNS:
            runs[condition].append(load_run(root, condition, run))

    us_scores = [item["score"] for item in runs["us"]]
    md_scores = [item["score"] for item in runs["markdown"]]
    us_median = statistics.median(us_scores)
    md_median = statistics.median(md_scores)

    us_critical = sum(len(item["critical_events"]) for item in runs["us"])
    md_critical = sum(len(item["critical_events"]) for item in runs["markdown"])

    us_family = family_medians(runs["us"])
    md_family = family_medians(runs["markdown"])
    us_family_advantages = sorted(
        family
        for family in EXPECTED_FAMILY_MAX
        if us_family[family] - md_family[family] >= 5
    )
    md_family_advantages = sorted(
        family
        for family in EXPECTED_FAMILY_MAX
        if md_family[family] - us_family[family] >= 5
    )

    paired_us_ge_md = sum(
        us >= md for us, md in zip(us_scores, md_scores, strict=True)
    )
    paired_md_ge_us = sum(
        md >= us for us, md in zip(us_scores, md_scores, strict=True)
    )

    insensitive_ceiling = (
        us_median >= 143
        and md_median >= 143
        and us_critical == 0
        and md_critical == 0
    )
    insensitive_floor = us_median <= 60 and md_median <= 60

    positive = (
        us_median - md_median >= 12
        and paired_us_ge_md >= 4
        and us_critical <= md_critical
        and len(us_family_advantages) >= 2
    )
    symmetric_negative = (
        md_median - us_median >= 12
        and paired_md_ge_us >= 4
        and md_critical <= us_critical
        and len(md_family_advantages) >= 2
    )

    if insensitive_ceiling:
        outcome = "insensitive_ceiling"
    elif insensitive_floor:
        outcome = "insensitive_floor"
    elif positive:
        outcome = "positive"
    elif symmetric_negative or us_critical > md_critical:
        outcome = "negative"
    elif abs(us_median - md_median) < 12 and us_critical == md_critical:
        outcome = "null"
    else:
        outcome = "inconclusive"

    result = {
        "schema": "us-language-gate-a2-series-v0",
        "us_scores": us_scores,
        "markdown_scores": md_scores,
        "us_median": us_median,
        "markdown_median": md_median,
        "paired_us_ge_markdown": paired_us_ge_md,
        "paired_markdown_ge_us": paired_md_ge_us,
        "us_critical_events": us_critical,
        "markdown_critical_events": md_critical,
        "us_family_medians": us_family,
        "markdown_family_medians": md_family,
        "us_family_advantages_ge_5": us_family_advantages,
        "markdown_family_advantages_ge_5": md_family_advantages,
        "outcome": outcome,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
