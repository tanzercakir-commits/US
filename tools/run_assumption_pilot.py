#!/usr/bin/env python3
"""Validate and execute the repository-local E3 assumption pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.assumption_manifest import (  # noqa: E402
    AssumptionManifestError,
    load_assumption_manifest_json,
    load_assumption_resolution_json,
    validate_assumption_resolution,
)


PILOT_SCHEMA = "codeskeptic.assumption-pilot/v1"
TEST_COMMAND = "python -m unittest tests.test_assumption_pilot"


def build_pilot_summary(manifest, resolution, root: Path) -> dict[str, object]:
    summary = validate_assumption_resolution(manifest, resolution, root)
    return {
        "contract": summary["contract"],
        "declared": summary["declared"],
        "manifest": summary["manifest"],
        "resolution": summary["resolution"],
        "resolved_checkable": summary["resolved_checkable"],
        "schema": PILOT_SCHEMA,
        "test": summary["test"],
        "test_command": TEST_COMMAND,
        "uncheckable": summary["uncheckable"],
    }


def render_summary(summary: dict[str, object]) -> str:
    return json.dumps(
        summary,
        allow_nan=False,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and run the repository-local assumption pilot."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("resolution", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", type=Path)
    arguments = parser.parse_args(argv)
    try:
        manifest = load_assumption_manifest_json(
            arguments.manifest.read_text(encoding="utf-8")
        )
        resolution = load_assumption_resolution_json(
            arguments.resolution.read_text(encoding="utf-8")
        )
        rendered = render_summary(
            build_pilot_summary(manifest, resolution, arguments.root)
        )
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_assumption_pilot"],
            cwd=arguments.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            print("assumption pilot test command failed", file=sys.stderr)
            if completed.stderr:
                print(completed.stderr.rstrip(), file=sys.stderr)
            return 1
        if arguments.check is not None:
            existing = arguments.check.read_text(encoding="utf-8")
            if existing.replace("\r\n", "\n") != rendered:
                print("assumption pilot check failed: content differs", file=sys.stderr)
                return 1
    except (AssumptionManifestError, OSError, UnicodeError, ValueError) as error:
        print(f"assumption pilot error: {error}", file=sys.stderr)
        return 2
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
