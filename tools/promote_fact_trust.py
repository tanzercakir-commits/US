"""Produce linked fact, verification, and trust artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.budget import SolverTimeout  # noqa: E402
from semantic_verifier.fact_trust_promotion import (  # noqa: E402
    FactTrustPromotionError,
    FactTrustPromotionPipeline,
    write_promotion_artifacts,
)
from semantic_verifier.frontend import FrontendError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote the referee-proved subset of D1 pure claims."
        )
    )
    parser.add_argument("source")
    parser.add_argument("--display-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="affine",
    )
    parser.add_argument("--clang")
    parser.add_argument("--z3")
    parser.add_argument(
        "--solver-timeout",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare all artifacts without writing",
    )
    arguments = parser.parse_args(argv)

    try:
        checker = create_backend(
            arguments.backend,
            z3=arguments.z3,
            timeout_seconds=SolverTimeout(
                arguments.solver_timeout
            ),
        )
        pipeline = FactTrustPromotionPipeline(
            arguments.clang,
            checker=checker,
            referee=f"codeskeptic.{arguments.backend}/v1",
        )
        result = pipeline.promote_file(
            arguments.source,
            display_path=arguments.display_path,
        )
        mismatches = write_promotion_artifacts(
            result,
            arguments.output_dir,
            check=arguments.check,
        )
    except (
        FactTrustPromotionError,
        FrontendError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(
            f"fact-trust promotion error: {error}",
            file=sys.stderr,
        )
        return 2

    if mismatches:
        for mismatch in mismatches:
            print(
                f"fact-trust promotion check failed: {mismatch}",
                file=sys.stderr,
            )
        return 1
    sys.stdout.write(result.summary_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
