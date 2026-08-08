"""Measure deterministic VC path growth on synthetic branch diamonds."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import CheckerBackend  # noqa: E402
from semantic_verifier.model import (  # noqa: E402
    Obligation,
    SCHEMA,
    VerificationResult,
    VerificationStatus,
    nodes_in,
)
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402


PROBE_SCHEMA = "codeskeptic.path-scaling-probe/v0"


class _MeasurementChecker(CheckerBackend):
    """Avoid solving while preserving the ordinary pipeline shape."""

    name = "path-scaling-measurement"

    def check(self, obligation: Obligation) -> VerificationResult:
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=VerificationStatus.UNKNOWN,
            location=obligation.location,
            message="unknown: path-scaling measurement does not invoke a referee",
        )


def diamond_source(diamonds: int) -> str:
    """Create sequential empty diamonds followed by one assertion."""

    if not 0 <= diamonds <= 12:
        raise ValueError("diamonds must be between 0 and 12")
    parameters = ["int x"] + [f"bool b{index}" for index in range(diamonds)]
    lines = ["void assert(bool);", "", f"int diamonds_{diamonds}({', '.join(parameters)}) {{"]
    for index in range(diamonds):
        lines.append(f"    if (b{index}) {{ }} else {{ }}")
    lines.extend(("    assert(x >= 0);", "    return x;", "}"))
    return "\n".join(lines) + "\n"


def obligation_semantic_key(obligation: Obligation) -> str:
    """Hash exact logical content while excluding source/result metadata."""

    encoded_assumptions = sorted(
        json.dumps(
            assumption.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for assumption in obligation.assumptions
    )
    payload = {
        "assumptions": encoded_assumptions,
        "conclusion": (
            obligation.conclusion.to_dict()
            if obligation.conclusion is not None
            else None
        ),
        "mode": obligation.mode,
        "schema": SCHEMA,
        "unsupported_reason": obligation.unsupported_reason,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def measure_case(diamonds: int, *, clang: str | None = None) -> dict[str, object]:
    source = diamond_source(diamonds)
    pipeline = VerificationPipeline(clang)
    pipeline.checker = _MeasurementChecker()
    report = pipeline.verify_source(
        source,
        display_path=f"probe/diamonds_{diamonds}.cpp",
    )
    if not report.module.functions or report.module.unsupported:
        raise RuntimeError("path-scaling source did not lower successfully")

    keys = [obligation_semantic_key(item) for item in report.obligations]
    kinds = Counter(item.kind for item in report.obligations)
    unique = len(set(keys))
    digest = hashlib.sha256("\n".join(sorted(keys)).encode("ascii")).hexdigest()
    return {
        "assertion_obligations": kinds["assertion"],
        "diamonds": diamonds,
        "duplicate_obligations": len(keys) - unique,
        "expected_paths": 2**diamonds,
        "ir_nodes": sum(
            1
            for function in report.module.functions
            for _node in nodes_in(function.body)
        ),
        "max_assumptions": max(
            (len(item.assumptions) for item in report.obligations),
            default=0,
        ),
        "obligation_digest": digest,
        "obligations": len(report.obligations),
        "source_bytes": len(source.encode("utf-8")),
        "unique_obligations": unique,
    }


def run_probe(
    diamonds: Iterable[int] = (1, 2, 4, 8),
    *,
    clang: str | None = None,
) -> dict[str, object]:
    values = tuple(diamonds)
    if not values:
        raise ValueError("at least one diamond count is required")
    if len(values) != len(set(values)):
        raise ValueError("diamond counts must be unique")
    return {
        "cases": [measure_case(value, clang=clang) for value in sorted(values)],
        "schema": PROBE_SCHEMA,
    }


def render_probe(
    diamonds: Iterable[int] = (1, 2, 4, 8),
    *,
    clang: str | None = None,
) -> str:
    return (
        json.dumps(
            run_probe(diamonds, clang=clang),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diamonds",
        type=int,
        nargs="*",
        default=[1, 2, 4, 8],
        help="diamond counts to measure (default: 1 2 4 8; maximum: 12)",
    )
    parser.add_argument("--clang", help="explicit Clang executable")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        sys.stdout.write(render_probe(arguments.diamonds, clang=arguments.clang))
        return 0
    except Exception as error:
        print(f"path-scaling probe failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
