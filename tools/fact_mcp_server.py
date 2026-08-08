"""Run the read-only CodeSkeptic fact-query MCP stdio server."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.fact_mcp import FactMcpServer  # noqa: E402
from semantic_verifier.fact_queries import FactWorld, read_fact_index  # noqa: E402
from semantic_verifier.facts import FactIndexError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Expose one validated CodeSkeptic fact index over MCP stdio."
        )
    )
    parser.add_argument("index", type=Path)
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
            f"fact-mcp input error: {error}",
            file=sys.stderr,
        )
        return 3

    server = FactMcpServer(world)
    try:
        return server.serve(
            sys.stdin.buffer,
            sys.stdout.buffer,
            sys.stderr,
        )
    except (BrokenPipeError, OSError) as error:
        print(
            f"fact-mcp transport error: {error}",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
