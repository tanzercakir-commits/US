"""Render or deterministically pre-screen an offline contract proposal."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.contract_proposals import (  # noqa: E402
    ProposalInputError,
    pre_screen_response,
    read_request,
    render_prompt_pack,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render or pre-screen an offline contract proposal."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--response",
        type=Path,
        help="Untrusted response to pre-screen; omit to render the prompt pack.",
    )
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="affine",
        help="Deterministic referee used only with --response (default: affine).",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--check", type=Path)
    args = parser.parse_args(argv)

    try:
        request = read_request(args.request)
        if args.response is None:
            rendered = render_prompt_pack(request)
            artifact_name = "contract proposal prompt"
        else:
            response_text = args.response.read_text(encoding="utf-8")
            report = pre_screen_response(
                request,
                response_text,
                checker=create_backend(args.backend),
            )
            rendered = report.to_json()
            artifact_name = "contract proposal pre-screen"
    except (OSError, ProposalInputError, RuntimeError, ValueError) as error:
        print(f"contract proposal error: {error}", file=sys.stderr)
        return 2

    if args.check is not None:
        try:
            expected = args.check.read_text(encoding="utf-8")
        except OSError as error:
            print(f"contract proposal check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print(f"{artifact_name} differs from expected", file=sys.stderr)
            return 1
        print(f"{artifact_name} matches {args.check.as_posix()}")
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