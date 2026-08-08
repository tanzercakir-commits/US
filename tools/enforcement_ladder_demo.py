"""Generate or check the complete three-rung enforcement demo."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.budget import SolverTimeout  # noqa: E402
from semantic_verifier.enforcement_ladder import (  # noqa: E402
    EnforcementLadderInputError,
)
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from semantic_verifier.runtime_assertions import (  # noqa: E402
    build_runtime_assertions,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the static/property/runtime provenance chain."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--property-skeleton", type=Path, required=True)
    parser.add_argument("--property-manifest", type=Path, required=True)
    parser.add_argument("--runtime-wrapper", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--demo-manifest", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--backend", choices=("affine", "z3", "both"), default="both"
    )
    parser.add_argument("--clang")
    parser.add_argument("--z3")
    parser.add_argument("--solver-timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    try:
        source = args.source.read_bytes().decode("utf-8")
        checker = create_backend(
            args.backend,
            z3=args.z3,
            timeout_seconds=SolverTimeout(args.solver_timeout),
        )
        report = VerificationPipeline(
            args.clang,
            checker=checker,
        ).verify_file(args.source)
        bundle = build_runtime_assertions(
            source,
            report,
            display_path=args.source.as_posix(),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        RuntimeError,
        EnforcementLadderInputError,
    ) as error:
        print(f"enforcement-demo error: {error}", file=sys.stderr)
        return 2

    outputs = (
        (args.property_skeleton, bundle.property.skeleton),
        (args.property_manifest, bundle.property.manifest_json()),
        (args.runtime_wrapper, bundle.wrapper),
        (args.runtime_manifest, bundle.manifest_json()),
        (args.demo_manifest, bundle.demo_manifest_json()),
    )
    if args.check:
        for path, rendered in outputs:
            try:
                expected = path.read_text(encoding="utf-8")
            except OSError as error:
                print(f"enforcement-demo check error: {error}", file=sys.stderr)
                return 2
            if rendered != expected:
                print(
                    f"enforcement-demo output differs from {path.as_posix()}",
                    file=sys.stderr,
                )
                return 1
        print("three-rung enforcement artifacts match")
        return 0

    try:
        for path, rendered in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")
    except OSError as error:
        print(f"enforcement-demo output error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())