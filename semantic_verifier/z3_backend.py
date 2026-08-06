"""Deterministic subprocess runner for the Z3 SMT solver."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import glob
import math
import os
from pathlib import Path
import shutil
import subprocess

from .model import VerificationStatus


class Z3DiscoveryError(RuntimeError):
    """Raised when no usable Z3 executable can be found."""


class Z3Outcome(str, Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    CRASH = "crash"
    CONFIGURATION_ERROR = "configuration_error"


@dataclass(frozen=True, slots=True)
class Z3RunResult:
    outcome: Z3Outcome
    status: VerificationStatus
    message: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None


def discover_z3(explicit: str | None = None) -> str:
    """Find Z3 using the documented deterministic precedence order."""

    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    configured = os.environ.get("SEMANTIC_VERIFIER_Z3")
    if configured:
        candidates.append(configured)
    resolved = shutil.which("z3")
    if resolved:
        candidates.append(resolved)
    candidates.extend(_known_z3_candidates())

    seen: set[str] = set()
    for candidate in candidates:
        expanded = os.path.abspath(os.path.expanduser(candidate))
        identity = os.path.normcase(expanded)
        if identity in seen:
            continue
        seen.add(identity)
        if Path(expanded).is_file():
            return str(Path(expanded))
    raise Z3DiscoveryError(
        "Z3 was not found. Set SEMANTIC_VERIFIER_Z3 or install z3 on PATH."
    )


def _known_z3_candidates() -> tuple[str, ...]:
    if os.name != "nt":
        return (
            "/opt/homebrew/bin/z3",
            "/usr/local/bin/z3",
            "/usr/bin/z3",
        )

    candidates: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            sorted(
                glob.glob(
                    str(Path(local_app_data) / "Programs" / "z3-*" / "bin" / "z3.exe")
                ),
                reverse=True,
            )
        )
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.extend(
        (
            str(Path(program_files) / "Z3" / "bin" / "z3.exe"),
            r"C:\z3\bin\z3.exe",
        )
    )
    return tuple(candidates)


class Z3ProcessRunner:
    """Execute SMT-LIB2 with fixed solver settings and bounded resources."""

    def __init__(
        self,
        z3: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        self._configured_z3 = z3
        self.timeout_seconds = float(timeout_seconds)

    def run(self, smtlib: str, mode: str = "validity") -> Z3RunResult:
        if mode not in {"validity", "satisfiable"}:
            return self._error(
                Z3Outcome.CONFIGURATION_ERROR,
                f"solver error: unknown obligation mode {mode!r}",
            )
        if not isinstance(smtlib, str) or not smtlib.strip():
            return self._error(
                Z3Outcome.CONFIGURATION_ERROR,
                "solver error: SMT-LIB2 query must be non-empty text",
            )
        try:
            executable = discover_z3(self._configured_z3)
        except Z3DiscoveryError as error:
            return self._error(
                Z3Outcome.CONFIGURATION_ERROR,
                f"solver error: Z3 configuration failed: {error}",
            )

        timeout_ms = max(1, math.ceil(self.timeout_seconds * 1000))
        command = [
            executable,
            "-in",
            "-smt2",
            f"timeout={timeout_ms}",
            "smt.random_seed=0",
            "sat.random_seed=0",
            "parallel.enable=false",
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            completed = subprocess.run(
                command,
                input=smtlib,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                creationflags=flags,
            )
        except subprocess.TimeoutExpired as error:
            return Z3RunResult(
                outcome=Z3Outcome.TIMEOUT,
                status=VerificationStatus.UNKNOWN,
                message=(
                    "unknown: Z3 timed out after "
                    f"{self.timeout_seconds:g} seconds"
                ),
                stdout=_process_text(error.stdout),
                stderr=_process_text(error.stderr),
            )
        except OSError as error:
            return self._error(
                Z3Outcome.CRASH,
                f"solver error: failed to execute Z3: {type(error).__name__}: {error}",
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0:
            detail = stderr.strip() or stdout.strip() or "no diagnostic output"
            return self._error(
                Z3Outcome.CRASH,
                f"solver error: Z3 exited with code {completed.returncode}: {detail}",
                stdout=stdout,
                stderr=stderr,
                returncode=completed.returncode,
            )

        first_line = next(
            (line.strip() for line in stdout.splitlines() if line.strip()), ""
        )
        try:
            outcome = Z3Outcome(first_line)
        except ValueError:
            detail = first_line or stderr.strip() or "no result output"
            return self._error(
                Z3Outcome.CRASH,
                f"solver error: unexpected Z3 output: {detail}",
                stdout=stdout,
                stderr=stderr,
                returncode=completed.returncode,
            )
        if outcome not in {Z3Outcome.SAT, Z3Outcome.UNSAT, Z3Outcome.UNKNOWN}:
            return self._error(
                Z3Outcome.CRASH,
                f"solver error: unexpected Z3 outcome {outcome.value!r}",
                stdout=stdout,
                stderr=stderr,
                returncode=completed.returncode,
            )
        status, message = _map_solver_outcome(outcome, mode)
        return Z3RunResult(
            outcome=outcome,
            status=status,
            message=message,
            stdout=stdout,
            stderr=stderr,
            returncode=completed.returncode,
        )

    @staticmethod
    def _error(
        outcome: Z3Outcome,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
    ) -> Z3RunResult:
        return Z3RunResult(
            outcome=outcome,
            status=VerificationStatus.SOLVER_ERROR,
            message=message,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )


def _map_solver_outcome(
    outcome: Z3Outcome, mode: str
) -> tuple[VerificationStatus, str]:
    if outcome == Z3Outcome.UNKNOWN:
        return VerificationStatus.UNKNOWN, "unknown: Z3 returned unknown"
    if mode == "validity":
        if outcome == Z3Outcome.UNSAT:
            return VerificationStatus.VERIFIED, "verified: Z3 proved the obligation"
        return VerificationStatus.VIOLATED, "violated: Z3 found a countermodel"
    if outcome == Z3Outcome.SAT:
        return VerificationStatus.VERIFIED, "verified: Z3 found a satisfying model"
    return VerificationStatus.VIOLATED, "violated: requirements are infeasible"


def _process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
