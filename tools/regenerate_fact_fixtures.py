"""Regenerate or check deterministic fact-index fixture artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.fact_extractor import (  # noqa: E402
    ClangFactExtractor,
    FactExtractionError,
)
from semantic_verifier.facts import FactIndexError  # noqa: E402
from semantic_verifier.frontend import FrontendError  # noqa: E402


FIXTURE_ROOT = ROOT / "fixtures" / "facts"
CASES = FIXTURE_ROOT / "cases"
EXPECTED = FIXTURE_ROOT / "expected"
MANIFEST = FIXTURE_ROOT / "manifest.json"
MANIFEST_SCHEMA = "codeskeptic.fact-fixture-corpus/v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _display_path(case: Path) -> str:
    return case.relative_to(ROOT).as_posix()


def _build_outputs(
    clang: str | None,
) -> tuple[dict[Path, str], str]:
    extractor = ClangFactExtractor(clang)
    outputs: dict[Path, str] = {}
    entries: list[dict[str, str]] = []
    cases = sorted(CASES.glob("*.cpp"), key=lambda path: path.name)
    if not cases:
        raise FactExtractionError("fact fixture corpus has no C++ cases")

    for case in cases:
        display = _display_path(case)
        index = extractor.extract_file(
            case,
            display_path=display,
        )
        rendered = index.to_json()
        expected = EXPECTED / f"{case.stem}.fact-index.json"
        outputs[expected] = rendered
        entries.append(
            {
                "case": case.relative_to(FIXTURE_ROOT).as_posix(),
                "display_path": display,
                "expected": expected.relative_to(FIXTURE_ROOT).as_posix(),
                "index_id": index.id,
                "output_sha256": _sha256(rendered.encode("utf-8")),
                "source_sha256": index.source.content_sha256,
            }
        )

    body: dict[str, Any] = {
        "entries": entries,
        "schema": MANIFEST_SCHEMA,
    }
    body["manifest_id"] = _sha256(
        json.dumps(
            body,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return outputs, _canonical_json(body)


def _stale_expected(outputs: dict[Path, str]) -> list[Path]:
    declared = set(outputs)
    return sorted(
        (
            path
            for path in EXPECTED.glob("*.fact-index.json")
            if path not in declared
        ),
        key=lambda path: path.name,
    )


def _check(outputs: dict[Path, str], manifest: str) -> int:
    mismatches: list[str] = []
    for path, rendered in sorted(
        outputs.items(),
        key=lambda item: item[0].as_posix(),
    ):
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as error:
            mismatches.append(f"{path.relative_to(ROOT).as_posix()}: {error}")
            continue
        if actual != rendered:
            mismatches.append(
                f"{path.relative_to(ROOT).as_posix()}: content differs"
            )

    try:
        actual_manifest = MANIFEST.read_text(encoding="utf-8")
    except OSError as error:
        mismatches.append(
            f"{MANIFEST.relative_to(ROOT).as_posix()}: {error}"
        )
    else:
        if actual_manifest != manifest:
            mismatches.append(
                f"{MANIFEST.relative_to(ROOT).as_posix()}: content differs"
            )

    for path in _stale_expected(outputs):
        mismatches.append(
            f"{path.relative_to(ROOT).as_posix()}: stale undeclared golden"
        )

    if mismatches:
        for mismatch in mismatches:
            print(f"fact-fixture check failed: {mismatch}", file=sys.stderr)
        return 1
    print(f"fact fixtures match ({len(outputs)} cases)")
    return 0


def _write(outputs: dict[Path, str], manifest: str) -> int:
    stale = _stale_expected(outputs)
    if stale:
        for path in stale:
            print(
                (
                    "fact-fixture generation refused stale golden: "
                    f"{path.relative_to(ROOT).as_posix()}"
                ),
                file=sys.stderr,
            )
        return 2
    try:
        EXPECTED.mkdir(parents=True, exist_ok=True)
        for path, rendered in sorted(
            outputs.items(),
            key=lambda item: item[0].as_posix(),
        ):
            path.write_text(
                rendered,
                encoding="utf-8",
                newline="\n",
            )
        MANIFEST.write_text(
            manifest,
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        print(f"fact-fixture output error: {error}", file=sys.stderr)
        return 2
    print(f"wrote fact fixtures ({len(outputs)} cases)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate or check the deterministic fact corpus."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--clang")
    args = parser.parse_args(argv)

    try:
        outputs, manifest = _build_outputs(args.clang)
    except (
        FactExtractionError,
        FactIndexError,
        FrontendError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"fact-fixture error: {error}", file=sys.stderr)
        return 2

    return (
        _check(outputs, manifest)
        if args.check
        else _write(outputs, manifest)
    )


if __name__ == "__main__":
    raise SystemExit(main())
