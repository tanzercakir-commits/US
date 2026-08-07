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

from .cpp26_contracts import (
    Cpp26ContractBridgeError,
    Cpp26FunctionContract,
    bridge_cpp26_contracts,
)
from .integer_types import TARGET_PROFILE_ID, TARGET_PROFILE_PROBE
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
    cpp26_contracts: tuple[Cpp26FunctionContract, ...] = ()


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


_PROFILE_VALIDATION: dict[str, str | None] = {}


def validate_integer_target_profile(clang: str) -> None:
    """Require the pinned integer implementation choices before lowering."""

    key = os.path.normcase(os.path.abspath(clang))
    if key in _PROFILE_VALIDATION:
        error = _PROFILE_VALIDATION[key]
        if error is not None:
            raise FrontendError(error)
        return

    command = [
        clang,
        "-x",
        "c++",
        "-std=c++17",
        "-fsyntax-only",
        "-Wno-everything",
        "-",
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    error: str | None = None
    try:
        completed = subprocess.run(
            command,
            input=TARGET_PROFILE_PROBE,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=flags,
        )
        if completed.returncode != 0:
            error = (
                f"Clang does not satisfy integer target profile "
                f"{TARGET_PROFILE_ID}"
            )
    except OSError as failure:
        error = f"failed to validate integer target profile: {failure}"
    _PROFILE_VALIDATION[key] = error
    if error is not None:
        raise FrontendError(error)


class ClangJsonFrontend:
    def __init__(self, clang: str | None = None) -> None:
        self.clang = discover_clang(clang)
        validate_integer_target_profile(self.clang)

    def parse_file(
        self, path: str | os.PathLike[str], display_path: str | None = None
    ) -> FrontendUnit:
        source_path = Path(path)
        shown = (display_path or source_path.as_posix()).replace(chr(92), "/")
        try:
            source = source_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise FrontendError(f"cannot read {shown}: {error}") from error
        try:
            bridge = bridge_cpp26_contracts(source)
        except Cpp26ContractBridgeError as error:
            raise FrontendError(
                f"unsupported C++26 contract bridge input: {error}"
            ) from error

        if not bridge.changed:
            ast = self._parse_ast(source_path, shown)
            physical_path = os.path.normcase(os.path.abspath(source_path))
            return FrontendUnit(
                source,
                shown,
                physical_path,
                ast,
                LineMap(source, shown),
            )

        with tempfile.TemporaryDirectory(
            prefix="semantic-verifier-cpp26-"
        ) as directory:
            compiler_path = Path(directory) / (
                "input" + (source_path.suffix or ".cpp")
            )
            compiler_path.write_bytes(bridge.compiler_source.encode("utf-8"))
            include_path: Path | None = None
            if bridge.assertion_count:
                include_path = Path(directory) / "codeskeptic_contract_assert.hpp"
                include_path.write_bytes(b"void assert(bool);\n")
            ast = self._parse_ast(compiler_path, shown, include_path=include_path)
            physical_path = os.path.normcase(os.path.abspath(compiler_path))
            return FrontendUnit(
                source,
                shown,
                physical_path,
                ast,
                LineMap(source, shown),
                bridge.function_contracts,
            )

    def _parse_ast(
        self,
        source_path: Path,
        shown: str,
        *,
        include_path: Path | None = None,
    ) -> dict[str, Any]:
        command = [
            self.clang,
            "-Xclang",
            "-ast-dump=json",
            "-fsyntax-only",
            "-fparse-all-comments",
            "-fno-color-diagnostics",
            "-Wno-everything",
            "-std=c++17",
        ]
        if include_path is not None:
            command.extend(["-include", str(include_path)])
        command.append(str(source_path))
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
            if include_path is not None:
                path_variants.update(
                    {
                        str(include_path),
                        include_path.as_posix(),
                        str(include_path.resolve()),
                        include_path.resolve().as_posix(),
                    }
                )
            for path_variant in sorted(path_variants, key=len, reverse=True):
                detail = detail.replace(path_variant, shown)
            raise FrontendError(f"Clang rejected the translation unit: {detail}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise FrontendError(f"Clang returned invalid AST JSON: {error}") from error

    def parse_source(
        self, source: str, display_path: str = "test.cpp"
    ) -> FrontendUnit:
        suffix = Path(display_path).suffix or ".cpp"
        with tempfile.TemporaryDirectory(prefix="semantic-verifier-") as directory:
            temp_path = Path(directory) / f"input{suffix}"
            temp_path.write_text(source, encoding="utf-8", newline="\n")
            return self.parse_file(temp_path, display_path=display_path)
