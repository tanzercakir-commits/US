"""Clang JSON-AST frontend adapter.

The production CodeSkeptic seam is an ASTContext callback.  This isolated US
prototype uses Clang's JSON dump so the logic layers remain dependency-light
while still consuming a real C++ frontend rather than a syntax imitation.
"""

from __future__ import annotations

from dataclasses import dataclass
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .locations import LineMap


class FrontendError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FrontendUnit:
    source: str
    display_path: str
    physical_path: str
    ast: dict[str, Any]
    line_map: LineMap


def discover_clang(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    configured = os.environ.get("SEMANTIC_VERIFIER_CLANG")
    if configured:
        candidates.append(configured)
    for name in ("clang++", "clang"):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)
    if os.name == "nt":
        candidates.extend(
            sorted(
                glob.glob(r"C:\llvm\clang+llvm-*\bin\clang.exe"),
                reverse=True,
            )
        )
        candidates.append(r"C:\Program Files\LLVM\bin\clang.exe")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise FrontendError(
        "Clang was not found. Set SEMANTIC_VERIFIER_CLANG or pass --clang."
    )


class ClangJsonFrontend:
    def __init__(self, clang: str | None = None) -> None:
        self.clang = discover_clang(clang)

    def parse_file(
        self, path: str | os.PathLike[str], display_path: str | None = None
    ) -> FrontendUnit:
        source_path = Path(path)
        shown = (display_path or source_path.as_posix()).replace(chr(92), "/")
        try:
            source = source_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise FrontendError(f"cannot read {shown}: {error}") from error

        command = [
            self.clang,
            "-Xclang",
            "-ast-dump=json",
            "-fsyntax-only",
            "-fparse-all-comments",
            "-fno-color-diagnostics",
            "-Wno-everything",
            "-std=c++17",
            str(source_path),
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                creationflags=flags,
            )
        except OSError as error:
            raise FrontendError(f"failed to execute Clang: {error}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "unknown Clang failure"
            path_variants = {
                str(source_path),
                source_path.as_posix(),
                str(source_path.resolve()),
                source_path.resolve().as_posix(),
            }
            for path_variant in sorted(path_variants, key=len, reverse=True):
                detail = detail.replace(path_variant, shown)
            raise FrontendError(f"Clang rejected the translation unit: {detail}")
        try:
            ast = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise FrontendError(f"Clang returned invalid AST JSON: {error}") from error
        physical_path = os.path.normcase(os.path.abspath(source_path))
        return FrontendUnit(source, shown, physical_path, ast, LineMap(source, shown))

    def parse_source(
        self, source: str, display_path: str = "test.cpp"
    ) -> FrontendUnit:
        suffix = Path(display_path).suffix or ".cpp"
        with tempfile.TemporaryDirectory(prefix="semantic-verifier-") as directory:
            temp_path = Path(directory) / f"input{suffix}"
            temp_path.write_text(source, encoding="utf-8", newline="\n")
            return self.parse_file(temp_path, display_path=display_path)
