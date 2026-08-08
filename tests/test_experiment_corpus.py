from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.experiment_corpus import (
    CASE_COUNT,
    EXPERIMENT_CONTEXT_SCHEMA,
    EXPERIMENT_CORPUS_SCHEMA,
    EXPERIMENT_ORACLE_SCHEMA,
    ExperimentCorpusError,
    _canonical_json,
    _content_id,
    _sha256_text,
    check_experiment_corpus,
    load_experiment_corpus,
    redact_contracts,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "experiment_e2" / "corpus"
TOOL = ROOT / "tools" / "check_experiment_corpus.py"


class ExperimentCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_experiment_corpus(CORPUS_ROOT)
        cls.checked = check_experiment_corpus(cls.corpus)

    def copied(self, parent: str) -> Path:
        target = Path(parent) / "relocated" / "corpus"
        shutil.copytree(CORPUS_ROOT, target)
        return target

    @staticmethod
    def manifest(root: Path) -> dict[str, object]:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def write_manifest(
        root: Path,
        payload: dict[str, object],
        *,
        reidentify: bool = False,
        canonical: bool = True,
    ) -> None:
        if reidentify:
            content = {
                "cases": payload["cases"],
                "schema": payload["schema"],
            }
            payload["id"] = _content_id(content)
        text = (
            _canonical_json(payload)
            if canonical
            else json.dumps(payload, separators=(",", ":")) + "\n"
        )
        (root / "manifest.json").write_text(
            text, encoding="utf-8", newline="\n"
        )

    @classmethod
    def rewrite_linked_json(
        cls,
        root: Path,
        case_index: int,
        link_field: str,
        hash_field: str,
        mutate,
        *,
        canonical: bool = True,
    ) -> None:
        manifest = cls.manifest(root)
        case = manifest["cases"][case_index]
        path = root / case[link_field]
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        text = (
            _canonical_json(payload)
            if canonical
            else json.dumps(payload, separators=(",", ":")) + "\n"
        )
        path.write_text(text, encoding="utf-8", newline="\n")
        case[hash_field] = _sha256_text(text)
        cls.write_manifest(root, manifest, reidentify=True)

    def test_frozen_manifest_has_twenty_unique_content_addressed_cases(self) -> None:
        self.assertEqual(len(self.corpus.cases), CASE_COUNT)
        self.assertEqual(
            [case.id for case in self.corpus.cases],
            [f"e2-case-{index:02d}" for index in range(1, 21)],
        )
        self.assertEqual(
            len({case.source_sha256 for case in self.corpus.cases}),
            CASE_COUNT,
        )
        self.assertEqual(
            self.corpus.to_json(),
            (CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"),
        )
        self.assertTrue(self.corpus.id.startswith("sha256:"))

    def test_all_originals_replay_and_all_oracles_verify(self) -> None:
        self.assertEqual(
            self.checked.to_dict(),
            {
                "case_count": 20,
                "corpus": self.corpus.id,
                "original_replayed": 20,
                "original_violated": 20,
                "repaired_verified": 20,
                "schema": "codeskeptic.experiment-corpus-check/v1",
            },
        )

    def test_compiler_contexts_are_exact_contract_redactions(self) -> None:
        for case in self.corpus.cases:
            with self.subTest(case=case.id):
                self.assertEqual(
                    case.redacted_source,
                    redact_contracts(case.source_text),
                )
                self.assertEqual(
                    case.redacted_source.count("\n"),
                    case.source_text.count("\n"),
                )
                self.assertNotIn("// cs:", case.redacted_source)
                self.assertNotIn("requires", case.redacted_source)
                self.assertNotIn("ensures", case.redacted_source)
                self.assertRegex(
                    case.diagnostic,
                    rf"^TEST FAILURE: {case.function}\(2\) expected -?\d+, observed -?\d+$",
                )
                self.assertNotIn("obligation", case.diagnostic)
                self.assertNotIn("counterexample", case.diagnostic)

    def test_oracles_are_single_non_contract_line_repairs(self) -> None:
        for case in self.corpus.cases:
            with self.subTest(case=case.id):
                before = case.source_text.splitlines()
                after = case.repaired_source().splitlines()
                changed = [
                    index for index, pair in enumerate(zip(before, after), start=1)
                    if pair[0] != pair[1]
                ]
                self.assertEqual(changed, [case.oracle_line])
                self.assertFalse(before[case.oracle_line - 1].lstrip().startswith("// cs:"))
                self.assertEqual(
                    _sha256_text(case.repaired_source()),
                    case.repaired_source_sha256,
                )

    def test_relocated_corpus_has_identical_bytes_and_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            relocated = self.copied(directory)
            loaded = load_experiment_corpus(relocated)
            checked = check_experiment_corpus(loaded)
            self.assertEqual(loaded.to_json(), self.corpus.to_json())
            self.assertEqual(checked.to_json(), self.checked.to_json())
            original = {
                path.relative_to(CORPUS_ROOT).as_posix(): path.read_bytes()
                for path in CORPUS_ROOT.rglob("*") if path.is_file()
            }
            copied = {
                path.relative_to(relocated).as_posix(): path.read_bytes()
                for path in relocated.rglob("*") if path.is_file()
            }
            self.assertEqual(copied, original)

    def test_shuffled_manifest_object_keys_load_to_same_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.copied(directory)
            payload = self.manifest(root)
            shuffled = {
                "schema": payload["schema"],
                "cases": [
                    dict(reversed(list(case.items())))
                    for case in payload["cases"]
                ],
                "id": payload["id"],
            }
            self.write_manifest(root, shuffled, canonical=False)
            loaded = load_experiment_corpus(root)
            self.assertEqual(loaded, self.corpus)
            self.assertEqual(loaded.to_json(), self.corpus.to_json())

    def test_missing_and_extra_files_fail_closed(self) -> None:
        for mode in ("missing", "extra"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                if mode == "missing":
                    (root / "cases" / "e2-case-01.cpp").unlink()
                else:
                    (root / "undeclared.txt").write_text("extra\n", encoding="utf-8")
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_duplicate_or_unsorted_cases_fail_closed(self) -> None:
        for mode in ("duplicate", "unsorted"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                payload = self.manifest(root)
                if mode == "duplicate":
                    payload["cases"][1] = deepcopy(payload["cases"][0])
                else:
                    payload["cases"][0], payload["cases"][1] = (
                        payload["cases"][1], payload["cases"][0]
                    )
                self.write_manifest(root, payload, reidentify=True)
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_manifest_schema_fields_and_identity_are_strict(self) -> None:
        mutations = (
            lambda value: value.update({"unknown": 1}),
            lambda value: value.pop("schema"),
            lambda value: value.update({"schema": "future"}),
            lambda value: value.update({"id": "sha256:" + "0" * 64}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                payload = self.manifest(root)
                mutate(payload)
                self.write_manifest(root, payload)
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_paths_and_source_hashes_are_strict(self) -> None:
        for mode in ("escape", "backslash", "stale"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                payload = self.manifest(root)
                case = payload["cases"][0]
                if mode == "escape":
                    case["source"] = "../outside.cpp"
                elif mode == "backslash":
                    case["source"] = "cases\\e2-case-01.cpp"
                else:
                    case["source_sha256"] = "sha256:" + "0" * 64
                self.write_manifest(root, payload, reidentify=True)
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_context_schema_links_fields_and_canonical_bytes_are_strict(self) -> None:
        def unknown(value):
            value["unknown"] = 1

        def wrong_schema(value):
            value["schema"] = "future"

        def stale_source(value):
            value["target_source"] = "sha256:" + "0" * 64

        def leaked_contract(value):
            value["redacted_source"] = "// cs: ensures false\n" + value["redacted_source"]

        for mutate, canonical in (
            (unknown, True),
            (wrong_schema, True),
            (stale_source, True),
            (leaked_contract, True),
            (lambda value: None, False),
        ):
            with self.subTest(mutate=mutate, canonical=canonical), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                self.rewrite_linked_json(
                    root,
                    0,
                    "compiler_context",
                    "compiler_context_sha256",
                    mutate,
                    canonical=canonical,
                )
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_oracle_schema_line_and_repaired_hash_are_strict(self) -> None:
        def unknown(value):
            value["unknown"] = 1

        def bool_line(value):
            value["line"] = True

        def contract_line(value):
            value["line"] = 1

        def stale_repair(value):
            value["repaired_source"] = "sha256:" + "0" * 64

        for mutate, canonical in (
            (unknown, True),
            (bool_line, True),
            (contract_line, True),
            (stale_repair, True),
            (lambda value: None, False),
        ):
            with self.subTest(mutate=mutate, canonical=canonical), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                self.rewrite_linked_json(
                    root,
                    0,
                    "oracle",
                    "oracle_sha256",
                    mutate,
                    canonical=canonical,
                )
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_utf8_bom_cr_and_nul_sources_fail_closed(self) -> None:
        for marker in (b"\xef\xbb\xbf", b"\r", b"\x00"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = self.copied(directory)
                path = root / "cases" / "e2-case-01.cpp"
                if marker == b"\xef\xbb\xbf":
                    path.write_bytes(marker + path.read_bytes())
                else:
                    path.write_bytes(path.read_bytes() + marker)
                with self.assertRaises(ExperimentCorpusError):
                    load_experiment_corpus(root)

    def test_cli_emits_exact_summary_and_errors_with_exit_two(self) -> None:
        success = subprocess.run(
            [sys.executable, str(TOOL), str(CORPUS_ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(success.stdout, self.checked.to_json())
        self.assertEqual(success.stderr, "")
        with tempfile.TemporaryDirectory() as directory:
            failure = subprocess.run(
                [sys.executable, str(TOOL), directory],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(failure.returncode, 2)
        self.assertEqual(failure.stdout, "")
        self.assertIn("experiment corpus error:", failure.stderr)


if __name__ == "__main__":
    unittest.main()
