"""Generate or check one replay-attested repair bundle."""

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
from semantic_verifier.model import VerificationStatus  # noqa: E402
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from semantic_verifier.repair_bundle import (  # noqa: E402
    RepairBundleBuilder,
    RepairBundleError,
)


def _write_atomic(path: Path, data: bytes) -> None:
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
        description="Generate a replay-attested repair bundle."
    )
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--display-path", required=True)
    parser.add_argument("--obligation")
    parser.add_argument(
        "--context-lines",
        type=int,
        default=4,
    )
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
        obligation_id = arguments.obligation
        if obligation_id is None:
            candidates = sorted(
                (
                    result.obligation_id
                    for result in report.results
                    if (
                        result.status
                        == VerificationStatus.VIOLATED
                        and result.counterexample
                    )
                )
            )
            if not candidates:
                raise RepairBundleError(
                    "report has no violated result with counterexample"
                )
            obligation_id = candidates[0]
        bundle = RepairBundleBuilder(
            arguments.clang,
            checker=checker,
            referee=f"codeskeptic.{arguments.backend}/v1",
            context_lines=arguments.context_lines,
        ).build(
            source,
            arguments.display_path,
            report,
            obligation_id,
        )
        rendered = bundle.to_json().encode("utf-8")
        output = Path(arguments.output)
        if arguments.check:
            try:
                actual = output.read_bytes()
            except OSError as error:
                raise RepairBundleError(
                    f"cannot read expected bundle: {error}"
                ) from error
            if actual != rendered:
                print(
                    "repair-bundle check failed: content differs",
                    file=sys.stderr,
                )
                return 1
        else:
            _write_atomic(output, rendered)
    except (
        OSError,
        UnicodeError,
        ValueError,
        RepairBundleError,
    ) as error:
        print(f"repair-bundle error: {error}", file=sys.stderr)
        return 2

    print(
        f"repair bundle {bundle.id} ({bundle.result['obligation']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
