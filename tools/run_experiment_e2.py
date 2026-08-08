#!/usr/bin/env python3
"""Run or check the frozen paired E2 repair experiment."""

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
    ARMS,
    ExperimentE2Error,
    load_experiment_inputs,
    run_experiment,
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
        description="Run the strict paired E2 repair experiment."
    )
    parser.add_argument("corpus", type=Path)
    parser.add_argument("contexts", type=Path)
    parser.add_argument("proposals", type=Path)
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
        result = run_experiment(inputs)
        rendered = result.to_json()
        if arguments.check:
            existing = arguments.output.read_text(encoding="utf-8")
            if existing.replace("\r\n", "\n") != rendered:
                print(
                    "experiment check failed: trial content differs",
                    file=sys.stderr,
                )
                return 1
        else:
            _atomic_write(arguments.output, rendered.encode("utf-8"))
    except (
        ExperimentCorpusError,
        ExperimentE2Error,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"experiment error: {error}", file=sys.stderr)
        return 2

    summaries = []
    for arm in ARMS:
        rows = [trial for trial in result.trials if trial.arm == arm]
        verified = sum(trial.status == "verified" for trial in rows)
        summaries.append(f"{arm}={verified}/{len(rows)} verified")
    print(f"experiment {result.id}: " + "; ".join(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
