"""Build or check a deterministic project compilation manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.project_manifest import (  # noqa: E402
    COMMAND_STYLES,
    ProjectManifestError,
    build_project_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory a C++ compilation database without executing its commands."
        )
    )
    parser.add_argument("project_root", type=Path)
    parser.add_argument(
        "--compile-commands",
        type=Path,
        default=Path("compile_commands.json"),
        help="database path, relative to project root by default",
    )
    parser.add_argument(
        "--command-style",
        choices=tuple(sorted(COMMAND_STYLES)),
        help="required only for entries using a command string",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path)
    destination.add_argument("--check", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        manifest = build_project_manifest(
            arguments.project_root,
            arguments.compile_commands,
            command_style=arguments.command_style,
        )
        rendered = manifest.to_json()
    except ProjectManifestError as error:
        print(f"project manifest input error: {error}", file=sys.stderr)
        return 2

    if arguments.output is not None:
        try:
            arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"project manifest output error: {error}", file=sys.stderr)
            return 2
    elif arguments.check is not None:
        try:
            expected = arguments.check.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"project manifest check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print("project manifest check failed: content differs", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(rendered)

    if not manifest.valid:
        rejected = sum(item.count for item in manifest.rejected)
        print(
            f"project manifest rejected {rejected} compilation entr"
            f"{'y' if rejected == 1 else 'ies'}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
