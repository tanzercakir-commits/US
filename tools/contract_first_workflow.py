"""Run the deterministic contract-first workflow checker."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.contract_first import (  # noqa: E402
    ContractFirstInputError,
    run_contract_first,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a content-addressed contract-first task."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--backend", choices=("affine", "z3", "both"), default="affine"
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = run_contract_first(
            args.manifest, checker=create_backend(args.backend)
        ).to_json()
    except (OSError, ValueError, RuntimeError, ContractFirstInputError) as error:
        print(f"contract-first error: {error}", file=sys.stderr)
        return 2
    if args.check is not None:
        try:
            expected = args.check.read_text(encoding="utf-8")
        except OSError as error:
            print(f"contract-first check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print("contract-first run differs from expected", file=sys.stderr)
            return 1
        print(f"contract-first run matches {args.check.as_posix()}")
        return 0
    if args.output is not None:
        try:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"contract-first output error: {error}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())