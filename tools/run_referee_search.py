#!/usr/bin/env python3
"""Generate or reproduce-check the frozen exhaustive referee search."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.experiment_corpus import (  # noqa: E402
    ExperimentCorpusError,
    load_experiment_corpus,
)
from semantic_verifier.referee_search import (  # noqa: E402
    RefereeSearchError,
    build_frozen_candidate_set,
    evaluate_candidate_set,
    load_candidate_set_json,
    load_search_report_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check the exhaustive Best-of-4 calibration."
    )
    parser.add_argument("corpus", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        corpus = load_experiment_corpus(arguments.corpus)
        expected_candidates = build_frozen_candidate_set(corpus)
        if arguments.check:
            candidates = load_candidate_set_json(
                arguments.candidates.read_text(encoding="utf-8"),
                corpus,
            )
            if candidates.to_json() != expected_candidates.to_json():
                print("referee search check failed: candidate content differs", file=sys.stderr)
                return 1
        else:
            candidates = expected_candidates
        report = evaluate_candidate_set(corpus, candidates)
        if arguments.check:
            frozen = load_search_report_json(
                arguments.report.read_text(encoding="utf-8"),
                candidates,
            )
            if frozen.to_json() != report.to_json():
                print("referee search check failed: report content differs", file=sys.stderr)
                return 1
        else:
            arguments.candidates.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.candidates.write_text(
                candidates.to_json(), encoding="utf-8", newline="\n"
            )
            arguments.report.write_text(
                report.to_json(), encoding="utf-8", newline="\n"
            )
    except (
        ExperimentCorpusError,
        RefereeSearchError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"referee search error: {error}", file=sys.stderr)
        return 2
    metrics = report._metrics()
    print(
        f"referee search {report.id}: {report.content_dict()['evaluated']} evaluated; "
        f"single={metrics['arms']['single_shot']['successes']}/20; "
        f"best-of-4={metrics['arms']['best_of_n']['successes']}/20; "
        f"uplift={metrics['uplift']['numerator']}/{metrics['uplift']['denominator']}; "
        f"{metrics['outcome']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
