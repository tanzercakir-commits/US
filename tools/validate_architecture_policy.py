"""Validate and canonicalize one CodeSkeptic architecture policy."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.architecture_policy import (  # noqa: E402
    ArchitecturePolicyError,
    read_architecture_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one strict CodeSkeptic architecture policy."
        )
    )
    parser.add_argument("policy", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        policy = read_architecture_policy(arguments.policy)
    except (
        ArchitecturePolicyError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(
            f"architecture-policy error: {error}",
            file=sys.stderr,
        )
        return 2

    sys.stdout.write(policy.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
