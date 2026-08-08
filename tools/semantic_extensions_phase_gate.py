"""Run the deterministic A6 semantic-extension phase gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.invariant_research import (  # noqa: E402
    SpacerRunner,
    render_artifact,
    run_corpus,
)
from semantic_verifier.model import SCHEMA  # noqa: E402
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from tools.integer_phase_gate import run_gate as run_integer_gate  # noqa: E402
from tools.regenerate_fixtures import (  # noqa: E402
    DEFAULT_OUTPUT,
    check_artifacts,
    generate,
)


GATE_SCHEMA = "codeskeptic.semantic-extensions-phase-gate/v1"
COMBINED_SLICE = ROOT / "examples" / "semantic_extensions_gate.cpp"
INFERENCE_MANIFEST = (
    ROOT / "benchmarks" / "invariant_inference" / "benchmarks.json"
)
INFERENCE_EXPECTED = INFERENCE_MANIFEST.with_name("expected_candidates.json")

FEATURES: dict[str, dict[str, Any]] = {
    "arrays": {
        "logic": "QF_ALIA/QF_ABV",
        "source": "array_slice.cpp",
        "verified": 18,
        "both_verified": 2,
        "both_unsupported": 16,
    },
    "bitwise_shifts": {
        "logic": "QF_BV",
        "source": "bitwise_slice.cpp",
        "verified": 19,
        "both_verified": 7,
        "both_unsupported": 12,
    },
    "fixed_signed": {
        "logic": "QF_LIA",
        "source": "int64_slice.cpp",
        "verified": 22,
        "both_verified": 22,
        "both_unsupported": 0,
    },
    "fixed_unsigned": {
        "logic": "QF_BV",
        "source": "unsigned_slice.cpp",
        "verified": 20,
        "both_verified": 1,
        "both_unsupported": 19,
    },
    "frames": {
        "logic": "QF_LIA/QF_RECORD",
        "source": "frame_conditions.cpp",
        "verified": 10,
        "both_verified": 5,
        "both_unsupported": 5,
    },
    "references": {
        "logic": "QF_LIA/QF_RECORD",
        "source": "reference_slice.cpp",
        "verified": 6,
        "both_verified": 2,
        "both_unsupported": 4,
    },
    "value_structs": {
        "logic": "QF_RECORD",
        "source": "struct_slice.cpp",
        "verified": 9,
        "both_verified": 0,
        "both_unsupported": 9,
    },
}
NEGATIVE_BOUNDARY = {
    "array_element_reference": (
        "int f() { int values[2] = {1, 2}; "
        "int &item = values[0]; return item; }\n"
    ),
    "dynamic_array": "int f(int n) { int values[n]; return 0; }\n",
    "missing_frame": (
        "void mutate(int &value); "
        "int f() { int value = 0; mutate(value); return value; }\n"
    ),
    "pointer": "int f(int *value) { return *value; }\n",
    "short_type": "short f(short value) { return value; }\n",
}


def _summary(*, verified: int, unsupported: int = 0) -> dict[str, int]:
    return {
        "solver_error": 0,
        "unknown": 0,
        "unsupported": unsupported,
        "verified": verified,
        "violated": 0,
    }


def _feature_matrix(
    *, clang: str | None, z3: str | None
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for feature, policy in sorted(FEATURES.items()):
        path = ROOT / "examples" / policy["source"]
        source = path.read_text(encoding="utf-8")
        display = f"examples/{policy['source']}"
        z3_report = VerificationPipeline(
            clang=clang,
            checker=create_backend("z3", z3=z3),
        ).verify_source(source, display)
        both_report = VerificationPipeline(
            clang=clang,
            checker=create_backend("both", z3=z3),
        ).verify_source(source, display)
        expected_z3 = _summary(verified=policy["verified"])
        expected_both = _summary(
            verified=policy["both_verified"],
            unsupported=policy["both_unsupported"],
        )
        if z3_report.summary() != expected_z3:
            raise RuntimeError(
                f"{feature} capable-backend summary changed: {z3_report.summary()}"
            )
        if both_report.summary() != expected_both:
            raise RuntimeError(
                f"{feature} cross-check summary changed: {both_report.summary()}"
            )
        if any(
            result.status.value != "verified" for result in z3_report.results
        ):
            raise RuntimeError(f"{feature} capable backend did not verify every result")
        if policy["both_unsupported"] and not any(
            result.status.value == "unsupported" for result in both_report.results
        ):
            raise RuntimeError(f"{feature} cross-check hid an unsupported result")
        evidence[feature] = {
            "capable_backend": "z3",
            "capable_report_sha256": _sha256_text(z3_report.to_json()),
            "capable_summary": z3_report.summary(),
            "default_backend": "both",
            "default_summary": both_report.summary(),
            "logic": policy["logic"],
            "source": display,
            "source_sha256": _sha256_text(source),
        }
    return evidence


def _combined_slice(
    *, clang: str | None, z3: str | None
) -> dict[str, Any]:
    source = COMBINED_SLICE.read_text(encoding="utf-8")
    display = "examples/semantic_extensions_gate.cpp"
    z3_report = VerificationPipeline(
        clang=clang,
        checker=create_backend("z3", z3=z3),
    ).verify_source(source, display)
    both_report = VerificationPipeline(
        clang=clang,
        checker=create_backend("both", z3=z3),
    ).verify_source(source, display)
    expected_z3 = _summary(verified=8)
    expected_both = _summary(verified=0, unsupported=8)
    if z3_report.summary() != expected_z3:
        raise RuntimeError(f"combined capable summary changed: {z3_report.summary()}")
    if both_report.summary() != expected_both:
        raise RuntimeError(f"combined default summary changed: {both_report.summary()}")
    if not all(result.status.value == "verified" for result in z3_report.results):
        raise RuntimeError("combined slice was not fully verified by Z3")
    if not all(result.status.value == "unsupported" for result in both_report.results):
        raise RuntimeError("combined cross-check did not fail closed")
    return {
        "capable_report_sha256": _sha256_text(z3_report.to_json()),
        "capable_summary": z3_report.summary(),
        "default_report_sha256": _sha256_text(both_report.to_json()),
        "default_summary": both_report.summary(),
        "obligation_kinds": sorted({result.kind for result in z3_report.results}),
        "source": display,
        "source_sha256": _sha256_text(source),
    }


def _negative_boundary(
    *, clang: str | None, z3: str | None
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for name, source in sorted(NEGATIVE_BOUNDARY.items()):
        report = VerificationPipeline(
            clang=clang,
            checker=create_backend("both", z3=z3),
        ).verify_source(source, f"negative/{name}.cpp")
        summary = report.summary()
        if not report.results or any(
            result.status.value != "unsupported" for result in report.results
        ):
            raise RuntimeError(f"negative boundary {name} did not fail closed")
        evidence[name] = {
            "reasons": sorted({result.message for result in report.results}),
            "source_sha256": _sha256_text(source),
            "summary": summary,
        }
    return evidence


def _fixture_evidence(*, z3: str | None) -> dict[str, Any]:
    first = generate(z3=z3)
    second = generate(z3=z3)
    if first != second:
        raise RuntimeError("fixture regeneration was not byte-identical")
    mismatches = check_artifacts(DEFAULT_OUTPUT, first)
    if mismatches:
        raise RuntimeError("current fixture mismatch: " + "; ".join(mismatches))
    hashes = {
        path.as_posix(): hashlib.sha256(content).hexdigest()
        for path, content in sorted(first.items(), key=lambda item: item[0].as_posix())
    }
    return {
        "artifacts": len(first),
        "combined_sha256": _hash_artifacts(first),
        "files": hashes,
        "regenerations_byte_identical": True,
    }


def _hash_artifacts(artifacts: dict[PurePosixPath, bytes]) -> str:
    digest = hashlib.sha256()
    for path, content in sorted(artifacts.items(), key=lambda item: item[0].as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _inference_evidence(*, z3: str | None) -> dict[str, Any]:
    runner = SpacerRunner(z3=z3, timeout_seconds=2.0)
    artifact = run_corpus(INFERENCE_MANIFEST, runner=runner)
    rendered = render_artifact(artifact)
    expected = INFERENCE_EXPECTED.read_text(encoding="utf-8")
    if rendered != expected:
        raise RuntimeError("invariant research artifact changed")
    cases = {item["id"]: item for item in artifact["cases"]}
    expected_statuses = {
        "count_exact": "useful",
        "count_insufficient": "insufficient",
        "malformed": "malformed",
        "timeout": "timeout",
        "unsafe": "no_candidate",
        "unsupported": "unsupported",
    }
    actual_statuses = {name: cases[name]["status"] for name in sorted(cases)}
    if actual_statuses != expected_statuses:
        raise RuntimeError(f"invariant research outcomes changed: {actual_statuses}")
    exact = cases["count_exact"]["validation"]
    insufficient = cases["count_insufficient"]["validation"]
    if not (
        exact["machine_proposed"]
        and exact["inductive"]
        and exact["accepted"]
        and insufficient["machine_proposed"]
        and insufficient["inductive"]
        and not insufficient["accepted"]
    ):
        raise RuntimeError("invariant proposal referee boundary changed")
    return {
        "artifact_sha256": _sha256_text(rendered),
        "ordinary_referee": {
            "insufficient_accepted": insufficient["accepted"],
            "insufficient_inductive": insufficient["inductive"],
            "useful_accepted": exact["accepted"],
            "useful_inductive": exact["inductive"],
        },
        "statuses": actual_statuses,
    }


def run_gate(
    *, clang: str | None = None, z3: str | None = None
) -> dict[str, Any]:
    integer_gate = run_integer_gate(clang=clang, z3=z3)
    migration = integer_gate["migration"]
    archive_v1 = migration["archive_v1"]
    if not archive_v1["valid"] or archive_v1["entries"] != 16:
        raise RuntimeError("legacy v1 archive changed")
    if integer_gate["combined_slice"]["violations_replayed"] != 13:
        raise RuntimeError("capable-backend counterexample replay changed")
    return {
        "backend_capability_matrix": _feature_matrix(clang=clang, z3=z3),
        "combined_slice": _combined_slice(clang=clang, z3=z3),
        "fixtures": _fixture_evidence(z3=z3),
        "inference": _inference_evidence(z3=z3),
        "migration": migration,
        "negative_boundary": _negative_boundary(clang=clang, z3=z3),
        "report_schema": SCHEMA,
        "replay": {
            "integer_gate_report_sha256": integer_gate["combined_slice"][
                "report_sha256"
            ],
            "violations_replayed": integer_gate["combined_slice"][
                "violations_replayed"
            ],
        },
        "schema": GATE_SCHEMA,
    }


def render_gate(
    *, clang: str | None = None, z3: str | None = None
) -> str:
    return json.dumps(
        run_gate(clang=clang, z3=z3),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", help="explicit Clang executable")
    parser.add_argument("--z3", help="explicit Z3 executable")
    parser.add_argument(
        "--output",
        type=Path,
        help="write the canonical gate artifact instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        rendered = render_gate(clang=arguments.clang, z3=arguments.z3)
        if arguments.output is None:
            sys.stdout.write(rendered)
        else:
            arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
        return 0
    except Exception as error:
        print(f"semantic-extension phase gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
