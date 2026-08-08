from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import unittest

from semantic_verifier.backend import CheckerBackend, create_backend
from semantic_verifier.enforcement_ladder import (
    EnforcementLadderInputError,
    build_property_skeleton,
)
from semantic_verifier.frontend import discover_clang
from semantic_verifier.model import VerificationResult, VerificationStatus
from semantic_verifier.pipeline import VerificationPipeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "enforcement_ladder" / "property"
SOURCE = FIXTURE / "square_bounded.cpp"


class StatusBackend(CheckerBackend):
    def __init__(self, status: VerificationStatus):
        self.status = status
        self.name = f"ladder-{status.value}"

    def check(self, obligation):
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=self.status,
            location=obligation.location,
            message=f"injected {self.status.value}",
        )


class EnforcementLadderTests(unittest.TestCase):
    def source_text(self) -> str:
        return SOURCE.read_text(encoding="utf-8")

    def affine_bundle(self):
        report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_file(SOURCE)
        bundle = build_property_skeleton(
            self.source_text(),
            report,
            display_path=SOURCE.as_posix(),
        )
        return report, bundle

    def test_frozen_affine_fallback_matches_both_goldens(self):
        report, bundle = self.affine_bundle()
        self.assertEqual(
            report.summary(),
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 2,
                "verified": 1,
                "violated": 0,
            },
        )
        self.assertEqual(
            bundle.skeleton,
            (FIXTURE / "expected.property.cpp").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            bundle.manifest_json(),
            (FIXTURE / "expected.manifest.json").read_text(encoding="utf-8"),
        )
        targets = bundle.manifest["property_targets"]
        self.assertEqual(len(targets), 1)
        self.assertEqual(
            targets[0]["contributing_obligations"], ["ob00002", "ob00003"]
        )

    def test_generated_skeleton_is_compilable_cpp17(self):
        completed = subprocess.run(
            [
                discover_clang(),
                "-x",
                "c++",
                "-std=c++17",
                "-fsyntax-only",
                str(FIXTURE / "expected.property.cpp"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_unknown_path_results_collapse_to_one_contract_target(self):
        source = (
            "// cs: requires value >= 0\n"
            "// cs: ensures result >= value\n"
            "int keep_or_increment(int value, bool increment) {\n"
            "  if (increment) return value + 1;\n"
            "  return value;\n"
            "}\n"
        )
        report = VerificationPipeline(
            checker=StatusBackend(VerificationStatus.UNKNOWN)
        ).verify_source(source, "unknown.cpp")
        bundle = build_property_skeleton(
            source, report, display_path="unknown.cpp"
        )
        self.assertEqual(len(bundle.manifest["property_targets"]), 1)
        target = bundle.manifest["property_targets"][0]
        self.assertGreater(len(target["contributing_obligations"]), 1)
        self.assertEqual(target["original_statuses"], ["unknown"])
        self.assertEqual(
            bundle.skeleton.count(
                "const int result = keep_or_increment(value, increment);"
            ),
            1,
        )

    def test_verified_violated_and_solver_error_never_generate_fallbacks(self):
        cases = (
            (
                "verified",
                "// cs: ensures result == value\n"
                "int identity(int value) { return value; }\n",
                None,
                "static_verified",
            ),
            (
                "violated",
                "// cs: ensures result > value\n"
                "int identity(int value) { return value; }\n",
                None,
                "defect_replayed",
            ),
            (
                "solver",
                self.source_text(),
                StatusBackend(VerificationStatus.SOLVER_ERROR),
                "infrastructure_error",
            ),
        )
        for name, source, checker, state in cases:
            with self.subTest(name=name):
                report = VerificationPipeline(checker=checker).verify_source(
                    source, f"{name}.cpp"
                )
                bundle = build_property_skeleton(
                    source, report, display_path=f"{name}.cpp"
                )
                self.assertEqual(bundle.manifest["property_targets"], [])
                self.assertEqual(bundle.manifest["state"], "no_property_target")
                self.assertTrue(
                    all(
                        route["fallback"] == "none"
                        for route in bundle.manifest["routes"]
                    )
                )
                self.assertIn(
                    state,
                    {route["state"] for route in bundle.manifest["routes"]},
                )

    def test_ineligible_unknown_is_explicit_manual_required(self):
        source = (
            "void assert(bool);\n"
            "int internal_only(int value) {\n"
            "  assert(value >= 0);\n"
            "  return value;\n"
            "}\n"
        )
        report = VerificationPipeline(
            checker=StatusBackend(VerificationStatus.UNKNOWN)
        ).verify_source(source, "manual.cpp")
        bundle = build_property_skeleton(
            source, report, display_path="manual.cpp"
        )
        self.assertEqual(bundle.manifest["property_targets"], [])
        manual = [
            route
            for route in bundle.manifest["routes"]
            if route["state"] == "manual_required"
        ]
        self.assertTrue(manual)
        self.assertTrue(all(route["fallback"] == "manual_required" for route in manual))
        self.assertIn("no postcondition", manual[0]["routing_reason"])

    def test_stale_contract_source_cannot_generate_a_skeleton(self):
        report, _ = self.affine_bundle()
        stale = self.source_text().replace("value <= 100", "value <= 99")
        bundle = build_property_skeleton(
            stale,
            report,
            display_path=SOURCE.as_posix(),
        )
        self.assertEqual(bundle.manifest["property_targets"], [])
        self.assertTrue(
            all(
                route["fallback"] in {"none", "manual_required"}
                for route in bundle.manifest["routes"]
            )
        )
        self.assertTrue(
            any(
                "stale" in route.get("routing_reason", "")
                for route in bundle.manifest["routes"]
            )
        )

    def test_malformed_or_unreplayed_reports_fail_closed(self):
        report, _ = self.affine_bundle()
        with self.assertRaisesRegex(
            EnforcementLadderInputError, "cover every obligation"
        ):
            build_property_skeleton(
                self.source_text(),
                replace(report, results=report.results[:-1]),
                display_path=SOURCE.as_posix(),
            )

        violated_source = (
            "// cs: ensures result > value\n"
            "int identity(int value) { return value; }\n"
        )
        violated_report = VerificationPipeline().verify_source(
            violated_source, "unreplayed.cpp"
        )
        violated = next(
            item
            for item in violated_report.results
            if item.status == VerificationStatus.VIOLATED
        )
        unreplayed = replace(violated, counterexample=None)
        results = tuple(
            unreplayed if item.obligation_id == violated.obligation_id else item
            for item in violated_report.results
        )
        with self.assertRaisesRegex(EnforcementLadderInputError, "replay"):
            build_property_skeleton(
                violated_source,
                replace(violated_report, results=results),
                display_path="unreplayed.cpp",
            )

    def test_relocation_preserves_skeleton_and_manifest_bytes(self):
        source = self.source_text()
        first_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(source, "a/square.cpp")
        second_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(source, "b/square.cpp")
        first = build_property_skeleton(
            source, first_report, display_path="a/square.cpp"
        )
        second = build_property_skeleton(
            source, second_report, display_path="b/square.cpp"
        )
        self.assertEqual(first.skeleton, second.skeleton)
        self.assertEqual(first.manifest_json(), second.manifest_json())

    def test_contract_change_updates_identity_and_exact_predicate(self):
        source = self.source_text()
        changed = source.replace("value <= 100", "value <= 99")
        first_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(source, "same.cpp")
        changed_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(changed, "same.cpp")
        first = build_property_skeleton(
            source, first_report, display_path="same.cpp"
        )
        second = build_property_skeleton(
            changed, changed_report, display_path="same.cpp"
        )
        self.assertNotEqual(
            first.manifest["source_sha256"], second.manifest["source_sha256"]
        )
        self.assertNotEqual(
            first.manifest["workflow_id"], second.manifest["workflow_id"]
        )
        self.assertIn("value <= 99", second.skeleton)

    def test_skeleton_uses_supplied_cases_and_one_function_evaluation(self):
        _, bundle = self.affine_bundle()
        self.assertIn("Caller supplies cases", bundle.skeleton)
        self.assertNotIn("random", bundle.skeleton.lower())
        self.assertNotIn("seed", bundle.skeleton.lower())
        self.assertEqual(
            bundle.skeleton.count(
                "const int result = square_bounded(value);"
            ),
            1,
        )
        self.assertIn(
            "if (!((value >= 0) && (value <= 100)))", bundle.skeleton
        )
        self.assertIn("assert((result == value * value));", bundle.skeleton)

    def test_cli_checks_frozen_artifacts(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "generate_property_skeleton.py"),
                str(SOURCE),
                "--backend",
                "affine",
                "--skeleton",
                str(FIXTURE / "expected.property.cpp"),
                "--manifest",
                str(FIXTURE / "expected.manifest.json"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("artifacts match", completed.stdout)


if __name__ == "__main__":
    unittest.main()