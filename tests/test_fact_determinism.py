from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.fact_extractor import ClangFactExtractor
from semantic_verifier.facts import load_fact_index_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "facts"
CASES = FIXTURES / "cases"
EXPECTED = FIXTURES / "expected"
MANIFEST = FIXTURES / "manifest.json"
TOOL = ROOT / "tools" / "regenerate_fact_fixtures.py"


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FactDeterminismTests(unittest.TestCase):
    def manifest(self):
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def expected_payloads(self):
        return {
            path.stem.removesuffix(".fact-index"): json.loads(
                path.read_text(encoding="utf-8")
            )
            for path in sorted(EXPECTED.glob("*.fact-index.json"))
        }

    def test_check_mode_matches_all_committed_artifacts(self):
        completed = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("fact fixtures match (2 cases)", completed.stdout)

    def test_manifest_declares_every_case_and_only_its_golden(self):
        manifest = self.manifest()
        self.assertEqual(
            manifest["schema"],
            "codeskeptic.fact-fixture-corpus/v1",
        )
        entries = manifest["entries"]
        self.assertEqual(
            [entry["case"] for entry in entries],
            ["cases/limitations.cpp", "cases/world.cpp"],
        )
        declared_cases = {
            FIXTURES / entry["case"]
            for entry in entries
        }
        declared_expected = {
            FIXTURES / entry["expected"]
            for entry in entries
        }
        self.assertEqual(
            declared_cases,
            set(CASES.glob("*.cpp")),
        )
        self.assertEqual(
            declared_expected,
            set(EXPECTED.glob("*.fact-index.json")),
        )
        self.assertEqual(
            [entry["display_path"] for entry in entries],
            sorted(entry["display_path"] for entry in entries),
        )

    def test_manifest_hashes_and_index_ids_are_exact(self):
        manifest = self.manifest()
        body = {
            "entries": manifest["entries"],
            "schema": manifest["schema"],
        }
        expected_manifest_id = sha256(
            json.dumps(
                body,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        self.assertEqual(
            manifest["manifest_id"],
            expected_manifest_id,
        )
        for entry in manifest["entries"]:
            case = FIXTURES / entry["case"]
            expected = FIXTURES / entry["expected"]
            source_bytes = case.read_bytes()
            output_bytes = expected.read_bytes()
            payload = json.loads(output_bytes)
            self.assertEqual(
                entry["source_sha256"],
                sha256(source_bytes),
            )
            self.assertEqual(
                entry["output_sha256"],
                sha256(output_bytes),
            )
            self.assertEqual(entry["index_id"], payload["id"])

    def test_goldens_are_strict_round_trippable_and_canonically_sorted(self):
        for path in sorted(EXPECTED.glob("*.fact-index.json")):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                index = load_fact_index_json(text)
                self.assertEqual(index.to_json(), text)
                payload = json.loads(text)
                for field in (
                    "calls",
                    "definitions",
                    "mutations",
                    "symbols",
                    "uses",
                ):
                    self.assertEqual(
                        [item["id"] for item in payload[field]],
                        sorted(item["id"] for item in payload[field]),
                    )
                self.assertEqual(
                    [item["function"] for item in payload["purity"]],
                    sorted(
                        item["function"]
                        for item in payload["purity"]
                    ),
                )

    def test_world_golden_covers_scopes_calls_and_mutations(self):
        payload = self.expected_payloads()["world"]
        symbols = {
            symbol["id"]: symbol
            for symbol in payload["symbols"]
        }
        functions = [
            symbol
            for symbol in symbols.values()
            if symbol["kind"] == "function"
        ]
        normalize = [
            symbol
            for symbol in functions
            if symbol["qualified_name"] == "math::normalize"
        ]
        self.assertEqual(len(normalize), 2)
        self.assertEqual(
            {symbol["type"] for symbol in normalize},
            {"int (bool)", "int (int)"},
        )
        self.assertEqual(
            len(
                [
                    symbol
                    for symbol in symbols.values()
                    if symbol["kind"] == "variable"
                    and symbol["name"] == "temporary"
                ]
            ),
            2,
        )
        edges = {
            (
                symbols[call["caller"]]["qualified_name"],
                symbols[call["callee"]]["qualified_name"],
            )
            for call in payload["calls"]
        }
        self.assertEqual(
            edges,
            {
                ("pipeline", "math::normalize"),
                ("pipeline", "store"),
                ("store", "math::normalize"),
            },
        )
        mutation_names = {
            symbols[mutation["target"]]["qualified_name"]
            for mutation in payload["mutations"]
        }
        self.assertIn("global_total", mutation_names)
        self.assertIn("Counter::value", mutation_names)
        self.assertIn("store::counter@parameter:0", mutation_names)
    def test_limitation_golden_covers_every_v0_fail_closed_route(self):
        payload = self.expected_payloads()["limitations"]
        self.assertEqual(
            {item["code"] for item in payload["limitations"]},
            {
                "indirect_call",
                "macro_location",
                "unresolved_symbol",
                "unsupported_ast",
                "virtual_dispatch",
            },
        )
        self.assertEqual(
            {item["status"] for item in payload["purity"]},
            {"unknown"},
        )
        all_reasons = {
            reason
            for item in payload["purity"]
            for reason in item["reasons"]
        }
        self.assertTrue(
            {
                "indirect_call",
                "unresolved_call",
                "unsupported_construct",
                "virtual_dispatch",
            }.issubset(all_reasons)
        )
        self.assertTrue(payload["calls"])
        self.assertFalse(payload["mutations"])

    def test_repeated_and_relocated_cases_match_golden_bytes(self):
        extractor = ClangFactExtractor()
        manifest = self.manifest()
        with tempfile.TemporaryDirectory() as directory:
            relocated = Path(directory)
            for entry in manifest["entries"]:
                case = FIXTURES / entry["case"]
                expected = (
                    FIXTURES / entry["expected"]
                ).read_text(encoding="utf-8")
                first = extractor.extract_file(
                    case,
                    display_path=entry["display_path"],
                ).to_json()
                copied = relocated / case.name
                shutil.copyfile(case, copied)
                second = extractor.extract_file(
                    copied,
                    display_path=entry["display_path"],
                ).to_json()
                with self.subTest(case=case.name):
                    self.assertEqual(first, expected)
                    self.assertEqual(second, expected)

    def test_artifacts_exclude_unstable_environment_state(self):
        forbidden = (
            "C:\\Projects\\US",
            "C:/Projects/US",
            "AppData",
            "semantic-verifier-",
            '"0x',
            '"clock"',
            '"duration"',
            '"random"',
        )
        artifacts = [
            MANIFEST.read_text(encoding="utf-8"),
            *[
                path.read_text(encoding="utf-8")
                for path in sorted(
                    EXPECTED.glob("*.fact-index.json")
                )
            ],
        ]
        for text in artifacts:
            for marker in forbidden:
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, text)
        self.assertNotIn(
            "clang",
            "\n".join(artifacts).lower(),
        )

    def test_generation_does_not_touch_verification_fixtures(self):
        protected = (
            ROOT
            / "fixtures"
            / "expected"
            / "vertical_slice.report.json"
        )
        before = protected.read_bytes()
        completed = subprocess.run(
            [sys.executable, str(TOOL)],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(protected.read_bytes(), before)
        checked = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
