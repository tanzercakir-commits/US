#!/usr/bin/env python3
"""Record or summarize append-only benchmark run evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.benchmark_corpus import (  # noqa: E402
    BenchmarkCorpusError,
    load_benchmark_corpus,
)
from semantic_verifier.benchmark_results import (  # noqa: E402
    BenchmarkResultError,
    append_benchmark_run,
    capture_benchmark_run,
    load_benchmark_run_ledger,
    summary_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record or summarize append-only benchmark evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("corpus", type=Path)
    record.add_argument("ledger", type=Path)
    record.add_argument("--observation", required=True)
    record.add_argument("--recorded-on", required=True)
    record.add_argument("--source-revision", required=True)
    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("ledger", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "record":
            corpus = load_benchmark_corpus(arguments.corpus)
            run = capture_benchmark_run(
                corpus,
                observation=arguments.observation,
                recorded_on=arguments.recorded_on,
                source_revision=arguments.source_revision,
            )
            append_benchmark_run(arguments.ledger, run)
            print(run.to_json_line(), end="")
        else:
            text = arguments.ledger.read_text(encoding="utf-8")
            print(summary_json(load_benchmark_run_ledger(text)), end="")
    except (
        BenchmarkCorpusError,
        BenchmarkResultError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"benchmark run error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
