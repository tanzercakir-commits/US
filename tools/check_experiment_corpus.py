#!/usr/bin/env python3
"""Validate and replay the frozen E2 seeded-bug corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.experiment_corpus import (
    ExperimentCorpusError,
    check_experiment_corpus,
    load_experiment_corpus,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and replay the strict E2 experiment corpus."
    )
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    try:
        corpus = load_experiment_corpus(args.corpus)
        result = check_experiment_corpus(corpus)
    except ExperimentCorpusError as error:
        print(f"experiment corpus error: {error}", file=sys.stderr)
        return 2
    print(result.to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
