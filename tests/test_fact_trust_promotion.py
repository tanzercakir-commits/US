from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.backend import CheckerBackend
from semantic_verifier.fact_trust import (
    FACT_TRUST_SCHEMA,
    load_fact_trust_json,
    verification_sha256,
)
from semantic_verifier.fact_trust_promotion import (
    FactTrustPromotionError,
    FactTrustPromotionPipeline,
    write_promotion_artifacts,
)
from semantic_verifier.model import (
    Obligation,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "fact_trust"
SOURCE = FIXTURE / "source.cpp"
EXPECTED = FIXTURE / "expected"
DISPLAY = "fixtures/fact_trust/source.cpp"


class StatusBackend(CheckerBackend):
    name = "test-status"

    def __init__(self, status: VerificationStatus) -> None:
        self.status = status

    def check(self, obligation: Obligation) -> VerificationResult:
        return VerificationResult(
            obligation.id,
            obligation.function,
            obligation.kind,
            self.status,
            obligation.location,
            f"test status: {self.status.value}",
        )




def _claims_by_name(result):
    names = {
        symbol.id: symbol.qualified_name
        for symbol in result.fact_index.symbols
        if symbol.kind == "function"
    }
    return {
        names[claim.function]: claim
        for claim in result.trust.claims
    }


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.as_posix(),
        )
    }


def _qualified_source(
    *,
    frame: str = "// cs: modifies\n",
    ensures: str = "// cs: ensures result == value\n",
    body: str = "return value;",
) -> str:
    return (
        frame
        + ensures
        + "int candidate(int value) { "
        + body
        + " }\n"
    )


