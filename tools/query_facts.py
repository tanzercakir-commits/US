"""Query a deterministic fact-index artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.fact_queries import (  # noqa: E402
    FactQueryError,
    FactWorld,
    read_fact_index,
)
from semantic_verifier.facts import FactIndexError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query one validated CodeSkeptic fact index."
    )
    parser.add_argument("index", type=Path)
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    callers = commands.add_parser(
        "who-calls",
        help="list indexed callers of one exact function",
    )
    callers.add_argument("selector")

    mutators = commands.add_parser(
        "who-mutates",
        help="list indexed mutators of one exact storage symbol",
    )
    mutators.add_argument("selector")

    neighborhood = commands.add_parser(
        "neighborhood",
        help="list the exact fact graph around one symbol",
    )
    neighborhood.add_argument("selector")
    neighborhood.add_argument(
        "--depth",
        type=int,
        default=2,
    )
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
            f"fact-query input error: {error}",
            file=sys.stderr,
        )
        return 3

    try:
        result = world.query(
            arguments.command,
            arguments.selector,
            depth=getattr(arguments, "depth", 2),
        )
    except FactQueryError as error:
        print(
            f"fact-query error: {error}",
            file=sys.stderr,
        )
        return 2

    sys.stdout.write(
        result.to_json()
        if arguments.format == "json"
        else result.to_text()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
