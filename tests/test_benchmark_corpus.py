from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from semantic_verifier.benchmark_corpus import (
    BENCHMARK_CORPUS_SCHEMA,
    CASE_COUNT,
    EXPECTED_COUNTS,
    TIERS,
    BenchmarkCorpusError,
    _canonical_json,
    _content_id,
    _sha256_text,
    check_benchmark_corpus,
    load_benchmark_corpus,
)
from tools.check_benchmark_corpus import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpus"
SCHEMA_PATH = (
    ROOT
    / "semantic_verifier"
    / "benchmark_corpus_schema"
    / "v1"
    / "manifest.schema.json"
)


class BenchmarkCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_benchmark_corpus(CORPUS_ROOT)
        cls.checked = check_benchmark_corpus(cls.corpus)
        cls.manifest_text = (CORPUS_ROOT / "manifest.json").read_text(
            encoding="utf-8"
        )

    @staticmethod
    def manifest(root: Path) -> dict[str, object]:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def write_manifest(root: Path, payload: dict[str, object]) -> None:
        content = {
            "cases": payload["cases"],
            "schema": payload["schema"],
            "source": payload["source"],
            "source_sha256": payload["source_sha256"],
            "tiers": payload["tiers"],
        }
        payload["id"] = _content_id(content)
        (root / "manifest.json").write_text(
            _canonical_json(payload), encoding="utf-8", newline="\n"
        )

    @staticmethod
    def copied(parent: str) -> Path:
        target = Path(parent) / "relocated" / "corpus"
        shutil.copytree(CORPUS_ROOT, target)
        return target

    def test_manifest_freezes_forty_unique_functions_and_four_tiers(self) -> None:
        self.assertEqual(self.corpus.to_json(), self.manifest_text)
        self.assertEqual(len(self.corpus.cases), CASE_COUNT)
        self.assertEqual(len({case.function for case in self.corpus.cases}), CASE_COUNT)
        self.assertEqual(tuple(tier.name for tier in self.corpus.tiers), TIERS)
        self.assertEqual([tier.count for tier in self.corpus.tiers], [10] * 4)
        self.assertEqual(
            [case.function for case in self.corpus.cases],
            sorted(case.function for case in self.corpus.cases),
        )
        self.assertEqual(_sha256_text(self.corpus.source_text), self.corpus.source_sha256)

    def test_combined_referee_check_has_exact_expected_statuses(self) -> None:
        self.assertEqual(self.checked.counts, EXPECTED_COUNTS)
        self.assertEqual(len(self.checked.cases), 40)
        by_status = {
            status: [item.function for item in self.checked.cases if item.status == status]
            for status in EXPECTED_COUNTS
        }
        self.assertEqual(len(by_status["verified"]), 20)
        self.assertEqual(len(by_status["violated"]), 10)
        self.assertEqual(len(by_status["unknown"]), 10)
        self.assertEqual(by_status["unsupported"], [])
        self.assertTrue(
            all(name.startswith("bench_search_frontier_") for name in by_status["unknown"])
        )
        self.assertTrue(
            all(
                name.startswith("bench_affine_counterexample_")
                for name in by_status["violated"]
            )
        )

    def test_source_is_standalone_complete_and_contains_no_nonlinear_frontier(self) -> None:
        names = re.findall(r"^int (bench_[a-z_]+_[0-9]{2})\(", self.corpus.source_text, re.MULTILINE)
        self.assertEqual(len(names), 40)
        self.assertEqual(set(names), {case.function for case in self.corpus.cases})
        self.assertNotIn("nonlinear_frontier", self.corpus.source_text)
        frontier = [
            line for line in self.corpus.source_text.splitlines()
            if line.startswith("int bench_search_frontier_")
        ]
        self.assertEqual(len(frontier), 10)
        self.assertTrue(all("int f) { return 0; }" in line for line in frontier))

    def test_relocated_check_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = self.copied(directory)
            relocated = check_benchmark_corpus(load_benchmark_corpus(target))
            self.assertEqual(relocated.to_json(), self.checked.to_json())
            self.assertEqual(
                (target / "manifest.json").read_text(encoding="utf-8"),
                self.manifest_text,
            )

    def test_loader_rejects_missing_duplicate_reordered_and_wrong_expectations(self) -> None:
        mutations = []
        missing = json.loads(self.manifest_text)
        missing["cases"].pop()
        mutations.append(missing)
        duplicate = json.loads(self.manifest_text)
        duplicate["cases"][1] = duplicate["cases"][0]
        mutations.append(duplicate)
        reordered = json.loads(self.manifest_text)
        reordered["cases"][0], reordered["cases"][1] = (
            reordered["cases"][1],
            reordered["cases"][0],
        )
        mutations.append(reordered)
        wrong = json.loads(self.manifest_text)
        wrong["cases"][0]["expected_status"] = "unknown"
        mutations.append(wrong)
        bool_count = json.loads(self.manifest_text)
        bool_count["tiers"][0]["count"] = True
        mutations.append(bool_count)
        for payload in mutations:
            with tempfile.TemporaryDirectory() as directory:
                target = self.copied(directory)
                self.write_manifest(target, payload)
                with self.assertRaises(BenchmarkCorpusError):
                    load_benchmark_corpus(target)

    def test_loader_rejects_stale_source_extra_file_and_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = self.copied(directory)
            (target / "corpus.cpp").write_text(
                self.corpus.source_text + "\n", encoding="utf-8", newline="\n"
            )
            with self.assertRaises(BenchmarkCorpusError):
                load_benchmark_corpus(target)
        with tempfile.TemporaryDirectory() as directory:
            target = self.copied(directory)
            (target / "extra.txt").write_text("extra\n", encoding="utf-8")
            with self.assertRaises(BenchmarkCorpusError):
                load_benchmark_corpus(target)
        for text in (
            "\ufeff" + self.manifest_text,
            json.dumps(json.loads(self.manifest_text)),
            self.manifest_text.replace('  "id":', '  "schema": "duplicate",\n  "id":', 1),
        ):
            with tempfile.TemporaryDirectory() as directory:
                target = self.copied(directory)
                (target / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
                with self.assertRaises(BenchmarkCorpusError):
                    load_benchmark_corpus(target)

    def test_undeclared_source_function_fails_before_status_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = self.copied(directory)
            source = (target / "corpus.cpp").read_text(encoding="utf-8")
            source += "\nint undeclared_benchmark(int value) { return value; }\n"
            (target / "corpus.cpp").write_text(source, encoding="utf-8", newline="\n")
            payload = self.manifest(target)
            payload["source_sha256"] = _sha256_text(source)
            self.write_manifest(target, payload)
            corpus = load_benchmark_corpus(target)
            with self.assertRaises(BenchmarkCorpusError):
                check_benchmark_corpus(corpus)

    def test_structural_schema_is_strict_and_matches_manifest(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema"]["const"], BENCHMARK_CORPUS_SCHEMA)
        self.assertEqual(schema["properties"]["cases"]["minItems"], 40)
        self.assertEqual(schema["properties"]["cases"]["maxItems"], 40)
        self.assertEqual(json.loads(self.manifest_text)["schema"], BENCHMARK_CORPUS_SCHEMA)

    def test_cli_success_and_error_exit(self) -> None:
        self.assertEqual(cli_main([str(CORPUS_ROOT)]), 0)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli_main([str(Path(directory) / "missing")]), 2)


if __name__ == "__main__":
    unittest.main()
