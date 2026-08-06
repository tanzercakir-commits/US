"""Export canonical Semantic IR and obligation JSON for the native adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SOURCE_MANIFEST = FIXTURES / "manifest.json"
DEFAULT_OUTPUT = FIXTURES / "native_adapter"
EXPORT_MANIFEST_SCHEMA = "codeskeptic.native-adapter-fixtures/v0"
IR_EXPORT_SCHEMA = "codeskeptic.native-adapter-semantic-ir/v0"
OBLIGATION_EXPORT_SCHEMA = "codeskeptic.native-adapter-obligations/v0"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.backend import create_backend  # noqa: E402
from semantic_verifier.model import SCHEMA  # noqa: E402
from semantic_verifier.pipeline import VerificationPipeline  # noqa: E402
from tools.regenerate_fixtures import load_manifest  # noqa: E402


def render_json(value: Mapping[str, Any]) -> bytes:
    """Serialize an export envelope with the cross-language byte contract."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def generate(
    *, clang: str | None = None, z3: str | None = None
) -> dict[PurePosixPath, bytes]:
    """Generate the complete native-adapter corpus in memory."""

    manifest = load_manifest()
    artifacts: dict[PurePosixPath, bytes] = {}
    cases: list[dict[str, Any]] = []
    for raw_case in sorted(manifest["cases"], key=lambda item: str(item["name"])):
        name = str(raw_case["name"])
        source_relative = _relative_path(str(raw_case["source"]))
        source_path = FIXTURES.joinpath(*source_relative.parts)
        source_bytes = source_path.read_bytes()
        source = source_bytes.decode("utf-8")
        display_path = (PurePosixPath("fixtures") / source_relative).as_posix()
        backend = str(raw_case.get("backend", "both"))
        report = VerificationPipeline(
            clang=clang,
            checker=create_backend(backend, z3=z3),
        ).verify_source(source, display_path)
        if report.summary() != raw_case["expected_summary"]:
            raise ValueError(
                f"fixture {name!r} summary changed: expected "
                f"{raw_case['expected_summary']}, got {report.summary()}"
            )

        ir_path = PurePosixPath(f"{name}.semantic-ir.json")
        obligations_path = PurePosixPath(f"{name}.obligations.json")
        ir_bytes = render_json(
            {
                "report_schema": SCHEMA,
                "schema": IR_EXPORT_SCHEMA,
                "semantic_ir": report.module.to_dict(),
                "source": display_path,
            }
        )
        obligation_bytes = render_json(
            {
                "obligations": [item.to_dict() for item in report.obligations],
                "report_schema": SCHEMA,
                "schema": OBLIGATION_EXPORT_SCHEMA,
                "source": display_path,
            }
        )
        artifacts[ir_path] = ir_bytes
        artifacts[obligations_path] = obligation_bytes
        cases.append(
            {
                "backend": backend,
                "expected_summary": raw_case["expected_summary"],
                "name": name,
                "obligations": obligations_path.as_posix(),
                "obligations_sha256": hashlib.sha256(obligation_bytes).hexdigest(),
                "semantic_ir": ir_path.as_posix(),
                "semantic_ir_sha256": hashlib.sha256(ir_bytes).hexdigest(),
                "source": display_path,
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )

    artifacts[PurePosixPath("manifest.json")] = render_json(
        {
            "cases": cases,
            "report_schema": SCHEMA,
            "schema": EXPORT_MANIFEST_SCHEMA,
        }
    )
    return dict(sorted(artifacts.items(), key=lambda item: item[0].as_posix()))


def write_artifacts(output: Path, artifacts: Mapping[PurePosixPath, bytes]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in artifacts.items():
        target = output.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def check_artifacts(
    output: Path, artifacts: Mapping[PurePosixPath, bytes]
) -> list[str]:
    expected_names = {path.as_posix() for path in artifacts}
    actual_names = (
        {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        }
        if output.exists()
        else set()
    )
    mismatches = [
        f"missing: {name}" for name in sorted(expected_names - actual_names)
    ]
    mismatches.extend(
        f"unexpected: {name}" for name in sorted(actual_names - expected_names)
    )
    for relative, content in artifacts.items():
        target = output.joinpath(*relative.parts)
        if target.is_file() and target.read_bytes() != content:
            mismatches.append(f"changed: {relative.as_posix()}")
    return mismatches


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"fixture path must stay relative: {value!r}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--clang", help="explicit Clang executable")
    parser.add_argument("--z3", help="explicit Z3 executable")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        artifacts = generate(clang=arguments.clang, z3=arguments.z3)
        output = arguments.output_dir.resolve()
        if arguments.check:
            mismatches = check_artifacts(output, artifacts)
            if mismatches:
                for mismatch in mismatches:
                    print(mismatch, file=sys.stderr)
                return 1
            print(f"native-adapter fixtures are current ({len(artifacts)} artifacts)")
            return 0
        write_artifacts(output, artifacts)
        print(f"wrote {len(artifacts)} native-adapter artifacts to {output}")
        return 0
    except Exception as error:
        print(f"native-adapter fixture export failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())