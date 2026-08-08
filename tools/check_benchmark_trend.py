#!/usr/bin/env python3
"""Generate or reproduce-check the complete logical benchmark trend."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.benchmark_results import (  # noqa: E402
    BenchmarkResultError,
    load_benchmark_run_ledger,
)
from semantic_verifier.benchmark_trend import (  # noqa: E402
    BenchmarkTrendError,
    derive_benchmark_trend,
    load_benchmark_trend_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check the complete benchmark trend."
    )
    parser.add_argument("ledger", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        ledger_text = arguments.ledger.read_text(encoding="utf-8")
        runs = load_benchmark_run_ledger(ledger_text)
        trend = derive_benchmark_trend(runs)
        rendered = trend.to_json()
        if arguments.check:
            existing = arguments.artifact.read_text(encoding="utf-8")
            load_benchmark_trend_json(existing, runs)
            if existing.encode("utf-8") != rendered.encode("utf-8"):
                raise BenchmarkTrendError("benchmark trend bytes are stale")
        else:
            arguments.artifact.parent.mkdir(parents=True, exist_ok=True)
            arguments.artifact.write_bytes(rendered.encode("utf-8"))
        print(rendered, end="")
        return 0 if trend.status == "green" else 1
    except (
        BenchmarkResultError,
        BenchmarkTrendError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"benchmark trend error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
