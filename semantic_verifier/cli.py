"""Command-line interface for the prototype."""

from __future__ import annotations

import argparse
import sys

from .backend import create_backend
from .budget import FileCheckBudget, SolverTimeout
from .dump import dump_module, dump_results
from .model import VerificationStatus
from .pipeline import VerificationPipeline


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="semantic-verify",
        description="Lower a restricted C++ subset and check its obligations.",
    )
    parser.add_argument("source", help="C++ source file")
    parser.add_argument(
        "--format",
        choices=("json", "text", "ir"),
        default="text",
        help="output representation (default: text)",
    )
    parser.add_argument(
        "--no-ir",
        action="store_true",
        help="omit Semantic IR from JSON output",
    )
    parser.add_argument(
        "--clang",
        help="path to clang (otherwise PATH/SEMANTIC_VERIFIER_CLANG is used)",
    )
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="both",
        help="checker backend (default: both)",
    )
    parser.add_argument(
        "--z3",
        help="path to Z3 (otherwise SEMANTIC_VERIFIER_Z3/PATH is used)",
    )
    parser.add_argument(
        "--solver-timeout",
        type=float,
        default=5.0,
        help="Z3 timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--cache",
        help="persistent exact obligation-result cache file",
    )
    parser.add_argument(
        "--max-checks",
        type=_non_negative_int,
        help="maximum supported obligation checks per file (default: unlimited)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        checker = create_backend(
            arguments.backend,
            z3=arguments.z3,
            timeout_seconds=SolverTimeout(arguments.solver_timeout),
        )
        pipeline = VerificationPipeline(
            arguments.clang,
            checker=checker,
            cache_path=arguments.cache,
            check_budget=FileCheckBudget(arguments.max_checks),
        )
        report = pipeline.verify_file(arguments.source)
    except Exception as error:
        print(f"semantic-verify: {type(error).__name__}: {error}", file=sys.stderr)
        return 3

    if arguments.format == "json":
        sys.stdout.write(report.to_json(include_ir=not arguments.no_ir))
    elif arguments.format == "ir":
        sys.stdout.write(dump_module(report.module))
    else:
        sys.stdout.write(dump_results(report))

    statuses = {result.status for result in report.results}
    if VerificationStatus.SOLVER_ERROR in statuses:
        return 3
    if VerificationStatus.VIOLATED in statuses:
        return 1
    if statuses & {VerificationStatus.UNKNOWN, VerificationStatus.UNSUPPORTED}:
        return 2
    return 0
