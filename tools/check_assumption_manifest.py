#!/usr/bin/env python3
"""Validate an immutable assumption declaration and resolution overlay."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.assumption_manifest import (  # noqa: E402
    AssumptionManifestError,
    load_assumption_manifest_json,
    load_assumption_resolution_json,
    summary_json,
    validate_assumption_resolution,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate assumption declaration and resolution evidence."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("resolution", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        manifest = load_assumption_manifest_json(
            arguments.manifest.read_text(encoding="utf-8")
        )
        resolution = load_assumption_resolution_json(
            arguments.resolution.read_text(encoding="utf-8")
        )
        summary = validate_assumption_resolution(
            manifest,
            resolution,
            arguments.root,
        )
    except (AssumptionManifestError, OSError, UnicodeError, ValueError) as error:
        print(f"assumption manifest error: {error}", file=sys.stderr)
        return 2
    print(summary_json(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
