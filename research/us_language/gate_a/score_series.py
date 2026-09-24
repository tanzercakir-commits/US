#!/usr/bin/env python3
"""Aggregate five paired Gate A repetitions into a frozen outcome."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys


CONDITIONS = ("us", "markdown")
STAGES = {
    "initial": 40,
    "csv": 25,
    "cache": 35,
}
RUNS = range(1, 6)


def load_run(root: Path, condition: str, run: int) -> dict:
    total = 0
    critical_events: list[tuple[int, str, str]] = []

    for stage, expected_max in STAGES.items():
        path = root / condition / f"run_{run}" / f"{stage}.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        if data.get("schema") != "us-language-gate-a-evaluation-v0":
            raise ValueError(f"{path}: unexpected schema")
        if data.get("stage") != stage:
            raise ValueError(f"{path}: stage mismatch")
        if data.get("max_score") != expected_max:
            raise ValueError(f"{path}: max_score must be {expected_max}")

        score = data.get("score")
        if not isinstance(score, int) or not 0 <= score <= expected_max:
            raise ValueError(f"{path}: invalid score {score!r}")
        total += score

        for critical in data.get("critical_violations", []):
            if not isinstance(critical, str):
                raise ValueError(f"{path}: invalid critical violation")
            critical_events.append((run, stage, critical))

    return {
        "score": total,
        "critical_events": critical_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    root = args.results.resolve()

    runs: dict[str, list[dict]] = {condition: [] for condition in CONDITIONS}
    for condition in CONDITIONS:
        for run in RUNS:
            runs[condition].append(load_run(root, condition, run))

    us_scores = [item["score"] for item in runs["us"]]
    md_scores = [item["score"] for item in runs["markdown"]]
    us_median = statistics.median(us_scores)
    md_median = statistics.median(md_scores)
    paired_us_ge_md = sum(
        us >= md for us, md in zip(us_scores, md_scores, strict=True)
    )

    us_critical = sum(len(item["critical_events"]) for item in runs["us"])
    md_critical = sum(len(item["critical_events"]) for item in runs["markdown"])

    positive = (
        us_median - md_median >= 10
        and paired_us_ge_md >= 4
        and us_critical <= md_critical
    )
    negative = (
        md_median - us_median >= 10
        or us_critical > md_critical
    )

    if positive:
        outcome = "positive"
    elif negative:
        outcome = "negative"
    elif abs(us_median - md_median) < 10 and us_critical == md_critical:
        outcome = "null"
    else:
        outcome = "inconclusive"

    result = {
        "schema": "us-language-gate-a-series-v0",
        "us_scores": us_scores,
        "markdown_scores": md_scores,
        "us_median": us_median,
        "markdown_median": md_median,
        "paired_us_ge_markdown": paired_us_ge_md,
        "us_critical_events": us_critical,
        "markdown_critical_events": md_critical,
        "outcome": outcome,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
