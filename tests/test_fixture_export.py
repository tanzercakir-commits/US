from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.model import SCHEMA
from tools.export_fixtures import (
    DEFAULT_OUTPUT,
    EXPORT_MANIFEST_SCHEMA,
    IR_EXPORT_SCHEMA,
    OBLIGATION_EXPORT_SCHEMA,
    check_artifacts,
    generate,
    write_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class NativeAdapterFixtureExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = generate()
        cls.second = generate()
        cls.manifest = json.loads(cls.first[PurePosixPath("manifest.json")])

    def test_export_manifest_is_sorted_self_describing_and_hash_complete(self):
        self.assertEqual(self.manifest["schema"], EXPORT_MANIFEST_SCHEMA)
        self.assertEqual(self.manifest["report_schema"], SCHEMA)
        cases = self.manifest["cases"]
        self.assertEqual(len(cases), 14)
        self.assertEqual([case["name"] for case in cases], sorted(case["name"] for case in cases))
        self.assertEqual(len(self.first), 29)
        for case in cases:
            ir_path = PurePosixPath(case["semantic_ir"])
            obligations_path = PurePosixPath(case["obligations"])
            self.assertEqual(
                hashlib.sha256(self.first[ir_path]).hexdigest(),
                case["semantic_ir_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(self.first[obligations_path]).hexdigest(),
                case["obligations_sha256"],
            )

    def test_two_in_memory_exports_are_byte_identical_and_committed(self):
        self.assertEqual(self.first, self.second)
        self.assertEqual(check_artifacts(DEFAULT_OUTPUT, self.first), [])
        self.assertEqual(
            hashlib.sha256(self.first[PurePosixPath("manifest.json")]).hexdigest(),
            "462d1be66df0a3ef4d6d9493a443270248289e2c91df9ccd18e825db244c8e82",
        )

    def test_exported_ir_and_obligations_equal_current_report_corpus(self):
        for case in self.manifest["cases"]:
            report = json.loads(
                (
                    ROOT
                    / "fixtures"
                    / "expected"
                    / f"{case['name']}.report.json"
                ).read_text(encoding="utf-8")
            )
            ir_export = json.loads(self.first[PurePosixPath(case["semantic_ir"])])
            obligation_export = json.loads(self.first[PurePosixPath(case["obligations"])])
            self.assertEqual(ir_export["schema"], IR_EXPORT_SCHEMA)
            self.assertEqual(obligation_export["schema"], OBLIGATION_EXPORT_SCHEMA)
            self.assertEqual(ir_export["report_schema"], report["schema"])
            self.assertEqual(obligation_export["report_schema"], report["schema"])
            self.assertEqual(ir_export["semantic_ir"], report["semantic_ir"])
            self.assertEqual(obligation_export["obligations"], report["obligations"])
            self.assertEqual(ir_export["source"], report["source"])
            self.assertEqual(obligation_export["source"], report["source"])

    def test_check_detects_unexpected_files_without_deleting_them(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_artifacts(output, self.first)
            unexpected = output / "owner-note.txt"
            unexpected.write_text("keep\n", encoding="utf-8")
            self.assertEqual(
                check_artifacts(output, self.first),
                ["unexpected: owner-note.txt"],
            )
            self.assertTrue(unexpected.is_file())

    def test_cli_check_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "export_fixtures.py"),
                    "--check",
                ],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("native-adapter fixtures are current (29 artifacts)", completed.stdout)


if __name__ == "__main__":
    unittest.main()