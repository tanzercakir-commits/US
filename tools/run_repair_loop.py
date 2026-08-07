"""Run or check the bounded offline repair harness."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded scripted repair loop."
    )
    parser.add_argument("source")
    parser.add_argument("bundle")
    parser.add_argument("script")
    parser.add_argument("output")
    parser.add_argument("--display-path", required=True)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="affine",
    )
    parser.add_argument("--clang")
    parser.add_argument("--z3")
    parser.add_argument("--solver-timeout", type=float, default=5.0)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)

    try:
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
        proposals = load_patch_script_json(
            Path(arguments.script).read_bytes().decode("utf-8")
        )
        log = RepairHarness(
            ScriptedPatchProposer(proposals),
            clang=arguments.clang,
            checker=checker,
            referee=f"codeskeptic.{arguments.backend}/v1",
            max_iterations=arguments.max_iterations,
        ).run(source, arguments.display_path, bundle)
        rendered = log.to_json().encode("utf-8")
        output = Path(arguments.output)
        if arguments.check:
            if output.read_bytes() != rendered:
                print(
                    "repair-loop check failed: content differs",
                    file=sys.stderr,
                )
                return 1
        else:
            _atomic_write(output, rendered)
    except (
        OSError,
        UnicodeError,
        ValueError,
        RepairBundleError,
        RepairLoopError,
    ) as error:
        print(f"repair-loop error: {error}", file=sys.stderr)
        return 2

    print(
        f"repair loop {log.id}: {log.status} "
        f"after {len(log.attempts)} attempt(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
