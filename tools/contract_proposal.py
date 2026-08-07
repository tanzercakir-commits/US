"""Render a deterministic, offline contract-proposal prompt pack."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.contract_proposals import (  # noqa: E402
    ProposalInputError,
    read_request,
    render_prompt_pack,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render an offline, vendor-neutral contract proposal prompt pack."
    )
    parser.add_argument("--request", type=Path, required=True)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--check", type=Path)
    args = parser.parse_args(argv)

    try:
        rendered = render_prompt_pack(read_request(args.request))
    except (OSError, ProposalInputError, RuntimeError) as error:
        print(f"contract proposal error: {error}", file=sys.stderr)
        return 2

    if args.check is not None:
        try:
            expected = args.check.read_text(encoding="utf-8")
        except OSError as error:
            print(f"contract proposal check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print("contract proposal prompt differs from expected", file=sys.stderr)
            return 1
        print(f"contract proposal prompt matches {args.check.as_posix()}")
        return 0

    if args.output is not None:
        try:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"contract proposal output error: {error}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())