class FactTrustPromotionTests(unittest.TestCase):
    def test_fixture_proves_leaf_and_direct_call_chain(self) -> None:
        result = FactTrustPromotionPipeline().promote_file(
            SOURCE,
            display_path=DISPLAY,
        )
        claims = _claims_by_name(result)
        self.assertEqual(claims["leaf"].trust, "proved")
        self.assertEqual(claims["caller"].trust, "proved")
        self.assertEqual(claims["no_frame"].trust, "derived")
        self.assertEqual(
            claims["zero_obligations"].trust,
            "derived",
        )
        self.assertEqual(
            result.summary(),
            json.loads(
                (EXPECTED / "promotion-run.json").read_text(
                    encoding="utf-8"
                )
            ),
        )
        self.assertEqual(
            result.artifacts(),
            {
                name: (EXPECTED / name).read_bytes()
                for name in (
                    "fact-index.json",
                    "fact-trust.json",
                    "verification.json",
                )
            },
        )

    def test_evidence_links_exact_source_report_obligations_and_callees(
        self,
    ) -> None:
        result = FactTrustPromotionPipeline().promote_file(
            SOURCE,
            display_path=DISPLAY,
        )
        claims = _claims_by_name(result)
        report_hash = verification_sha256(
            result.verification.to_json().encode("utf-8")
        )
        ids_by_name = {
            symbol.qualified_name: symbol.id
            for symbol in result.fact_index.symbols
            if symbol.kind == "function"
        }
        for name in ("leaf", "caller"):
            evidence = claims[name].evidence
            self.assertEqual(
                evidence.source_sha256,
                result.fact_index.source.content_sha256,
            )
            self.assertEqual(
                evidence.verification_sha256,
                report_hash,
            )
            expected_ids = tuple(
                sorted(
                    obligation.id
                    for obligation in result.verification.obligations
                    if obligation.function == name
                )
            )
            self.assertEqual(evidence.obligations, expected_ids)
        self.assertEqual(claims["leaf"].evidence.callees, ())
        self.assertEqual(
            claims["caller"].evidence.callees,
            (ids_by_name["leaf"],),
        )
        self.assertEqual(
            load_fact_trust_json(
                result.trust.to_json(),
                result.fact_index,
            ),
            result.trust,
        )

    def test_frontend_unit_is_parsed_once_for_both_artifacts(self) -> None:
        pipeline = FactTrustPromotionPipeline()
        original = pipeline.extractor.frontend.parse_source
        with patch.object(
            pipeline.extractor.frontend,
            "parse_source",
            wraps=original,
        ) as parsed:
            result = pipeline.promote_source(
                _qualified_source(),
                "trust/once.cpp",
            )
        self.assertEqual(parsed.call_count, 1)
        self.assertEqual(
            result.fact_index.source.file,
            result.verification.module.source,
        )

    def test_absent_nonempty_and_machine_frames_do_not_promote(self) -> None:
        cases = {
            "absent": _qualified_source(frame=""),
            "machine": _qualified_source(
                frame="// cs: ai modifies\n"
            ),
            "nonempty-external": (
                "// cs: modifies value\n"
                "// cs: ensures result == value\n"
                "int candidate(int &value);\n"
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                result = FactTrustPromotionPipeline().promote_source(
                    source,
                    f"trust/{name}.cpp",
                )
                self.assertTrue(
                    all(
                        claim.trust == "derived"
                        for claim in result.trust.claims
                    )
                )

    def test_zero_incomplete_unknown_and_solver_error_results_do_not_promote(
        self,
    ) -> None:
        pipeline = FactTrustPromotionPipeline()
        zero = pipeline.promote_source(
            _qualified_source(ensures=""),
            "trust/zero.cpp",
        )
        self.assertEqual(
            _claims_by_name(zero)["candidate"].trust,
            "derived",
        )

        base = pipeline.promote_source(
            _qualified_source(),
            "trust/result-boundary.cpp",
        )
        reports = [
            VerificationReport(
                base.verification.module,
                base.verification.obligations,
                (),
            )
        ]
        for status in (
            VerificationStatus.UNKNOWN,
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.SOLVER_ERROR,
        ):
            reports.append(
                VerificationReport(
                    base.verification.module,
                    base.verification.obligations,
                    tuple(
                        replace(result, status=status)
                        for result in base.verification.results
                    ),
                )
            )
        names = {
            symbol.id: symbol.qualified_name
            for symbol in base.fact_index.symbols
            if symbol.kind == "function"
        }
        for report in reports:
            with self.subTest(results=report.results):
                trust = pipeline._promote(
                    base.fact_index,
                    report,
                )
                claim = next(
                    claim
                    for claim in trust.claims
                    if names[claim.function] == "candidate"
                )
                self.assertEqual(claim.trust, "derived")

    def test_referee_identity_is_bound_to_exact_builtin_checker(self) -> None:
        with self.assertRaisesRegex(
            FactTrustPromotionError,
            "not an admitted proof referee",
        ):
            FactTrustPromotionPipeline(
                checker=StatusBackend(
                    VerificationStatus.VERIFIED
                )
            )
        with self.assertRaisesRegex(
            FactTrustPromotionError,
            "does not match",
        ):
            FactTrustPromotionPipeline(
                referee="codeskeptic.z3/v1"
            )

    def test_violated_contract_remains_derived(self) -> None:
        result = FactTrustPromotionPipeline().promote_source(
            _qualified_source(
                ensures="// cs: ensures result != value\n"
            ),
            "trust/violated.cpp",
        )
        claim = _claims_by_name(result)["candidate"]
        self.assertEqual(claim.trust, "derived")
        self.assertIn(
            VerificationStatus.VIOLATED,
            {item.status for item in result.verification.results},
        )

    def test_impure_and_unknown_d1_values_never_promote(self) -> None:
        impure_source = (
            "int state = 0;\n"
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int candidate(int value) { state = value; return value; }\n"
        )
        unknown_source = (
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int candidate(int value, int (*fn)(int)) { "
            "return fn(value); }\n"
        )
        for name, source in (
            ("impure", impure_source),
            ("unknown", unknown_source),
        ):
            with self.subTest(name=name):
                result = FactTrustPromotionPipeline().promote_source(
                    source,
                    f"trust/{name}.cpp",
                )
                claims = _claims_by_name(result)
                self.assertNotEqual(
                    claims["candidate"].value,
                    "pure",
                )
                self.assertEqual(
                    claims["candidate"].trust,
                    "derived",
                )

    def test_external_or_derived_direct_callee_blocks_caller(self) -> None:
        source = (
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int external(int value);\n"
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int caller(int value) { "
            "int output = external(value); return output; }\n"
        )
        result = FactTrustPromotionPipeline().promote_source(
            source,
            "trust/external.cpp",
        )
        claims = _claims_by_name(result)
        self.assertEqual(claims["external"].trust, "derived")
        self.assertEqual(claims["caller"].trust, "derived")
        caller_result = next(
            item
            for item in result.verification.results
            if item.function == "caller"
        )
        self.assertEqual(
            caller_result.status,
            VerificationStatus.VERIFIED,
        )

    def test_module_limitation_blocks_otherwise_eligible_function(self) -> None:
        source = (
            "using Value = int;\n"
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int candidate(int value) { return value; }\n"
        )
        result = FactTrustPromotionPipeline().promote_source(
            source,
            "trust/module-limitation.cpp",
        )
        self.assertTrue(result.fact_index.limitations)
        self.assertEqual(
            _claims_by_name(result)["candidate"].trust,
            "derived",
        )

    def test_ambiguous_overload_names_fail_closed(self) -> None:
        source = (
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "int same(int value) { return value; }\n"
            "// cs: modifies\n"
            "// cs: ensures result == value\n"
            "long long same(long long value) { return value; }\n"
        )
        result = FactTrustPromotionPipeline().promote_source(
            source,
            "trust/overload.cpp",
        )
        same_claims = [
            claim
            for name, claim in _claims_by_name(result).items()
            if name == "same"
        ]
        self.assertTrue(
            all(claim.trust == "derived" for claim in same_claims)
        )
        self.assertTrue(
            all(
                claim.trust == "derived"
                for claim in result.trust.claims
            )
        )

    def test_relocated_files_are_byte_stable_with_frozen_display_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                first = Path(first_dir) / "source.cpp"
                second = Path(second_dir) / "source.cpp"
                shutil.copyfile(SOURCE, first)
                shutil.copyfile(SOURCE, second)
                first_result = (
                    FactTrustPromotionPipeline().promote_file(
                        first,
                        display_path=DISPLAY,
                    )
                )
                second_result = (
                    FactTrustPromotionPipeline().promote_file(
                        second,
                        display_path=DISPLAY,
                    )
                )
                self.assertEqual(
                    first_result.artifacts(),
                    second_result.artifacts(),
                )
                self.assertEqual(
                    first_result.summary_json(),
                    second_result.summary_json(),
                )
                serialized = b"".join(
                    first_result.artifacts().values()
                )
                self.assertNotIn(
                    str(Path(first_dir)).encode("utf-8"),
                    serialized,
                )

    def test_artifact_writer_and_check_mode_are_exact(self) -> None:
        result = FactTrustPromotionPipeline().promote_file(
            SOURCE,
            display_path=DISPLAY,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                write_promotion_artifacts(result, root),
                (),
            )
            self.assertEqual(
                write_promotion_artifacts(
                    result,
                    root,
                    check=True,
                ),
                (),
            )
            (root / "fact-trust.json").write_bytes(b"stale\n")
            mismatches = write_promotion_artifacts(
                result,
                root,
                check=True,
            )
            self.assertEqual(
                mismatches,
                ("fact-trust.json: content differs",),
            )
            (root / "extra.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            self.assertIn(
                "extra.json: stale undeclared artifact",
                write_promotion_artifacts(
                    result,
                    root,
                    check=True,
                ),
            )

    def test_cli_write_check_stale_and_error_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            command = [
                sys.executable,
                str(ROOT / "tools" / "promote_fact_trust.py"),
                str(SOURCE),
                "--display-path",
                DISPLAY,
                "--output-dir",
                str(output),
                "--backend",
                "affine",
            ]
            written = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertEqual(
                json.loads(written.stdout)["proved"],
                2,
            )
            self.assertEqual(
                _tree_bytes(output),
                _tree_bytes(EXPECTED),
            )
            checked = subprocess.run(
                [*command, "--check"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            (output / "fact-index.json").write_bytes(b"stale\n")
            stale = subprocess.run(
                [*command, "--check"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(stale.returncode, 1)
            self.assertIn("content differs", stale.stderr)

            before = _tree_bytes(output)
            missing = subprocess.run(
                [
                    *command[:2],
                    str(root / "missing.cpp"),
                    *command[3:],
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(_tree_bytes(output), before)


if __name__ == "__main__":
    unittest.main()
