"""Generate or check one deterministic, byte-bounded fact context pack."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.fact_context import (  # noqa: E402
    DEFAULT_CONTEXT_BUDGET,
    ContextBudgetError,
    build_fact_context,
)
from semantic_verifier.fact_queries import (  # noqa: E402
    FactQueryError,
    FactWorld,
    read_fact_index,
)
from semantic_verifier.facts import FactIndexError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate or check one exact CodeSkeptic fact context pack."
        )
    )
    parser.add_argument("index", type=Path)
    parser.add_argument("selector")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_CONTEXT_BUDGET,
    )
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        world = FactWorld(read_fact_index(arguments.index))
    except (
        FactIndexError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(
            f"fact-context input error: {error}",
            file=sys.stderr,
        )
        return 3

    try:
        rendered = build_fact_context(
            world,
            arguments.selector,
            arguments.budget,
        ).to_json()
    except (ContextBudgetError, FactQueryError) as error:
        print(
            f"fact-context error: {error}",
            file=sys.stderr,
        )
        return 2

    if arguments.check:
        try:
            actual = arguments.output.read_bytes()
        except OSError as error:
            print(
                f"fact-context check failed: {error}",
                file=sys.stderr,
            )
            return 1
        expected = rendered.encode("utf-8")
        if actual != expected:
            print(
                "fact-context check failed: content differs",
                file=sys.stderr,
            )
            return 1
        print(
            f"fact context matches ({len(expected)} bytes)"
        )
        return 0

    try:
        arguments.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        arguments.output.write_bytes(rendered.encode("utf-8"))
    except OSError as error:
        print(
            f"fact-context output error: {error}",
            file=sys.stderr,
        )
        return 3
    print(
        (
            f"wrote fact context ({len(rendered.encode('utf-8'))} "
            "bytes)"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
