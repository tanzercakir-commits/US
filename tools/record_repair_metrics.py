"""Record append-only timed repair metrics or summarize a ledger."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.budget import SolverTimeout  # noqa: E402
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from semantic_verifier.repair_bundle import (  # noqa: E402
    RepairBundleError,
    load_repair_bundle_json,
)
from semantic_verifier.repair_loop import (  # noqa: E402
    RepairHarness,
    RepairLoopError,
    ScriptedPatchProposer,
    load_patch_script_json,
)
from semantic_verifier.repair_metrics import (  # noqa: E402
    RepairMetricsError,
    append_metric,
    load_metrics_jsonl,
    measure_repair,
    summary_json,
)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record or summarize repair metrics."
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )
    record = commands.add_parser("record")
    record.add_argument("source")
    record.add_argument("bundle")
    record.add_argument("script")
    record.add_argument("loop_output")
    record.add_argument("ledger")
    record.add_argument("--display-path", required=True)
    record.add_argument("--max-iterations", type=int, default=3)
    record.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="affine",
    )
    record.add_argument("--clang")
    record.add_argument("--z3")
    record.add_argument("--solver-timeout", type=float, default=5.0)
    summary = commands.add_parser("summary")
    summary.add_argument("ledger")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "summary":
            rows = load_metrics_jsonl(
                Path(arguments.ledger).read_bytes().decode("utf-8")
            )
            sys.stdout.write(summary_json(rows))
            return 0

        source = Path(arguments.source).read_bytes().decode("utf-8")
        checker = create_backend(
            arguments.backend,
            z3=arguments.z3,
            timeout_seconds=SolverTimeout(
                arguments.solver_timeout
            ),
        )
        report = VerificationPipeline(
            arguments.clang,
            checker=checker,
        ).verify_source(source, arguments.display_path)
        bundle = load_repair_bundle_json(
            Path(arguments.bundle).read_bytes().decode("utf-8"),
            source=source,
            report=report,
        )
        proposer = ScriptedPatchProposer(
            load_patch_script_json(
                Path(arguments.script).read_bytes().decode("utf-8")
            )
        )
        harness = RepairHarness(
            proposer,
            clang=arguments.clang,
            checker=checker,
            referee=f"codeskeptic.{arguments.backend}/v1",
            max_iterations=arguments.max_iterations,
        )
        loop, metric = measure_repair(
            lambda: harness.run(
                source,
                arguments.display_path,
                bundle,
            ),
            bundle,
            clock_ns=time.perf_counter_ns,
        )
        append_metric(arguments.ledger, metric)
        _atomic_write(
            Path(arguments.loop_output),
            loop.to_json().encode("utf-8"),
        )
        sys.stdout.write(metric.to_json_line())
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        RepairBundleError,
        RepairLoopError,
        RepairMetricsError,
    ) as error:
        print(f"repair-metrics error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
