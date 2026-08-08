#!/usr/bin/env python3
"""Validate and execute the curated benchmark corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.benchmark_corpus import (  # noqa: E402
    BenchmarkCorpusError,
    check_benchmark_corpus,
    load_benchmark_corpus,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and run the curated supported-subset benchmark."
    )
    parser.add_argument("corpus", type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = check_benchmark_corpus(load_benchmark_corpus(arguments.corpus))
    except (BenchmarkCorpusError, OSError, UnicodeError, ValueError) as error:
        print(f"benchmark corpus error: {error}", file=sys.stderr)
        return 2
    print(result.to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
