"""Run the deterministic A5 scaling, cache, and budget phase gate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import CheckerBackend, create_backend  # noqa: E402
from semantic_verifier.budget import FileCheckBudget  # noqa: E402
from semantic_verifier.model import (  # noqa: E402
    Obligation,
    VerificationReport,
    VerificationResult,
)
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from tools.path_scaling_probe import run_probe  # noqa: E402


GATE_SCHEMA = "codeskeptic.scaling-phase-gate/v0"
SLICE = ROOT / "examples" / "scaling_slice.cpp"


class _CountingChecker(CheckerBackend):
    def __init__(self, backend: CheckerBackend) -> None:
        self.backend = backend
        self.name = backend.name
        self.calls = 0

    def cache_identity(self) -> Mapping[str, object]:
        return self.backend.cache_identity()

    def check(self, obligation: Obligation) -> VerificationResult:
        self.calls += 1
        return self.backend.check(obligation)


def _run_report(
    source: str,
    *,
    backend_name: str,
    z3: str | None,
    cache_path: Path | None = None,
    budget: FileCheckBudget | None = None,
) -> tuple[VerificationReport, int]:
    counted = _CountingChecker(create_backend(backend_name, z3=z3))
    report = VerificationPipeline(
        checker=counted,
        cache_path=cache_path,
        check_budget=budget,
    ).verify_source(source, "examples/scaling_slice.cpp")
    return report, counted.calls


def run_gate(
    *,
    backend_name: str = "both",
    z3: str | None = None,
    budget_checks: int = 5,
) -> dict[str, object]:
    if backend_name not in {"affine", "z3", "both"}:
        raise ValueError(f"unknown backend {backend_name!r}")
    budget = FileCheckBudget(budget_checks)
    source = SLICE.read_text(encoding="utf-8")

    uncached, uncached_calls = _run_report(
        source,
        backend_name=backend_name,
        z3=z3,
    )
    with tempfile.TemporaryDirectory() as temporary:
        cache_path = Path(temporary) / "results.json"
        cache_fill, cache_fill_calls = _run_report(
            source,
            backend_name=backend_name,
            z3=z3,
            cache_path=cache_path,
        )
        warm, warm_calls = _run_report(
            source,
            backend_name=backend_name,
            z3=z3,
            cache_path=cache_path,
        )

    uncached_json = uncached.to_json()
    if not uncached_json == cache_fill.to_json() == warm.to_json():
        raise RuntimeError("uncached, cache-fill, and warm reports differ")
    if warm_calls != 0:
        raise RuntimeError(f"warm cache invoked the backend {warm_calls} times")

    first_budgeted, first_budget_calls = _run_report(
        source,
        backend_name=backend_name,
        z3=z3,
        budget=budget,
    )
    second_budgeted, second_budget_calls = _run_report(
        source,
        backend_name=backend_name,
        z3=z3,
        budget=budget,
    )
    budgeted_json = first_budgeted.to_json()
    if budgeted_json != second_budgeted.to_json():
        raise RuntimeError("repeated budgeted reports differ")

    probe = run_probe((1, 2, 4, 8))
    assertion_counts = [
        item["assertion_obligations"] for item in probe["cases"]
    ]
    if assertion_counts != [1, 1, 1, 1]:
        raise RuntimeError(
            f"merge target regressed: expected [1, 1, 1, 1], got {assertion_counts}"
        )

    return {
        "backend": backend_name,
        "budget": {
            "byte_identical": True,
            "first_backend_calls": first_budget_calls,
            "max_checks": budget_checks,
            "report_sha256": _sha256(budgeted_json),
            "second_backend_calls": second_budget_calls,
            "summary": first_budgeted.summary(),
        },
        "cache": {
            "byte_identical": True,
            "cache_fill_backend_calls": cache_fill_calls,
            "report_sha256": _sha256(uncached_json),
            "uncached_backend_calls": uncached_calls,
            "warm_backend_calls": warm_calls,
        },
        "path_probe": {
            "assertion_obligations": assertion_counts,
            "expected_paths": [item["expected_paths"] for item in probe["cases"]],
            "target_met": True,
        },
        "scaling_slice": {
            "obligations": len(uncached.obligations),
            "source_sha256": _sha256(source),
            "summary": uncached.summary(),
        },
        "schema": GATE_SCHEMA,
    }


def render_gate(
    *,
    backend_name: str = "both",
    z3: str | None = None,
    budget_checks: int = 5,
) -> str:
    return (
        json.dumps(
            run_gate(
                backend_name=backend_name,
                z3=z3,
                budget_checks=budget_checks,
            ),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("affine", "z3", "both"),
        default="both",
        help="checker backend used by the gate (default: both)",
    )
    parser.add_argument("--z3", help="explicit Z3 executable")
    parser.add_argument(
        "--max-checks",
        type=int,
        default=5,
        help="budgeted-run supported check limit (default: 5)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        sys.stdout.write(
            render_gate(
                backend_name=arguments.backend,
                z3=arguments.z3,
                budget_checks=arguments.max_checks,
            )
        )
        return 0
    except Exception as error:
        print(f"scaling phase gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
