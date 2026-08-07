from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from semantic_verifier.assumption_manifest import (
    AssumptionManifestError,
    AssumptionResolution,
    AssumptionResolutionRow,
    ResolutionEvidence,
    load_assumption_manifest_json,
    load_assumption_resolution_json,
    repository_text,
    text_sha256,
    validate_assumption_resolution,
)
from tools.run_assumption_pilot import (
    TEST_COMMAND,
    build_pilot_summary,
    main as pilot_main,
    render_summary,
)


ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "pilots" / "assumption_protocol"
MANIFEST_PATH = PILOT_ROOT / "e3-pilot.manifest.json"
RESOLUTION_PATH = PILOT_ROOT / "e3-pilot.resolution.json"
SUMMARY_PATH = PILOT_ROOT / "e3-pilot.summary.json"
PILOT_REPORT_PATH = PILOT_ROOT / "e3-pilot.report.md"
ARCHIVE_ROOT = PILOT_ROOT / "archive"
REPORT_PATH = ROOT / "benchmarks" / "experiment_e2" / "results" / "report.json"
TRIAL_PATH = ROOT / "benchmarks" / "experiment_e2" / "results" / "trials.json"
DOC_PATH = ROOT / "docs" / "experiment_e2.md"
DECLARATION_ID = "sha256:13ecfcb8a49d419ad196106836d3d26818399d6eb8d77d0d69d89cd996c55ebb"


class AssumptionPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_assumption_manifest_json(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )
        cls.resolution = load_assumption_resolution_json(
            RESOLUTION_PATH.read_text(encoding="utf-8")
        )
        cls.summary = build_pilot_summary(
            cls.manifest,
            cls.resolution,
            ARCHIVE_ROOT,
        )

    def test_e2_report_has_twenty_complete_pairs(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(report["pairs"]), 20)
        self.assertEqual(
            [pair["case"] for pair in report["pairs"]],
            [f"e2-case-{index:02d}" for index in range(1, 21)],
        )
        self.assertEqual(len({pair["compiler_trial"] for pair in report["pairs"]}), 20)
        self.assertEqual(len({pair["semantic_trial"] for pair in report["pairs"]}), 20)

    def test_e2_report_exact_arithmetic_matches_predeclared_threshold(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(report["arms"]["compiler_test"]["median"], {"numerator": 7, "denominator": 2})
        self.assertEqual(report["arms"]["semantic_bundle"]["median"], {"numerator": 1, "denominator": 1})
        self.assertEqual(report["improvement"], {"numerator": 5, "denominator": 7})
        self.assertEqual(
            report["hypothesis"]["semantic_bundle_reduction_threshold"],
            {"numerator": 2, "denominator": 5},
        )
        self.assertEqual(report["outcome"], "passed")

    def test_human_report_retains_machine_limitations(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        document = " ".join(DOC_PATH.read_text(encoding="utf-8").lower().split())
        for phrase in (
            "does not establish consciousness",
            "general model behavior",
            "causality",
            "does not measure an independently sampled ai model",
        ):
            self.assertIn(phrase, document)
        self.assertEqual(len(report["limitations"]), 3)

    def test_trials_and_report_retain_recorded_proxy_provenance(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        trials = json.loads(TRIAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(report["evidence_scope"], "recorded-scripted-proxy")
        self.assertEqual(trials["evidence_scope"], "recorded-scripted-proxy")
        self.assertEqual(report["proposer"], trials["proposer"])
        self.assertNotIn("external-model", report["proposer"])

    def test_closure_links_unchanged_declaration_and_all_snapshot_inputs(self) -> None:
        self.assertEqual(self.manifest.id, DECLARATION_ID)
        self.assertEqual(self.resolution.manifest, DECLARATION_ID)
        self.assertEqual(len(self.manifest.snapshot), 5)
        self.assertEqual(
            [item.path for item in self.manifest.snapshot],
            [
                "PLAN.md",
                "benchmarks/experiment_e2/results/report.json",
                "benchmarks/experiment_e2/results/trials.json",
                "docs/assumption_protocol.md",
                "docs/experiment_e2.md",
            ],
        )
        for item in self.manifest.snapshot:
            self.assertEqual(item.sha256, text_sha256(repository_text(ARCHIVE_ROOT, item.path)))
        archived = sorted(
            path.relative_to(ARCHIVE_ROOT).as_posix()
            for path in ARCHIVE_ROOT.rglob("*")
            if path.is_file()
        )
        self.assertEqual(
            archived,
            sorted([item.path for item in self.manifest.snapshot] + ["tests/test_assumption_pilot.py"]),
        )
        live_plan = text_sha256(repository_text(ROOT, "PLAN.md"))
        declared_plan = next(item.sha256 for item in self.manifest.snapshot if item.path == "PLAN.md")
        self.assertNotEqual(live_plan, declared_plan)

    def test_overlay_resolves_five_tests_and_one_honest_uncheckable(self) -> None:
        summary = validate_assumption_resolution(
            self.manifest,
            self.resolution,
            ARCHIVE_ROOT,
        )
        self.assertEqual(summary["declared"], 6)
        self.assertEqual(summary["test"], 5)
        self.assertEqual(summary["uncheckable"], 1)
        self.assertEqual(summary["resolved_checkable"], 5)
        uncheckable = self.resolution.resolutions[-1]
        self.assertEqual(uncheckable.assumption, "asm-006")
        self.assertEqual(uncheckable.disposition, "uncheckable")
        self.assertEqual(uncheckable.evidence, ())
        self.assertIn("independently sampled", uncheckable.reason)
        pilot_report = " ".join(PILOT_REPORT_PATH.read_text(encoding="utf-8").lower().split())
        for phrase in (
            "does not establish consciousness",
            "general ai-model behavior",
            "external-model repair performance",
            "causality",
        ):
            self.assertIn(phrase, pilot_report)

    def test_pilot_summary_is_exact_repeated_and_relocated(self) -> None:
        self.assertEqual(self.summary["test_command"], TEST_COMMAND)
        self.assertEqual(render_summary(self.summary), SUMMARY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            render_summary(build_pilot_summary(self.manifest, self.resolution, ARCHIVE_ROOT)),
            render_summary(self.summary),
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "repo"
            target.mkdir()
            for item in self.manifest.snapshot:
                source = ARCHIVE_ROOT / item.path
                destination = target / item.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            evidence_path = target / "tests" / "test_assumption_pilot.py"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ARCHIVE_ROOT / "tests" / "test_assumption_pilot.py", evidence_path)
            self.assertEqual(
                render_summary(build_pilot_summary(self.manifest, self.resolution, target)),
                render_summary(self.summary),
            )
            archived_plan = target / "PLAN.md"
            archived_plan.write_text(
                archived_plan.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssumptionManifestError):
                build_pilot_summary(self.manifest, self.resolution, target)
            shutil.copy2(ARCHIVE_ROOT / "PLAN.md", archived_plan)
            evidence_path.write_text(
                evidence_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssumptionManifestError):
                build_pilot_summary(self.manifest, self.resolution, target)

    def test_stale_declaration_evidence_missing_resolution_and_false_uncheckable_fail(self) -> None:
        with self.assertRaises(AssumptionManifestError):
            ResolutionEvidence("../escape", "sha256:" + "0" * 64, "anchor")
        with self.assertRaises(AssumptionManifestError):
            validate_assumption_resolution(
                replace(self.manifest, id="sha256:" + "0" * 64),
                self.resolution,
                ARCHIVE_ROOT,
            )
        rows = list(self.resolution.resolutions)
        missing = AssumptionResolution.create(
            manifest=self.manifest.id,
            resolutions=rows[:-1],
        )
        with self.assertRaises(AssumptionManifestError):
            validate_assumption_resolution(self.manifest, missing, ARCHIVE_ROOT)
        evidence = ResolutionEvidence(
            "tests/test_assumption_pilot.py",
            text_sha256(repository_text(ARCHIVE_ROOT, "tests/test_assumption_pilot.py")),
            "class AssumptionPilotTests",
        )
        with self.assertRaises(AssumptionManifestError):
            AssumptionResolutionRow(
                "asm-006",
                "uncheckable",
                (evidence,),
                "false boundary",
            )
        stale_rows = list(rows)
        stale_rows[0] = replace(
            stale_rows[0],
            evidence=(replace(stale_rows[0].evidence[0], sha256="sha256:" + "0" * 64),),
        )
        stale = AssumptionResolution.create(
            manifest=self.manifest.id,
            resolutions=stale_rows,
        )
        with self.assertRaises(AssumptionManifestError):
            validate_assumption_resolution(self.manifest, stale, ARCHIVE_ROOT)

    def test_pilot_cli_success_mismatch_test_failure_and_input_error(self) -> None:
        success = Mock(returncode=0, stdout="", stderr="")
        with patch("tools.run_assumption_pilot.subprocess.run", return_value=success):
            self.assertEqual(
                pilot_main([
                    str(MANIFEST_PATH),
                    str(RESOLUTION_PATH),
                    "--root",
                    str(ROOT),
                    "--validation-root",
                    str(ARCHIVE_ROOT),
                    "--check",
                    str(SUMMARY_PATH),
                ]),
                0,
            )
            with tempfile.TemporaryDirectory() as directory:
                wrong = Path(directory) / "summary.json"
                wrong.write_text("{}\n", encoding="utf-8")
                self.assertEqual(
                    pilot_main([
                        str(MANIFEST_PATH),
                        str(RESOLUTION_PATH),
                        "--root",
                        str(ROOT),
                        "--validation-root",
                        str(ARCHIVE_ROOT),
                        "--check",
                        str(wrong),
                    ]),
                    1,
                )
        failed = Mock(returncode=1, stdout="", stderr="failure")
        with patch("tools.run_assumption_pilot.subprocess.run", return_value=failed):
            self.assertEqual(
                pilot_main([
                    str(MANIFEST_PATH),
                    str(RESOLUTION_PATH),
                    "--root",
                    str(ROOT),
                    "--validation-root",
                    str(ARCHIVE_ROOT),
                ]),
                1,
            )
        with patch(
            "tools.run_assumption_pilot.load_assumption_manifest_json",
            side_effect=AssumptionManifestError("broken"),
        ):
            self.assertEqual(
                pilot_main([
                    str(MANIFEST_PATH),
                    str(RESOLUTION_PATH),
                    "--root",
                    str(ROOT),
                    "--validation-root",
                    str(ARCHIVE_ROOT),
                ]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
