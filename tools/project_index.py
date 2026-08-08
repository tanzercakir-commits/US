"""Build or check a deterministic project declaration/call index."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.project_index import (  # noqa: E402
    ProjectIndexError,
    build_project_index,
)
from semantic_verifier.project_manifest import (  # noqa: E402
    COMMAND_STYLES,
    ProjectManifestError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Index project C++ declarations and direct calls with trusted Clang."
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
    parser.add_argument("--clang", help="trusted Clang executable")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path)
    destination.add_argument("--check", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        index = build_project_index(
            arguments.project_root,
            arguments.compile_commands,
            command_style=arguments.command_style,
            clang=arguments.clang,
        )
        rendered = index.to_json()
    except (ProjectIndexError, ProjectManifestError) as error:
        print(f"project index input error: {error}", file=sys.stderr)
        return 2

    if arguments.output is not None:
        try:
            arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"project index output error: {error}", file=sys.stderr)
            return 2
    elif arguments.check is not None:
        try:
            expected = arguments.check.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"project index check error: {error}", file=sys.stderr)
            return 2
        if rendered != expected:
            print("project index check failed: content differs", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(rendered)

    if not index.valid:
        print(
            f"project index has {len(index.rejections)} rejection(s)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
