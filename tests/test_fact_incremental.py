from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.fact_incremental import (
    FactCacheManifest,
    FactIncrementalError,
    TranslationUnit,
    TranslationUnitManifest,
    extract_incrementally,
    load_cache_manifest_json,
    load_translation_units_json,
)
from semantic_verifier.facts import FactIndex, FactSource


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "fact_incremental"
DECLARATION = FIXTURE / "translation-units.json"
WORKSPACE = FIXTURE / "workspace"
EXPECTED = FIXTURE / "expected"


class StubExtractor:
    def __init__(self, failure: str | None = None) -> None:
        self.calls: list[str] = []
        self.failure = failure

    def extract_file(
        self,
        path: str | Path,
        *,
        display_path: str | None = None,
    ) -> FactIndex:
        shown = display_path or Path(path).as_posix()
        self.calls.append(shown)
        if self.failure is not None:
            raise RuntimeError(self.failure)
        source = Path(path).read_bytes().decode("utf-8")
        return FactIndex.create(
            source=FactSource.from_text(shown, source)
        )


class ExplodingExtractor:
    def extract_file(
        self,
        path: str | Path,
        *,
        display_path: str | None = None,
    ) -> FactIndex:
        raise AssertionError("cache hit invoked extractor")


def _declaration() -> TranslationUnitManifest:
    return load_translation_units_json(
        DECLARATION.read_text(encoding="utf-8")
    )


def _copy_workspace(root: Path) -> Path:
    target = root / "workspace"
    shutil.copytree(WORKSPACE, target)
    return target


def _copy_cache(root: Path) -> Path:
    target = root / "cache"
    shutil.copytree(EXPECTED / "cache", target)
    return target


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.as_posix(),
        )
    }


