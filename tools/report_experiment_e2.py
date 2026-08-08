#!/usr/bin/env python3
"""Generate or check the exact honest E2 experiment report."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.experiment_corpus import (  # noqa: E402
    ExperimentCorpusError,
    load_experiment_corpus,
)
from semantic_verifier.experiment_e2 import (  # noqa: E402
    ExperimentE2Error,
    load_experiment_inputs,
    load_experiment_trials_json,
)
from semantic_verifier.experiment_report import (  # noqa: E402
    ExperimentReportError,
    build_experiment_report,
)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the exact honest E2 paired report."
    )
    parser.add_argument("corpus", type=Path)
    parser.add_argument("contexts", type=Path)
    parser.add_argument("proposals", type=Path)
    parser.add_argument("trials", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        corpus = load_experiment_corpus(arguments.corpus)
        inputs = load_experiment_inputs(
            corpus,
            arguments.contexts,
            arguments.proposals,
        )
        trials = load_experiment_trials_json(
            arguments.trials.read_text(encoding="utf-8"),
            inputs,
        )
        report = build_experiment_report(trials)
        rendered = report.to_json()
        if arguments.check:
            existing = arguments.output.read_text(encoding="utf-8")
            if existing.replace("\r\n", "\n") != rendered:
                print(
                    "experiment report check failed: content differs",
                    file=sys.stderr,
                )
                return 1
        else:
            _atomic_write(arguments.output, rendered.encode("utf-8"))
    except (
        ExperimentCorpusError,
        ExperimentE2Error,
        ExperimentReportError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"experiment report error: {error}", file=sys.stderr)
        return 2

    compiler = report.arms[0].median
    semantic = report.arms[1].median
    improvement = report.improvement
    print(
        f"experiment report {report.id}: {report.outcome}; "
        f"medians={compiler.numerator}/{compiler.denominator},"
        f"{semantic.numerator}/{semantic.denominator}; "
        f"improvement={improvement.numerator}/{improvement.denominator}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
