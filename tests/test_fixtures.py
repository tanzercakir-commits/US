import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class FixtureInfrastructureTests(unittest.TestCase):
    def test_manifest_cases_have_sources_and_both_golden_outputs(self):
        manifest = json.loads(
            (FIXTURES / "manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["schema"], "codeskeptic.fixture-corpus/v0")
        self.assertGreaterEqual(len(manifest["cases"]), 5)
        names = []
        for case in manifest["cases"]:
            names.append(case["name"])
            self.assertTrue((FIXTURES / case["source"]).is_file())
            self.assertTrue(
                (FIXTURES / "expected" / f"{case['name']}.ir").is_file()
            )
            self.assertTrue(
                (
                    FIXTURES
                    / "expected"
                    / f"{case['name']}.report.json"
                ).is_file()
            )
        self.assertEqual(len(names), len(set(names)))

    def test_regeneration_check_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "regenerate_fixtures.py"),
                    "--check",
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("fixtures are current (10 artifacts)", completed.stdout)