class FactIncrementalTests(unittest.TestCase):
    def test_translation_unit_manifest_is_strict_and_canonical(self) -> None:
        manifest = _declaration()
        shuffled = {
            "units": [
                unit.to_dict()
                for unit in reversed(manifest.units)
            ],
            "schema": "codeskeptic.translation-units/v1",
        }
        self.assertEqual(
            load_translation_units_json(
                json.dumps(shuffled)
            ).to_json(),
            manifest.to_json(),
        )

        invalid = (
            '{"schema":"codeskeptic.translation-units/v1",'
            '"schema":"codeskeptic.translation-units/v1","units":[]}',
            '{"schema":"wrong","units":[]}',
            '{"schema":"codeskeptic.translation-units/v1",'
            '"units":[],"extra":true}',
            '{"schema":"codeskeptic.translation-units/v1",'
            '"units":[{"source":"../a.cpp","display_path":"a.cpp"}]}',
            '{"schema":"codeskeptic.translation-units/v1",'
            '"units":[{"source":"C:/a.cpp","display_path":"a.cpp"}]}',
            '{"schema":"codeskeptic.translation-units/v1",'
            '"units":[{"source":"a\\\\b.cpp","display_path":"a.cpp"}]}',
            '{"schema":"codeskeptic.translation-units/v1","units":NaN}',
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(FactIncrementalError):
                    load_translation_units_json(payload)

        with self.assertRaises(FactIncrementalError):
            TranslationUnitManifest(
                (
                    TranslationUnit("a.cpp", "a.cpp"),
                    TranslationUnit("a.cpp", "b.cpp"),
                )
            )
        with self.assertRaises(FactIncrementalError):
            TranslationUnitManifest(
                (
                    TranslationUnit("a.cpp", "same.cpp"),
                    TranslationUnit("b.cpp", "same.cpp"),
                )
            )

    def test_cache_manifest_is_strict_content_addressed_state(self) -> None:
        path = EXPECTED / "cache" / "current.json"
        text = path.read_text(encoding="utf-8")
        manifest = load_cache_manifest_json(text)
        self.assertEqual(manifest.to_json(), text)
        self.assertEqual(
            tuple(entry.source for entry in manifest.units),
            ("src/alpha.cpp", "src/beta.cpp"),
        )

        payload = json.loads(text)
        mutations = []
        for field, value in (
            ("schema", "wrong"),
            ("extractor_contract", "wrong"),
            ("fact_schema", "wrong"),
            ("manifest_id", "sha256:" + "0" * 64),
        ):
            changed = dict(payload)
            changed[field] = value
            mutations.append(json.dumps(changed))
        changed = json.loads(text)
        changed["units"][0]["cache_key"] = "sha256:" + "0" * 64
        mutations.append(json.dumps(changed))
        for candidate in mutations:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(FactIncrementalError):
                    load_cache_manifest_json(candidate)

    def test_cold_real_extraction_matches_frozen_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = root / "cache"
            result = extract_incrementally(
                workspace,
                _declaration(),
                cache,
            )
            self.assertEqual(
                result.to_json(),
                (EXPECTED / "cold-run.json").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertEqual(
                _tree_bytes(cache),
                _tree_bytes(EXPECTED / "cache"),
            )

    def test_warm_run_reuses_every_index_without_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            before = _tree_bytes(cache)
            result = extract_incrementally(
                workspace,
                _declaration(),
                cache,
                extractor=ExplodingExtractor(),
            )
            self.assertEqual(
                result.to_json(),
                (EXPECTED / "warm-run.json").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertEqual(_tree_bytes(cache), before)

    def test_one_edit_reextracts_exactly_one_translation_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            alpha = workspace / "src" / "alpha.cpp"
            alpha.write_text(
                alpha.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
                newline="\n",
            )
            extractor = StubExtractor()
            result = extract_incrementally(
                workspace,
                _declaration(),
                cache,
                extractor=extractor,
            )
            self.assertEqual(
                extractor.calls,
                ["project/src/alpha.cpp"],
            )
            self.assertEqual(result.extracted, ("src/alpha.cpp",))
            self.assertEqual(result.reused, ("src/beta.cpp",))
            second = extract_incrementally(
                workspace,
                _declaration(),
                cache,
                extractor=ExplodingExtractor(),
            )
            self.assertEqual(second.status, "current")

    def test_added_and_removed_units_are_accounted_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            (workspace / "src" / "gamma.cpp").write_text(
                "int gamma() { return 3; }\n",
                encoding="utf-8",
                newline="\n",
            )
            declaration = TranslationUnitManifest(
                (
                    TranslationUnit(
                        "src/alpha.cpp",
                        "project/src/alpha.cpp",
                    ),
                    TranslationUnit(
                        "src/gamma.cpp",
                        "project/src/gamma.cpp",
                    ),
                )
            )
            extractor = StubExtractor()
            result = extract_incrementally(
                workspace,
                declaration,
                cache,
                extractor=extractor,
            )
            self.assertEqual(result.added, ("src/gamma.cpp",))
            self.assertEqual(result.removed, ("src/beta.cpp",))
            self.assertEqual(result.extracted, ("src/gamma.cpp",))
            self.assertEqual(result.reused, ("src/alpha.cpp",))

    def test_relocated_and_shuffled_inputs_are_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                first = Path(first_dir)
                second = Path(second_dir)
                first_workspace = _copy_workspace(first)
                second_workspace = _copy_workspace(second)
                declaration = _declaration()
                shuffled = TranslationUnitManifest(
                    tuple(reversed(declaration.units))
                )
                extract_incrementally(
                    first_workspace,
                    declaration,
                    first / "cache",
                    extractor=StubExtractor(),
                )
                extract_incrementally(
                    second_workspace,
                    shuffled,
                    second / "cache",
                    extractor=StubExtractor(),
                )
                self.assertEqual(
                    _tree_bytes(first / "cache"),
                    _tree_bytes(second / "cache"),
                )

    def test_invalid_utf8_and_missing_sources_fail_closed(self) -> None:
        declaration = TranslationUnitManifest(
            (TranslationUnit("bad.cpp", "project/bad.cpp"),)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.cpp").write_bytes(b"\xff")
            with self.assertRaisesRegex(
                FactIncrementalError,
                "cannot read unit",
            ):
                extract_incrementally(
                    root,
                    declaration,
                    root / "cache",
                    extractor=StubExtractor(),
                )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                FactIncrementalError,
                "cannot read unit",
            ):
                extract_incrementally(
                    root,
                    declaration,
                    root / "cache",
                    extractor=StubExtractor(),
                )

    def test_corrupt_cache_state_never_becomes_a_miss(self) -> None:
        cases = ("manifest-whitespace", "manifest-duplicate", "index")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    workspace = _copy_workspace(root)
                    cache = _copy_cache(root)
                    current = cache / "current.json"
                    if case == "manifest-whitespace":
                        current.write_bytes(current.read_bytes() + b" ")
                    elif case == "manifest-duplicate":
                        text = current.read_text(encoding="utf-8")
                        current.write_text(
                            text.replace(
                                '"schema":',
                                '"schema":"duplicate","schema":',
                                1,
                            ),
                            encoding="utf-8",
                            newline="\n",
                        )
                    else:
                        manifest = load_cache_manifest_json(
                            current.read_text(encoding="utf-8")
                        )
                        index = cache / manifest.units[0].index
                        index.write_bytes(index.read_bytes() + b" ")
                    with self.assertRaises(FactIncrementalError):
                        extract_incrementally(
                            workspace,
                            _declaration(),
                            cache,
                            extractor=StubExtractor(),
                        )

    def test_extractor_failure_preserves_current_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            current = cache / "current.json"
            before = current.read_bytes()
            alpha = workspace / "src" / "alpha.cpp"
            alpha.write_text(
                alpha.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(
                FactIncrementalError,
                "deliberate failure",
            ):
                extract_incrementally(
                    workspace,
                    _declaration(),
                    cache,
                    extractor=StubExtractor("deliberate failure"),
                )
            self.assertEqual(current.read_bytes(), before)

    def test_check_mode_reports_staleness_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            before = _tree_bytes(cache)
            current = extract_incrementally(
                workspace,
                _declaration(),
                cache,
                extractor=ExplodingExtractor(),
                check=True,
            )
            self.assertEqual(current.status, "current")
            alpha = workspace / "src" / "alpha.cpp"
            alpha.write_text(
                alpha.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
                newline="\n",
            )
            stale = extract_incrementally(
                workspace,
                _declaration(),
                cache,
                extractor=ExplodingExtractor(),
                check=True,
            )
            self.assertEqual(stale.status, "stale")
            self.assertEqual(stale.extracted, ("src/alpha.cpp",))
            self.assertEqual(_tree_bytes(cache), before)

    def test_cli_check_exit_codes_and_canonical_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _copy_workspace(root)
            cache = _copy_cache(root)
            command = [
                sys.executable,
                str(ROOT / "tools" / "extract_facts_incremental.py"),
                str(DECLARATION),
                "--workspace",
                str(workspace),
                "--cache-dir",
                str(cache),
                "--check",
            ]
            current = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(current.returncode, 0, current.stderr)
            self.assertEqual(
                json.loads(current.stdout)["status"],
                "current",
            )
            alpha = workspace / "src" / "alpha.cpp"
            alpha.write_text(
                alpha.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
                newline="\n",
            )
            stale = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(stale.returncode, 1, stale.stderr)
            self.assertEqual(
                json.loads(stale.stdout)["extracted"],
                ["src/alpha.cpp"],
            )
            bad = subprocess.run(
                [*command[:2], str(root / "missing.json"), *command[3:]],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, "")
            self.assertIn("fact-cache error:", bad.stderr)


if __name__ == "__main__":
    unittest.main()
