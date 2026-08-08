from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.project_manifest import (
    PROJECT_MANIFEST_SCHEMA,
    REJECTION_REASONS,
    SKIP_REASONS,
    ProjectManifestError,
    ProjectManifestRequest,
    build_project_manifest,
    load_project_manifest_json,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "project_manifest"
SCHEMA = (
    ROOT
    / "semantic_verifier"
    / "project_manifest_schema"
    / "v1"
    / "manifest.schema.json"
)
TOOL = ROOT / "tools" / "project_manifest.py"


class ProjectManifestTests(unittest.TestCase):
    def write_project(
        self,
        root: Path,
        sources: dict[str, str],
        entries: list[object],
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

    def test_machine_schema_is_versioned_and_strict(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], PROJECT_MANIFEST_SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["unit"]["additionalProperties"])
        self.assertFalse(
            schema["$defs"]["dispositionBase"]["additionalProperties"]
        )
        rejection_enum = set(
            schema["$defs"]["rejection"]["allOf"][1]["properties"]["reason"][
                "enum"
            ]
        )
        self.assertEqual(rejection_enum, REJECTION_REASONS)
        self.assertEqual(
            {
                schema["$defs"]["skip"]["allOf"][1]["properties"]["reason"][
                    "const"
                ]
            },
            SKIP_REASONS,
        )

    def test_committed_fixture_matches_and_accounts_for_c_source(self) -> None:
        manifest = build_project_manifest(FIXTURE / "project")
        expected = (FIXTURE / "expected.manifest.json").read_text(
            encoding="utf-8"
        )

        self.assertTrue(manifest.valid)
        self.assertEqual(manifest.to_json(), expected)
        self.assertEqual(manifest.entry_count, 3)
        self.assertEqual(
            tuple(unit.file for unit in manifest.selected),
            ("src/add.cpp", "src/main.cpp"),
        )
        self.assertEqual(manifest.skipped[0].file, "src/legacy.c")
        self.assertEqual(manifest.skipped[0].reason, "non_cpp_language")

    def test_manifest_is_immutable_and_requires_canonical_json(self) -> None:
        expected = (FIXTURE / "expected.manifest.json").read_text(
            encoding="utf-8"
        )
        manifest = load_project_manifest_json(expected)
        request = ProjectManifestRequest(FIXTURE / "project")

        self.assertEqual(manifest.to_json(), expected)
        with self.assertRaises(FrozenInstanceError):
            manifest.status = "invalid"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.command_style = "posix"  # type: ignore[misc]
        with self.assertRaisesRegex(ProjectManifestError, "not canonical"):
            load_project_manifest_json(expected.rstrip())
        malformed = json.loads(expected)
        malformed["skipped"][0]["reason"] = []
        with self.assertRaisesRegex(ProjectManifestError, "must be non-empty text"):
            load_project_manifest_json(
                json.dumps(malformed, indent=2, sort_keys=True) + "\n"
            )

    def test_shuffled_relocated_absolute_databases_are_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifests = []
            for ordinal, name in enumerate(("checkout-a", "checkout-b")):
                root = Path(directory) / name
                source_a = root / "src" / "a.cpp"
                source_b = root / "src" / "b.cpp"
                entries: list[object] = []
                for source in (source_a, source_b):
                    entries.append(
                        {
                            "arguments": [
                                str(root / "toolchain" / "clang++.exe"),
                                "-std=c++17",
                                "-I" + str(root / "include"),
                                "-c",
                                str(source),
                                "-o",
                                str(root / "build" / (source.stem + ".o")),
                            ],
                            "directory": str(root),
                            "file": str(source),
                        }
                    )
                if ordinal:
                    entries.reverse()
                self.write_project(
                    root,
                    {
                        "src/a.cpp": "int a() { return 1; }\n",
                        "src/b.cpp": "int b() { return 2; }\n",
                    },
                    entries,
                )
                manifests.append(build_project_manifest(root))

        self.assertEqual(manifests[0].to_json(), manifests[1].to_json())
        self.assertEqual(
            manifests[0].selected[0].arguments,
            (
                "clang++.exe",
                "-std=c++17",
                "-I$ROOT/include",
                "$SOURCE",
            ),
        )

    def test_posix_command_requires_explicit_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {"src/a.cpp": "int a() { return 1; }\n"},
                [
                    {
                        "command": (
                            "clang++ -std=c++17 -openmp -c 'src/a.cpp' "
                            "-o build/a.o"
                        ),
                        "directory": ".",
                        "file": "src/a.cpp",
                    }
                ],
            )

            unspecified = build_project_manifest(root)
            explicit = build_project_manifest(root, command_style="posix")

        self.assertFalse(unspecified.valid)
        self.assertEqual(
            unspecified.rejected[0].reason,
            "command_style_required",
        )
        self.assertTrue(explicit.valid)
        self.assertEqual(
            explicit.selected[0].arguments,
            ("clang++", "-std=c++17", "-openmp", "$SOURCE"),
        )

    def test_windows_command_style_preserves_quoted_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            self.write_project(
                root,
                {"src/a file.cpp": "int a() { return 1; }\n"},
                [
                    {
                        "command": (
                            'clang++ -std=c++17 -c "src/a file.cpp" '
                            "/Fobuild\\a.obj"
                        ),
                        "directory": ".",
                        "file": "src/a file.cpp",
                    }
                ],
            )

            manifest = build_project_manifest(root, command_style="windows")
            payload = json.loads(
                (root / "compile_commands.json").read_text(encoding="utf-8")
            )
            payload[0]["command"] = (
                'clang++ "" -c "src/a file.cpp" /Fobuild\\a.obj'
            )
            (root / "compile_commands.json").write_text(
                json.dumps(payload) + "\n",
                encoding="utf-8",
            )
            empty_argument = build_project_manifest(
                root,
                command_style="windows",
            )

        self.assertTrue(manifest.valid)
        self.assertEqual(
            manifest.selected[0].arguments,
            ("clang++", "-std=c++17", "$SOURCE"),
        )
        self.assertEqual(empty_argument.rejected[0].reason, "invalid_arguments")

    def test_malformed_entries_are_all_accounted_for(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            valid = ["clang++", "-c", "src/a.cpp"]
            self.write_project(
                root,
                {
                    "src/a.cpp": "int a() { return 1; }\n",
                    "src/b.cpp": "int b() { return 2; }\n",
                    "src/c.cpp": "int c() { return 3; }\n",
                    "src/d.cpp": "int d() { return 4; }\n",
                },
                [
                    7,
                    {
                        "arguments": valid,
                        "directory": ".",
                        "extra": True,
                        "file": "src/a.cpp",
                    },
                    {
                        "arguments": ["clang++", "-c", "src/b.cpp"],
                        "command": "clang++ -c src/b.cpp",
                        "directory": ".",
                        "file": "src/b.cpp",
                    },
                    {
                        "arguments": ["clang++", 3],
                        "directory": ".",
                        "file": "src/c.cpp",
                    },
                    {
                        "directory": ".",
                        "file": "src/d.cpp",
                    },
                ],
            )

            manifest = build_project_manifest(root)

        self.assertFalse(manifest.valid)
        self.assertEqual(manifest.entry_count, 5)
        self.assertEqual(
            sum(item.count for item in manifest.rejected),
            5,
        )
        self.assertEqual(manifest.selected, ())
        self.assertEqual(
            {item.reason for item in manifest.rejected},
            {
                "ambiguous_command_fields",
                "invalid_arguments",
                "invalid_entry",
                "missing_command",
                "unexpected_fields",
            },
        )

    def test_missing_and_outside_root_entries_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            outside = base / "outside"
            outside.mkdir()
            (outside / "outside.cpp").write_text(
                "int outside();\n",
                encoding="utf-8",
            )
            self.write_project(
                root,
                {},
                [
                    {
                        "arguments": [
                            "clang++",
                            "-c",
                            str(outside / "outside.cpp"),
                        ],
                        "directory": str(outside),
                        "file": str(outside / "outside.cpp"),
                    },
                    {
                        "arguments": ["clang++", "-c", "src/missing.cpp"],
                        "directory": ".",
                        "file": "src/missing.cpp",
                    },
                ],
            )

            manifest = build_project_manifest(root)
            readable_project = Path(directory) / "readable-project"
            self.write_project(
                readable_project,
                {"src/a.cpp": "int a();\n"},
                [
                    {
                        "arguments": ["clang++", "-c", "src/a.cpp"],
                        "directory": ".",
                        "file": "src/a.cpp",
                    }
                ],
            )
            with patch.object(Path, "read_bytes", side_effect=OSError("denied")):
                unreadable = build_project_manifest(readable_project)
            outside_database = base / "outside.json"
            outside_database.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ProjectManifestError,
                "outside project root",
            ):
                build_project_manifest(root, outside_database)

        self.assertFalse(manifest.valid)
        self.assertEqual(
            {item.reason for item in manifest.rejected},
            {"outside_project_root", "source_missing"},
        )
        self.assertEqual(unreadable.rejected[0].reason, "source_unreadable")

    def test_duplicate_and_ambiguous_commands_never_select_a_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            valid = {
                "arguments": ["clang++", "-c", "src/a.cpp"],
                "directory": ".",
                "file": "src/a.cpp",
            }
            self.write_project(
                root,
                {
                    "src/a.cpp": "int a() { return 1; }\n",
                    "src/c.cpp": "int c() { return 3; }\n",
                    "src/d.cpp": "int d() { return 4; }\n",
                    "src/legacy.c": "int legacy(void) { return 0; }\n",
                    "src/note.txt": "not source\n",
                },
                [
                    valid,
                    dict(valid),
                    {
                        "arguments": ["clang", "-c", "src/legacy.c"],
                        "directory": ".",
                        "file": "src/legacy.c",
                    },
                    {
                        "arguments": ["clang++", "-c", "src/note.txt"],
                        "directory": ".",
                        "file": "src/note.txt",
                    },
                    {
                        "arguments": [
                            "clang++",
                            "-c",
                            "src/c.cpp",
                            "src/d.cpp",
                        ],
                        "directory": ".",
                        "file": "src/c.cpp",
                    },
                ],
            )

            manifest = build_project_manifest(root)

        self.assertFalse(manifest.valid)
        self.assertEqual(manifest.selected, ())
        self.assertEqual(manifest.skipped[0].reason, "non_cpp_language")
        self.assertEqual(
            {(item.reason, item.count) for item in manifest.rejected},
            {
                ("duplicate_source_entry", 2),
                ("source_argument_ambiguous", 1),
                ("unsupported_source_extension", 1),
            },
        )

    def test_cli_output_check_and_invalid_exit_codes_are_exact(self) -> None:
        project = FIXTURE / "project"
        expected = FIXTURE / "expected.manifest.json"
        run = subprocess.run(
            [sys.executable, str(TOOL), str(project)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        check = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(project),
                "--check",
                str(expected),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, expected.read_text(encoding="utf-8"))
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(check.stdout, "")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.json"
            write = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(project),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            mismatch_file = Path(directory) / "mismatch.json"
            mismatch_file.write_text("{}\n", encoding="utf-8")
            mismatch = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(project),
                    "--check",
                    str(mismatch_file),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(write.returncode, 0, write.stderr)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                expected.read_text(encoding="utf-8"),
            )
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("content differs", mismatch.stderr)

            root = Path(directory) / "project"
            self.write_project(
                root,
                {"src/a.cpp": "int a();\n"},
                [
                    {
                        "command": "clang++ -c src/a.cpp",
                        "directory": ".",
                        "file": "src/a.cpp",
                    }
                ],
            )
            invalid = subprocess.run(
                [sys.executable, str(TOOL), str(root)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(invalid.returncode, 2)
        self.assertIn('"status": "invalid"', invalid.stdout)
        self.assertIn("rejected 1 compilation entry", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
