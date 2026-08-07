from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.assumption_manifest import (
    ASSUMPTION_SUMMARY_SCHEMA,
    Assumption,
    AssumptionManifestError,
    AssumptionResolution,
    AssumptionResolutionRow,
    ResolutionEvidence,
    SnapshotFile,
    _rooted_file,
    load_assumption_manifest_json,
    load_assumption_resolution_json,
    normalized_text,
    repository_text,
    snapshot_file,
    summary_json,
    text_sha256,
    validate_assumption_resolution,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "assumption_manifest"
MANIFEST_PATH = FIXTURE / "expected.manifest.json"
RESOLUTION_PATH = FIXTURE / "expected.resolution.json"
SUMMARY_PATH = FIXTURE / "expected.summary.json"
TOOL = ROOT / "tools" / "check_assumption_manifest.py"
SCHEMA_ROOT = ROOT / "semantic_verifier" / "assumption_manifest_schema" / "v1"


class AssumptionManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
        cls.resolution_text = RESOLUTION_PATH.read_text(encoding="utf-8")
        cls.manifest = load_assumption_manifest_json(cls.manifest_text)
        cls.resolution = load_assumption_resolution_json(cls.resolution_text)
        cls.summary = validate_assumption_resolution(
            cls.manifest,
            cls.resolution,
            FIXTURE,
        )

    def copy_fixture(self, parent: str) -> Path:
        target = Path(parent) / "relocated"
        shutil.copytree(FIXTURE, target)
        return target

    def test_frozen_contract_test_uncheckable_fixture_and_summary(self) -> None:
        self.assertEqual(len(self.manifest.assumptions), 3)
        self.assertEqual(
            [item.intended_disposition for item in self.manifest.assumptions],
            ["contract", "test", "uncheckable"],
        )
        self.assertEqual(
            self.summary,
            {
                "contract": 1,
                "declared": 3,
                "manifest": self.manifest.id,
                "resolution": self.resolution.id,
                "resolved_checkable": 2,
                "schema": ASSUMPTION_SUMMARY_SCHEMA,
                "test": 1,
                "uncheckable": 1,
            },
        )
        self.assertEqual(summary_json(self.summary), SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_declaration_identity_is_independent_of_later_resolution(self) -> None:
        alternate_rows = list(self.resolution.resolutions)
        alternate_rows[-1] = replace(
            alternate_rows[-1],
            reason="A different concrete external-study limitation.",
        )
        alternate = AssumptionResolution.create(
            manifest=self.manifest.id,
            resolutions=alternate_rows,
        )
        self.assertNotEqual(alternate.id, self.resolution.id)
        self.assertEqual(self.manifest.to_json(), self.manifest_text)
        self.assertEqual(
            load_assumption_manifest_json(self.manifest_text).id,
            self.manifest.id,
        )

    def test_relocated_snapshot_and_evidence_validate_identically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            relocated = self.copy_fixture(directory)
            manifest = load_assumption_manifest_json(
                (relocated / "expected.manifest.json").read_text(encoding="utf-8")
            )
            resolution = load_assumption_resolution_json(
                (relocated / "expected.resolution.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary_json(validate_assumption_resolution(manifest, resolution, relocated)),
                SUMMARY_PATH.read_text(encoding="utf-8"),
            )

    def test_resolution_value_rules_keep_uncheckable_distinct(self) -> None:
        evidence = self.resolution.resolutions[0].evidence
        invalid = (
            lambda: AssumptionResolutionRow("asm-001", "contract", (), None),
            lambda: AssumptionResolutionRow("asm-001", "test", evidence, "reason"),
            lambda: AssumptionResolutionRow("asm-003", "uncheckable", evidence, "reason"),
            lambda: AssumptionResolutionRow("asm-003", "uncheckable", (), None),
            lambda: AssumptionResolutionRow("asm-003", "verified", (), "reason"),
        )
        for build in invalid:
            with self.subTest(build=build), self.assertRaises(AssumptionManifestError):
                build()
        self.assertNotIn("verified", self.summary)
        self.assertEqual(self.summary["uncheckable"], 1)

    def test_missing_extra_duplicate_and_wrong_disposition_fail_closed(self) -> None:
        rows = list(self.resolution.resolutions)
        candidates = []
        candidates.append(
            AssumptionResolution.create(
                manifest=self.manifest.id,
                resolutions=rows[:-1],
            )
        )
        candidates.append(
            AssumptionResolution.create(
                manifest=self.manifest.id,
                resolutions=rows + [
                    AssumptionResolutionRow(
                        "asm-999",
                        "uncheckable",
                        (),
                        "No declaration exists for this row.",
                    )
                ],
            )
        )
        wrong_rows = list(rows)
        wrong_rows[0] = AssumptionResolutionRow(
            "asm-001",
            "test",
            wrong_rows[0].evidence,
            None,
        )
        candidates.append(
            AssumptionResolution.create(
                manifest=self.manifest.id,
                resolutions=wrong_rows,
            )
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate.id), self.assertRaises(AssumptionManifestError):
                validate_assumption_resolution(self.manifest, candidate, FIXTURE)
        with self.assertRaises(AssumptionManifestError):
            AssumptionResolution.create(
                manifest=self.manifest.id,
                resolutions=rows + [rows[0]],
            )

    def test_stale_snapshot_evidence_and_absent_anchor_fail_closed(self) -> None:
        for mode in ("snapshot", "evidence", "anchor"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.copy_fixture(directory)
                if mode == "snapshot":
                    (root / "input.txt").write_text("changed\n", encoding="utf-8")
                    resolution = self.resolution
                elif mode == "evidence":
                    (root / "contract_evidence.cpp").write_text("changed\n", encoding="utf-8")
                    resolution = self.resolution
                else:
                    rows = list(self.resolution.resolutions)
                    item = rows[0].evidence[0]
                    rows[0] = replace(
                        rows[0],
                        evidence=(replace(item, anchor="absent anchor"),),
                    )
                    resolution = AssumptionResolution.create(
                        manifest=self.manifest.id,
                        resolutions=rows,
                    )
                with self.assertRaises(AssumptionManifestError):
                    validate_assumption_resolution(self.manifest, resolution, root)

    def test_paths_hashes_and_line_endings_are_canonical(self) -> None:
        for path in ("../escape", "/absolute", "a\\b", "./same"):
            with self.subTest(path=path), self.assertRaises(AssumptionManifestError):
                SnapshotFile(path, "sha256:" + "0" * 64)
        with self.assertRaises(AssumptionManifestError):
            SnapshotFile("input.txt", "SHA256:" + "0" * 64)
        self.assertEqual(text_sha256("a\r\nb\r"), text_sha256("a\nb\n"))
        self.assertEqual(normalized_text("a\r\nb"), "a\nb")

    def test_symlink_style_resolved_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            outside = Path(directory) / "outside.txt"
            root.mkdir()
            outside.write_text("outside\n", encoding="utf-8")
            original = Path.resolve

            def resolve(path, strict=False):
                if path.name == "escape.txt":
                    return outside
                return original(path, strict=strict)

            with patch.object(Path, "resolve", resolve), self.assertRaises(AssumptionManifestError):
                _rooted_file(root, "escape.txt")

    def test_utf8_bom_nul_and_invalid_bytes_fail_closed(self) -> None:
        for data in (b"\xef\xbb\xbftext\n", b"text\x00\n", b"\xff\xfe"):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                root = self.copy_fixture(directory)
                (root / "input.txt").write_bytes(data)
                with self.assertRaises(AssumptionManifestError):
                    repository_text(root, "input.txt")

    def test_json_unknown_missing_duplicate_nonfinite_and_stale_ids_fail(self) -> None:
        manifest = json.loads(self.manifest_text)
        manifest["unknown"] = 1
        with self.assertRaises(AssumptionManifestError):
            load_assumption_manifest_json(json.dumps(manifest))
        manifest = json.loads(self.manifest_text)
        manifest.pop("subject")
        with self.assertRaises(AssumptionManifestError):
            load_assumption_manifest_json(json.dumps(manifest))
        manifest = json.loads(self.manifest_text)
        manifest["id"] = "sha256:" + "0" * 64
        with self.assertRaises(AssumptionManifestError):
            load_assumption_manifest_json(json.dumps(manifest))
        duplicate = self.manifest_text.replace(
            '  "subject":', '  "subject": "duplicate",\n  "subject":', 1
        )
        with self.assertRaises(AssumptionManifestError):
            load_assumption_manifest_json(duplicate)
        nonfinite = self.manifest_text.replace(
            '"risk": "high"', '"risk": NaN', 1
        )
        with self.assertRaises(AssumptionManifestError):
            load_assumption_manifest_json(nonfinite)

    def test_shuffled_json_keys_and_resolution_rows_are_identity_stable(self) -> None:
        manifest = json.loads(self.manifest_text)
        shuffled_manifest = dict(reversed(list(manifest.items())))
        resolution = json.loads(self.resolution_text)
        resolution["resolutions"] = list(reversed(resolution["resolutions"]))
        shuffled_resolution = dict(reversed(list(resolution.items())))
        self.assertEqual(
            load_assumption_manifest_json(json.dumps(shuffled_manifest)),
            self.manifest,
        )
        self.assertEqual(
            load_assumption_resolution_json(json.dumps(shuffled_resolution)),
            self.resolution,
        )

    def test_schema_documents_parse_and_match_runtime_schema_ids(self) -> None:
        manifest_schema = json.loads(
            (SCHEMA_ROOT / "manifest.schema.json").read_text(encoding="utf-8")
        )
        resolution_schema = json.loads(
            (SCHEMA_ROOT / "resolution.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest_schema["properties"]["schema"]["const"],
            "codeskeptic.assumption-manifest/v1",
        )
        self.assertEqual(
            resolution_schema["properties"]["schema"]["const"],
            "codeskeptic.assumption-resolution/v1",
        )
        self.assertFalse(manifest_schema["additionalProperties"])
        self.assertFalse(resolution_schema["additionalProperties"])

    def test_snapshot_helper_and_evidence_hashes_are_exact(self) -> None:
        snapshot = snapshot_file(FIXTURE, "input.txt")
        self.assertEqual(snapshot, self.manifest.snapshot[0])
        for row in self.resolution.resolutions:
            for evidence in row.evidence:
                self.assertEqual(
                    evidence.sha256,
                    text_sha256(repository_text(FIXTURE, evidence.path)),
                )
                self.assertIn(
                    evidence.anchor,
                    repository_text(FIXTURE, evidence.path),
                )

    def test_cli_outputs_exact_summary_and_errors_with_exit_two(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(MANIFEST_PATH),
                str(RESOLUTION_PATH),
                "--root",
                str(FIXTURE),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, SUMMARY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(completed.stderr, "")
        with tempfile.TemporaryDirectory() as directory:
            failure = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(MANIFEST_PATH),
                    str(RESOLUTION_PATH),
                    "--root",
                    directory,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(failure.returncode, 2)
        self.assertIn("assumption manifest error:", failure.stderr)


if __name__ == "__main__":
    unittest.main()
