from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.project_index import (
    CALL_STATES,
    FUNCTION_STATES,
    ISSUE_CODES,
    PROJECT_FRONTEND_POLICY,
    PROJECT_INDEX_SCHEMA,
    ProjectIndexError,
    build_project_index,
    build_project_index_from_manifest,
)
from semantic_verifier.project_manifest import build_project_manifest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "project_index"
SCHEMA = (
    ROOT
    / "semantic_verifier"
    / "project_index_schema"
    / "v1"
    / "index.schema.json"
)
TOOL = ROOT / "tools" / "project_index.py"


class ProjectIndexTests(unittest.TestCase):
    def write_project(
        self,
        root: Path,
        sources: dict[str, str],
        entries: list[dict[str, object]],
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for relative, text in sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        (root / "compile_commands.json").write_text(
            json.dumps(entries, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def entry(
        self,
        source: str,
        *extra: str,
        directory: str = ".",
    ) -> dict[str, object]:
        return {
            "arguments": [
                "clang++",
                "-std=c++17",
                *extra,
                "-c",
                source,
                "-o",
                f"build/{Path(source).stem}.o",
            ],
            "directory": directory,
            "file": source,
        }

    def test_machine_schema_is_versioned_strict_and_matches_enums(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], PROJECT_INDEX_SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["function"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["call"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["issue"]["additionalProperties"])
        self.assertEqual(
            set(schema["$defs"]["function"]["properties"]["status"]["enum"]),
            FUNCTION_STATES,
        )
        self.assertEqual(
            set(schema["$defs"]["call"]["properties"]["state"]["enum"]),
            CALL_STATES,
        )
        self.assertEqual(
            set(schema["$defs"]["issue"]["properties"]["code"]["enum"]),
            ISSUE_CODES,
        )

    def test_committed_fixture_is_exact_and_zero_silent_accounting(self) -> None:
        index = build_project_index(FIXTURE / "project")
        expected = (FIXTURE / "expected.index.json").read_text(
            encoding="utf-8"
        )

        self.assertEqual(index.to_json(), expected)
        self.assertTrue(index.valid)
        self.assertEqual(index.frontend_policy, PROJECT_FRONTEND_POLICY)
        self.assertEqual(index.accounting.units_selected, 2)
        self.assertEqual(index.accounting.units_parsed, 2)
        self.assertEqual(index.accounting.functions_discovered, 6)
        self.assertEqual(index.accounting.functions_defined, 6)
        self.assertEqual(index.accounting.calls_discovered, 4)
        self.assertEqual(index.accounting.calls_linked, 4)
        self.assertFalse(index.limitations)
        self.assertFalse(index.rejections)
        self.assertEqual(
            {source.file for source in index.sources},
            {"include/api.hpp", "src/library.cpp", "src/main.cpp"},
        )

    def test_values_are_immutable_and_public_ids_ignore_clang_ids(self) -> None:
        first = build_project_index(FIXTURE / "project")
        second = build_project_index(FIXTURE / "project")

        self.assertEqual(first.to_json(), second.to_json())
        with self.assertRaises(FrozenInstanceError):
            first.status = "invalid"  # type: ignore[misc]
        self.assertTrue(
            all(
                function.id.startswith("sha256:")
                for function in first.functions
            )
        )
        self.assertNotIn("0x", first.to_json())

    def test_relocated_and_reordered_projects_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = []
            for ordinal, name in enumerate(("checkout-a", "checkout-b")):
                root = Path(directory) / name
                sources = {
                    "include/api.hpp": "int target(int value);\n",
                    "src/a.cpp": (
                        '#include "api.hpp"\n'
                        "int target(int value) { return value + 1; }\n"
                    ),
                    "src/b.cpp": (
                        '#include "api.hpp"\n'
                        "int caller() { return target(2); }\n"
                    ),
                }
                entries = [
                    {
                        "arguments": [
                            str(root / "toolchain" / "clang++.exe"),
                            "-std=c++17",
                            "-I" + str(root / "include"),
                            "-c",
                            str(root / "src" / source),
                            "-o",
                            str(root / "build" / (Path(source).stem + ".o")),
                        ],
                        "directory": str(root),
                        "file": str(root / "src" / source),
                    }
                    for source in ("a.cpp", "b.cpp")
                ]
                if ordinal:
                    entries.reverse()
                self.write_project(root, sources, entries)
                results.append(build_project_index(root).to_json())

        self.assertEqual(results[0], results[1])

    def test_overloads_merge_by_canonical_type(self) -> None:
        index = build_project_index(FIXTURE / "project")
        choices = [
            function
            for function in index.functions
            if function.qualified_name == "choose"
        ]

        self.assertEqual(
            {function.type for function in choices},
            {"int (bool)", "int (int)"},
        )
        chosen_call = next(
            call
            for call in index.calls
            if call.location.file == "src/main.cpp"
            and call.target_name == "choose"
        )
        self.assertEqual(chosen_call.target_type, "int (int)")
        self.assertEqual(chosen_call.state, "linked")

    def test_internal_linkage_is_owned_by_translation_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {
                    "a.cpp": (
                        "static int helper() { return 1; }\n"
                        "int a() { return helper(); }\n"
                    ),
                    "b.cpp": (
                        "static int helper() { return 2; }\n"
                        "int b() { return helper(); }\n"
                    ),
                },
                [self.entry("a.cpp"), self.entry("b.cpp")],
            )
            index = build_project_index(root)

        helpers = [
            function
            for function in index.functions
            if function.qualified_name == "helper"
        ]
        self.assertEqual(len(helpers), 2)
        self.assertEqual(
            {function.owner_translation_unit for function in helpers},
            {"a.cpp", "b.cpp"},
        )
        self.assertEqual(len({function.id for function in helpers}), 2)
        self.assertEqual(index.accounting.calls_linked, 2)

    def test_odr_conflict_rejects_function_and_call_edge(self) -> None:
        index = build_project_index(FIXTURE / "odr_conflict")

        shared = next(
            function
            for function in index.functions
            if function.qualified_name == "shared"
        )
        self.assertFalse(index.valid)
        self.assertEqual(shared.status, "odr_conflict")
        self.assertEqual(len(shared.definitions), 2)
        self.assertEqual(index.calls[0].state, "conflicting")
        self.assertIn("odr_conflict", {item.code for item in index.rejections})

    def test_called_project_declaration_without_definition_is_rejected(self) -> None:
        index = build_project_index(FIXTURE / "missing_definition")

        missing = next(
            function
            for function in index.functions
            if function.qualified_name == "missing"
        )
        self.assertEqual(missing.status, "declaration_only")
        self.assertEqual(index.calls[0].state, "unresolved")
        self.assertFalse(index.valid)
        self.assertIn(
            "missing_definition",
            {item.code for item in index.rejections},
        )

    def test_indirect_call_is_explicitly_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {
                    "main.cpp": (
                        "int caller(int (*callback)()) { return callback(); }\n"
                    )
                },
                [self.entry("main.cpp")],
            )
            index = build_project_index(root)

        self.assertTrue(index.valid)
        self.assertEqual(index.accounting.calls_discovered, 1)
        self.assertEqual(index.accounting.calls_unsupported, 1)
        self.assertEqual(index.calls[0].state, "unsupported")
        self.assertIn(
            "unsupported_call",
            {item.code for item in index.limitations},
        )

    def test_member_function_and_calls_are_counted_as_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {
                    "main.cpp": (
                        "struct Box { int value() { return 1; } };\n"
                        "int caller() { Box box; return box.value(); }\n"
                    )
                },
                [self.entry("main.cpp")],
            )
            index = build_project_index(root)

        self.assertTrue(index.valid)
        self.assertEqual(index.accounting.functions_discovered, 2)
        self.assertEqual(index.accounting.functions_defined, 1)
        self.assertEqual(index.accounting.functions_unsupported, 1)
        self.assertGreaterEqual(index.accounting.calls_discovered, 1)
        self.assertEqual(
            index.accounting.calls_discovered,
            index.accounting.calls_unsupported,
        )
        self.assertTrue(
            all(call.state == "unsupported" for call in index.calls)
        )

    def test_external_header_call_is_not_guessed_as_project_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            external = base / "external"
            external.mkdir()
            (external / "vendor.hpp").write_text(
                "int vendor_api(int value);\n",
                encoding="utf-8",
                newline="\n",
            )
            root = base / "project"
            self.write_project(
                root,
                {
                    "main.cpp": (
                        '#include "vendor.hpp"\n'
                        "int caller() { return vendor_api(3); }\n"
                    )
                },
                [self.entry("main.cpp", "-I" + str(external))],
            )
            index = build_project_index(root)

        self.assertTrue(index.valid)
        self.assertEqual(index.calls[0].state, "external")
        self.assertIsNone(index.calls[0].target)
        self.assertNotIn("vendor.hpp", {source.file for source in index.sources})

    def test_manifest_arguments_drive_preprocessing_but_plugins_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {
                    "main.cpp": (
                        "#if PROJECT_VALUE != 7\n"
                        '#error "compile definition was not applied"\n'
                        "#endif\n"
                        "int value() { return PROJECT_VALUE; }\n"
                    )
                },
                [self.entry("main.cpp", "-DPROJECT_VALUE=7")],
            )
            accepted = build_project_index(root)
            payload = json.loads(
                (root / "compile_commands.json").read_text(encoding="utf-8")
            )
            payload[0]["arguments"].insert(2, "-fplugin=untrusted")
            (root / "compile_commands.json").write_text(
                json.dumps(payload) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            rejected = build_project_index(root)

        self.assertTrue(accepted.valid)
        self.assertFalse(rejected.valid)
        self.assertEqual(rejected.accounting.units_frontend_error, 1)
        self.assertEqual(
            rejected.rejections[0].code,
            "compiler_argument_unsupported",
        )

    def test_source_change_after_manifest_is_rejected_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {"main.cpp": "int value() { return 1; }\n"},
                [self.entry("main.cpp")],
            )
            manifest = build_project_manifest(root)
            (root / "main.cpp").write_text(
                "int value() { return 2; }\n",
                encoding="utf-8",
                newline="\n",
            )
            index = build_project_index_from_manifest(root, manifest)

        self.assertFalse(index.valid)
        self.assertEqual(index.accounting.units_frontend_error, 1)
        self.assertEqual(index.rejections[0].code, "stale_source")

    def test_invalid_manifest_is_not_partially_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {"main.cpp": "int value() { return 1; }\n"},
                [
                    {
                        "arguments": ["clang++", "-c", "missing.cpp"],
                        "directory": ".",
                        "file": "missing.cpp",
                    }
                ],
            )
            manifest = build_project_manifest(root)

            with self.assertRaisesRegex(ProjectIndexError, "valid project manifest"):
                build_project_index_from_manifest(root, manifest)

    def test_cli_check_and_invalid_exit_codes_are_exact(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(FIXTURE / "project"),
                "--check",
                str(FIXTURE / "expected.index.json"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "wrong.json"
            wrong.write_text("{}\n", encoding="utf-8", newline="\n")
            mismatch = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(FIXTURE / "project"),
                    "--check",
                    str(wrong),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn("content differs", mismatch.stderr)


if __name__ == "__main__":
    unittest.main()
