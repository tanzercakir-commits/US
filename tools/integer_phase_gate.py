"""Run the deterministic A6.12 fixed-width integer phase gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.integer_types import (  # noqa: E402
    FIXED_INTEGER_TYPES,
    TARGET_PROFILE,
    convert_integer,
    usual_arithmetic_type,
)
from semantic_verifier.model import (  # noqa: E402
    SCHEMA,
    Expr,
    Obligation,
    SourceLocation,
    VerificationResult,
)
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from semantic_verifier.query_fragment import (  # noqa: E402
    classify_obligation,
)
from semantic_verifier.smtlib import emit_smtlib  # noqa: E402


GATE_SCHEMA = "codeskeptic.fixed-integer-phase-gate/v3"
SLICE = ROOT / "examples" / "fixed_integer_gate.cpp"
V1_ARCHIVE = ROOT / "fixtures" / "versions" / "v1"
V2_ARCHIVE = ROOT / "fixtures" / "versions" / "v2"
V3_ARCHIVE = ROOT / "fixtures" / "versions" / "v3"
V4_ARCHIVE = ROOT / "fixtures" / "versions" / "v4"
CURRENT_FIXTURES = ROOT / "fixtures" / "expected"
EXPECTED_SUMMARY = {
    "solver_error": 0,
    "unknown": 0,
    "unsupported": 0,
    "verified": 47,
    "violated": 13,
}


Evidence = tuple[str, str, str]
TRUTH_TABLE_EXPECTATIONS: dict[str, dict[str, tuple[Evidence, ...]]] = {
    "signed_add_subtract_multiply": {
        "positive": (
            ("signed_add_safe", "signed_overflow", "verified"),
            ("signed_subtract_safe", "signed_overflow", "verified"),
            ("signed_multiply_safe", "signed_overflow", "verified"),
        ),
        "negative": (
            ("signed_add_overflow", "signed_overflow", "violated"),
            ("signed_subtract_overflow", "signed_overflow", "violated"),
            ("signed_multiply_overflow", "signed_overflow", "violated"),
        ),
    },
    "unsigned_add_subtract_multiply": {
        "positive": (
            ("unsigned_wrap", "postcondition", "verified"),
            ("unsigned_subtract_wrap", "postcondition", "verified"),
            ("unsigned_multiply_wrap", "postcondition", "verified"),
        ),
        "negative": (("unsigned_wrap_wrong", "postcondition", "violated"),),
    },
    "unary_negation": {
        "positive": (
            ("signed_negation_safe", "postcondition", "verified"),
            ("unsigned_negation", "postcondition", "verified"),
        ),
        "negative": (
            ("signed_negation_minimum", "signed_overflow", "violated"),
        ),
    },
    "division_remainder": {
        "positive": (
            ("division_safe", "postcondition", "verified"),
            ("remainder_safe", "postcondition", "verified"),
        ),
        "negative": (
            ("division_zero", "division_by_zero", "violated"),
            ("division_overflow", "signed_overflow", "violated"),
        ),
    },
    "equality_relational": {
        "positive": (
            ("signed_comparison", "postcondition", "verified"),
            ("mixed_comparison", "postcondition", "verified"),
        ),
        "negative": (
            ("mixed_comparison_wrong", "postcondition", "violated"),
        ),
    },
    "bitwise": {
        "positive": (
            ("de_morgan", "postcondition", "verified"),
            ("xor_identity", "postcondition", "verified"),
        ),
        "negative": (("bitwise_wrong", "postcondition", "violated"),),
    },
    "left_shift": {
        "positive": (
            ("signed_left_boundary", "signed_left_shift", "verified"),
        ),
        "negative": (
            ("left_count_invalid", "shift_count", "violated"),
            (
                "signed_left_value_invalid",
                "signed_left_shift",
                "violated",
            ),
        ),
    },
    "right_shift": {
        "positive": (
            ("arithmetic_right", "postcondition", "verified"),
            ("logical_right", "postcondition", "verified"),
        ),
        "negative": (("right_count_invalid", "shift_count", "violated"),),
    },
}


def _obligation(conclusion: Expr) -> Obligation:
    return Obligation(
        id="ob00001",
        function="phase_gate",
        kind="postcondition",
        assumptions=(),
        conclusion=conclusion,
        location=SourceLocation("integer-phase-gate.cpp", 1, 1),
        description="integer phase-gate capability probe",
    )


def _capability_obligations() -> tuple[Obligation, Obligation]:
    signed = Expr.variable("signed#0", "i32")
    lia = _obligation(Expr.binary("==", signed, signed))
    unsigned = Expr.variable("unsigned#0", "u32")
    masked = Expr.binary("&", unsigned, unsigned, "u32")
    bv = _obligation(Expr.binary("==", masked, unsigned))
    return lia, bv


def _backend_matrix(
    lia: Obligation, bv: Obligation, *, z3: str | None
) -> dict[str, dict[str, str]]:
    matrix: dict[str, dict[str, str]] = {}
    for backend_name in ("affine", "z3", "both"):
        backend = create_backend(backend_name, z3=z3)
        matrix[backend_name] = {
            "QF_BV": backend.check(bv).status.value,
            "QF_LIA": backend.check(lia).status.value,
        }
    expected = {
        "affine": {"QF_BV": "unsupported", "QF_LIA": "verified"},
        "both": {"QF_BV": "unsupported", "QF_LIA": "verified"},
        "z3": {"QF_BV": "verified", "QF_LIA": "verified"},
    }
    if matrix != expected:
        raise RuntimeError(f"backend capability matrix changed: {matrix}")
    return matrix


def _truth_table(results: tuple[VerificationResult, ...]) -> dict[str, object]:
    available = {
        (result.function, result.kind, result.status.value): result
        for result in results
    }
    evidence: dict[str, object] = {}
    for row, polarities in TRUTH_TABLE_EXPECTATIONS.items():
        row_evidence: dict[str, object] = {}
        for polarity, expected in polarities.items():
            missing = [item for item in expected if item not in available]
            if missing:
                raise RuntimeError(
                    f"truth-table evidence missing for {row}/{polarity}: {missing}"
                )
            row_evidence[polarity] = [
                {"function": item[0], "kind": item[1], "status": item[2]}
                for item in expected
            ]
        evidence[row] = row_evidence
    return evidence


def _archive_evidence(
    archive: Path, version: str
) -> dict[str, object]:
    manifest = archive / "SHA256SUMS"
    entries: list[tuple[str, str]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        actual = hashlib.sha256((archive / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"archived {version} hash changed: {relative}")
        entries.append((relative, actual))
    return {
        "entries": len(entries),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "valid": True,
    }


def _migration_evidence(
    archive: Path, migration: str
) -> dict[str, object]:
    old_reports = archive / "expected"
    cases: list[str] = []
    for old_path in sorted(old_reports.glob("*.report.json")):
        old = json.loads(old_path.read_text(encoding="utf-8"))
        new = json.loads(
            (CURRENT_FIXTURES / old_path.name).read_text(encoding="utf-8")
        )
        fields = ("obligation", "function", "kind", "status")
        old_statuses = [
            tuple(item[field] for field in fields) for item in old["results"]
        ]
        new_statuses = [
            tuple(item[field] for field in fields) for item in new["results"]
        ]
        if new["schema"] != SCHEMA or new_statuses != old_statuses:
            raise RuntimeError(f"{migration} status equivalence changed: {old_path.stem}")
        cases.append(old_path.stem.removesuffix(".report"))
    return {"cases": cases, "count": len(cases), "status_equivalent": True}


def _target_profile() -> dict[str, object]:
    types = {
        name: {
            "maximum": str(profile.maximum),
            "minimum": str(profile.minimum),
            "signed": profile.signed,
            "width": profile.width,
        }
        for name, profile in sorted(FIXED_INTEGER_TYPES.items())
    }
    names = ("i32", "u32", "i64", "u64")
    conversions = {
        left: {right: usual_arithmetic_type(left, right) for right in names}
        for left in names
    }
    assignment_samples = {
        "i32_minus_one_to_u32": str(convert_integer(-1, "u32")),
        "u32_max_to_i64": str(convert_integer(2**32 - 1, "i64")),
        "u64_max_to_i32": str(convert_integer(2**64 - 1, "i32")),
    }
    return {
        "assignment_samples": assignment_samples,
        "id": TARGET_PROFILE.id,
        "types": types,
        "usual_conversions": conversions,
        "validated_by_combined_slice": True,
    }


def run_gate(
    *, clang: str | None = None, z3: str | None = None
) -> dict[str, object]:
    source = SLICE.read_text(encoding="utf-8")
    report = VerificationPipeline(
        clang=clang,
        checker=create_backend("z3", z3=z3),
    ).verify_source(source, "examples/fixed_integer_gate.cpp")
    if report.summary() != EXPECTED_SUMMARY:
        raise RuntimeError(
            f"combined integer summary changed: {report.summary()}"
        )
    violated = [
        result for result in report.results if result.status.value == "violated"
    ]
    if not all("replayed" in result.message for result in violated):
        raise RuntimeError("combined integer violation did not replay")

    lia, bv = _capability_obligations()
    lia_query = emit_smtlib(lia)
    bv_query = emit_smtlib(bv)
    if "(set-logic QF_LIA)" not in lia_query or "BitVec" in lia_query:
        raise RuntimeError("QF_LIA classifier/emission changed")
    if "(set-logic QF_BV)" not in bv_query or " Int" in bv_query:
        raise RuntimeError("QF_BV classifier/emission changed")

    report_json = report.to_json()
    return {
        "backend_matrix": _backend_matrix(lia, bv, z3=z3),
        "classifier": {
            "bitvector": classify_obligation(bv).value,
            "bitvector_query_sha256": _sha256(bv_query),
            "signed_linear": classify_obligation(lia).value,
            "signed_linear_query_sha256": _sha256(lia_query),
        },
        "combined_slice": {
            "obligations": len(report.obligations),
            "report_sha256": _sha256(report_json),
            "source_sha256": _sha256(source),
            "summary": report.summary(),
            "violations_replayed": len(violated),
        },
        "migration": {
            "archive_v1": _archive_evidence(V1_ARCHIVE, "v1"),
            "archive_v2": _archive_evidence(V2_ARCHIVE, "v2"),
            "archive_v3": _archive_evidence(V3_ARCHIVE, "v3"),
            "archive_v4": _archive_evidence(V4_ARCHIVE, "v4"),
            "v1_to_v5": _migration_evidence(V1_ARCHIVE, "v1/v5"),
            "v2_to_v5": _migration_evidence(V2_ARCHIVE, "v2/v5"),
            "v3_to_v5": _migration_evidence(V3_ARCHIVE, "v3/v5"),
            "v4_to_v5": _migration_evidence(V4_ARCHIVE, "v4/v5"),
        },
        "schema": GATE_SCHEMA,
        "target_profile": _target_profile(),
        "truth_table": _truth_table(report.results),
    }


def render_gate(
    *, clang: str | None = None, z3: str | None = None
) -> str:
    return (
        json.dumps(
            run_gate(clang=clang, z3=z3),
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
    parser.add_argument("--clang", help="explicit Clang executable")
    parser.add_argument("--z3", help="explicit Z3 executable")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        sys.stdout.write(render_gate(clang=arguments.clang, z3=arguments.z3))
        return 0
    except Exception as error:
        print(f"integer phase gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
