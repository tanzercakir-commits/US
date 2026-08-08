"""Render, pre-screen, review, or audit an offline contract proposal."""

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
    build_review_bundle,
    pre_screen_response,
    read_request,
    render_prompt_pack,
    validate_accepted_source,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render, pre-screen, review, or audit an offline proposal."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--response",
        type=Path,
        help="Untrusted response; omit to render the prompt pack.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--review",
        action="store_true",
        help="Build a review bundle after a successful pre-screen.",
    )
    mode.add_argument(
        "--accepted-source",
        type=Path,
        help="Separately human-edited source to audit for accepted intent.",
    )
    parser.add_argument(
        "--overlay-output",
        type=Path,
        help="Write the cs: ai candidate overlay; valid only with --review.",
    )
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="affine",
        help="Deterministic referee used with --response (default: affine).",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--check", type=Path)
    args = parser.parse_args(argv)

    if (args.review or args.accepted_source is not None) and args.response is None:
        parser.error("--review/--accepted-source requires --response")
    if args.overlay_output is not None and not args.review:
        parser.error("--overlay-output requires --review")

    try:
        request = read_request(args.request)
        if args.response is None:
            rendered = render_prompt_pack(request)
            artifact_name = "contract proposal prompt"
        else:
            response_text = args.response.read_text(encoding="utf-8")
            checker = create_backend(args.backend)
            if args.accepted_source is not None:
                accepted_source = args.accepted_source.read_text(encoding="utf-8")
                artifact = validate_accepted_source(
                    request,
                    response_text,
                    accepted_source,
                    checker=checker,
                )
                rendered = artifact.to_json()
                artifact_name = "accepted intent audit"
            elif args.review:
                artifact = build_review_bundle(
                    request,
                    response_text,
                    checker=checker,
                )
                if args.overlay_output is not None:
                    if artifact.candidate_overlay is None:
                        raise ProposalInputError(
                            "review bundle is not reviewable; no overlay exported"
                        )
                    args.overlay_output.write_text(
                        artifact.candidate_overlay,
                        encoding="utf-8",
                        newline="\n",
                    )
                rendered = artifact.to_json()
                artifact_name = "contract proposal review"
            else:
                artifact = pre_screen_response(
                    request,
                    response_text,
                    checker=checker,
                )
                rendered = artifact.to_json()
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