"""Check or update a deterministic translation-unit fact cache."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.fact_incremental import (  # noqa: E402
    FactIncrementalError,
    extract_incrementally,
    read_translation_units,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract changed translation units into a strict fact cache."
        )
    )
    parser.add_argument("manifest")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--clang")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report staleness without invoking Clang or writing",
    )
    arguments = parser.parse_args(argv)

    try:
        declaration = read_translation_units(arguments.manifest)
        result = extract_incrementally(
            arguments.workspace,
            declaration,
            arguments.cache_dir,
            clang=arguments.clang,
            check=arguments.check,
        )
    except (FactIncrementalError, OSError, UnicodeError) as error:
        print(f"fact-cache error: {error}", file=sys.stderr)
        return 2

    sys.stdout.write(result.to_json())
    if arguments.check and result.status == "stale":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
