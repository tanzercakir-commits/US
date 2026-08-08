"""Run the isolated A6.6 CHC/Spacer invariant research corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.invariant_research import (  # noqa: E402
    ResearchBudget,
    ResearchInputError,
    render_artifact,
    run_corpus,
)


DEFAULT_MANIFEST = ROOT / "benchmarks" / "invariant_inference" / "benchmarks.json"
DEFAULT_EXPECTED = ROOT / "benchmarks" / "invariant_inference" / "expected_candidates.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run proposal-only invariant inference research benchmarks."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args(argv)
    try:
        artifact = run_corpus(
            args.manifest,
            budget=ResearchBudget(max_solver_cases=args.max_cases),
        )
    except (OSError, ResearchInputError, ValueError) as error:
        print(f"invariant research error: {error}", file=sys.stderr)
        return 2
    rendered = render_artifact(artifact)
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    if args.check:
        try:
            expected = args.expected.read_text(encoding="utf-8")
        except OSError as error:
            print(f"invariant research check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print("invariant research artifact differs from expected", file=sys.stderr)
            return 1
        print(f"invariant research artifact matches {args.expected.as_posix()}")
        return 0
    if args.output is None:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())