"""Check exact fact calls against an architectural dependency policy."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.architecture import enforce_architecture  # noqa: E402
from semantic_verifier.architecture_policy import (  # noqa: E402
    ArchitecturePolicyError,
    read_architecture_policy,
)
from semantic_verifier.fact_queries import read_fact_index  # noqa: E402
from semantic_verifier.facts import FactIndexError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check exact direct-call facts against one architecture policy."
        )
    )
    parser.add_argument("index", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument(
        "--format",
        choices=("json", "sarif", "text"),
        default="json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        index = read_fact_index(arguments.index)
        policy = read_architecture_policy(arguments.policy)
    except (
        ArchitecturePolicyError,
        FactIndexError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(
            f"architecture input error: {error}",
            file=sys.stderr,
        )
        return 3

    report = enforce_architecture(index, policy)
    if arguments.format == "sarif":
        sys.stdout.write(report.to_sarif())
    elif arguments.format == "text":
        sys.stdout.write(report.to_text())
    else:
        sys.stdout.write(report.to_json())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
