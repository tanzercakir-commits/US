"""Deterministic subprocess runner for the Z3 SMT solver."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
import glob
import math
import os
from pathlib import Path
import shutil
import subprocess

from .array_types import array_type, is_array_type
from .budget import SolverTimeout
from .checker import evaluate, resolve_trace
from .counterexample import minimize_counterexample
from .integer_types import convert_integer, integer_type, is_fixed_integer_type
from .model import (
    Expr,
    Obligation,
    TraceStep,
    VerificationResult,
    VerificationStatus,
)
from .smtlib import SmtLibEmissionError, decode_symbol, emit_smtlib


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
        timeout_seconds: float | SolverTimeout = 5.0,
    ) -> None:
        timeout = (
            timeout_seconds
            if isinstance(timeout_seconds, SolverTimeout)
            else SolverTimeout(timeout_seconds)
        )
        self._configured_z3 = z3
        self.timeout_seconds = timeout.seconds

    def cache_identity(self) -> Mapping[str, object]:
        """Describe every runner setting that can change a returned result."""

        try:
            executable = Path(discover_z3(self._configured_z3)).as_posix()
        except Z3DiscoveryError:
            executable = self._configured_z3
        return {
            "command_policy": "homogeneous-qf-lia-qf-bv-qf-array-deterministic-seeds/v2",
            "executable": executable,
            "timeout_seconds": self.timeout_seconds,
        }

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


class Z3ModelError(ValueError):
    """Raised when solver model output is malformed or incomplete."""


EvidenceValue = int | bool | tuple[int, ...]


def parse_z3_model(
    output: str,
    expected_types: Mapping[str, str] | None = None,
) -> dict[str, EvidenceValue]:
    """Parse zero-arity scalar/owned-array models into source-level bindings."""

    expressions = _parse_s_expressions(output)
    if len(expressions) != 2 or expressions[0] != "sat":
        raise Z3ModelError("model output must contain a leading sat result")
    model = expressions[1]
    if not isinstance(model, list):
        raise Z3ModelError("model output must contain an S-expression")
    forms = model[1:] if model and model[0] == "model" else model

    bindings: dict[str, EvidenceValue] = {}
    sorts: dict[str, str] = {}
    for form in forms:
        if (
            not isinstance(form, list)
            or len(form) != 5
            or form[0] != "define-fun"
            or not isinstance(form[1], str)
            or form[2] != []
        ):
            raise Z3ModelError("model contains an unsupported definition")
        try:
            source_name = decode_symbol(form[1])
        except SmtLibEmissionError as error:
            raise Z3ModelError(f"invalid model symbol {form[1]!r}: {error}") from error
        if source_name in bindings:
            raise Z3ModelError(f"duplicate model binding for {source_name!r}")
        sort = _normalize_model_sort(form[3])
        expected_type = (
            expected_types.get(source_name)
            if expected_types is not None
            else None
        )
        bindings[source_name] = _parse_model_value(
            form[4], sort, expected_type
        )
        sorts[source_name] = sort

    if expected_types is not None:
        expected_names = set(expected_types)
        actual_names = set(bindings)
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            raise Z3ModelError(
                f"model binding mismatch: missing={missing!r}, "
                f"unexpected={unexpected!r}"
            )
        fixed_sorts = {
            sorts[name]
            for name, type_name in expected_types.items()
            if is_fixed_integer_type(type_name)
        }
        if "Int" in fixed_sorts and any(
            sort.startswith("BitVec") for sort in fixed_sorts
        ):
            raise Z3ModelError("model mixes Int and BitVec fixed-width bindings")
        for name in sorted(expected_types):
            type_name = expected_types[name]
            actual_sort = sorts[name]
            if type_name == "bool":
                expected_sorts = {"Bool"}
            elif is_fixed_integer_type(type_name):
                profile = integer_type(type_name)
                expected_sorts = {f"BitVec{profile.width}"}
                if profile.signed:
                    expected_sorts.add("Int")
            elif is_array_type(type_name):
                profile = array_type(type_name)
                element = integer_type(profile.element_type)
                expected_sorts = {
                    f"Array[BitVec64,BitVec{element.width}]"
                }
                if element.signed:
                    expected_sorts.add("Array[Int,Int]")
            else:
                expected_sorts = set()
            if actual_sort not in expected_sorts:
                raise Z3ModelError(
                    f"model sort mismatch for {name!r}: "
                    f"expected {sorted(expected_sorts)!r}, got {actual_sort!r}"
                )
            if actual_sort.startswith("BitVec"):
                bindings[name] = convert_integer(int(bindings[name]), type_name)
            elif actual_sort.startswith("Array[BitVec"):
                profile = array_type(type_name)
                bindings[name] = tuple(
                    convert_integer(int(item), profile.element_type)
                    for item in bindings[name]  # type: ignore[union-attr]
                )
    return bindings


def check_obligation(
    obligation: Obligation,
    runner: Z3ProcessRunner | None = None,
) -> VerificationResult:
    """Check one obligation and replay any countermodel before returning it."""

    runner = runner or Z3ProcessRunner()
    if obligation.unsupported_reason:
        return _obligation_result(
            obligation,
            VerificationStatus.UNSUPPORTED,
            f"unsupported: {obligation.unsupported_reason}",
        )
    if obligation.mode == "well_formed":
        if obligation.conclusion is None:
            return _obligation_result(
                obligation,
                VerificationStatus.UNSUPPORTED,
                "unsupported: missing logical conclusion",
            )
        try:
            emit_smtlib(replace(obligation, mode="validity"))
        except SmtLibEmissionError as error:
            return _obligation_result(
                obligation,
                VerificationStatus.UNSUPPORTED,
                f"unsupported: {error}",
            )
        return _obligation_result(
            obligation,
            VerificationStatus.VERIFIED,
            "verified: contract expression is in the supported logic fragment",
        )
    try:
        query = emit_smtlib(obligation)
    except SmtLibEmissionError as error:
        return _obligation_result(
            obligation,
            VerificationStatus.UNSUPPORTED,
            f"unsupported: {error}",
        )

    first = runner.run(query, obligation.mode)
    if first.outcome != Z3Outcome.SAT or obligation.mode != "validity":
        return _obligation_result(obligation, first.status, first.message)

    model_query = query.rstrip() + "\n(get-model)\n"
    second = runner.run(model_query, obligation.mode)
    if second.outcome == Z3Outcome.TIMEOUT:
        return _obligation_result(
            obligation,
            VerificationStatus.UNKNOWN,
            "unknown: Z3 timed out while requesting a replayable countermodel",
        )
    if second.outcome != Z3Outcome.SAT:
        return _obligation_result(
            obligation,
            VerificationStatus.SOLVER_ERROR,
            "solver error: Z3 model query disagreed with the initial sat result",
        )
    expressions = obligation.assumptions + (obligation.conclusion,)
    assert obligation.conclusion is not None
    expected_types = _variable_types(expressions)
    try:
        model = parse_z3_model(second.stdout, expected_types)
        if not all(bool(evaluate(item, model)) for item in obligation.assumptions):
            raise Z3ModelError("countermodel does not satisfy the assumptions")
        if bool(evaluate(obligation.conclusion, model)):
            raise Z3ModelError("countermodel does not falsify the conclusion")
        trace = resolve_trace(obligation.trace_templates, model)
    except (ArithmeticError, KeyError, TypeError, ValueError) as error:
        return _obligation_result(
            obligation,
            VerificationStatus.SOLVER_ERROR,
            f"solver error: countermodel replay failed: {error}",
        )
    minimized = minimize_counterexample(
        obligation,
        model,
        lambda assumptions, conclusion: _proves_violation_core(
            obligation,
            assumptions,
            conclusion,
            runner,
        ),
    )
    return _obligation_result(
        obligation,
        VerificationStatus.VIOLATED,
        (
            "violated: Z3 countermodel replayed successfully; "
            f"minimized from {len(model)} to {len(minimized)} bindings"
        ),
        _human_counterexample(minimized),
        trace,
    )


def _proves_violation_core(
    obligation: Obligation,
    assumptions: tuple[Expr, ...],
    conclusion: Expr,
    runner: Z3ProcessRunner,
) -> bool:
    candidate = replace(
        obligation,
        assumptions=assumptions,
        conclusion=conclusion,
        mode="validity",
        unsupported_reason=None,
    )
    try:
        query = emit_smtlib(candidate)
    except SmtLibEmissionError:
        return False
    return runner.run(query, "validity").outcome == Z3Outcome.UNSAT


def _parse_s_expressions(text: str) -> list[str | list[object]]:
    if not isinstance(text, str):
        raise Z3ModelError("model output must be text")
    tokens = _tokenize_s_expressions(text)
    expressions: list[str | list[object]] = []

    def parse(index: int) -> tuple[str | list[object], int]:
        if index >= len(tokens):
            raise Z3ModelError("unexpected end of model output")
        token = tokens[index]
        if token == ")":
            raise Z3ModelError("unexpected ')' in model output")
        if token != "(":
            return token, index + 1
        values: list[object] = []
        index += 1
        while True:
            if index >= len(tokens):
                raise Z3ModelError("unterminated model S-expression")
            if tokens[index] == ")":
                return values, index + 1
            value, index = parse(index)
            values.append(value)

    index = 0
    while index < len(tokens):
        expression, index = parse(index)
        expressions.append(expression)
    return expressions


def _tokenize_s_expressions(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if character == ";":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if character in "()":
            tokens.append(character)
            index += 1
            continue
        if character in {'"', "|"}:
            raise Z3ModelError("quoted model tokens are unsupported")
        end = index
        while end < len(text) and not text[end].isspace() and text[end] not in "();":
            end += 1
        if end == index:
            raise Z3ModelError(f"invalid model character {character!r}")
        tokens.append(text[index:end])
        index = end
    return tokens


def _normalize_model_sort(value: object) -> str:
    if isinstance(value, str) and value in {"Bool", "Int"}:
        return str(value)
    if (
        isinstance(value, list)
        and len(value) == 3
        and value[0] == "_"
        and value[1] == "BitVec"
        and isinstance(value[2], str)
        and value[2].isdecimal()
        and int(value[2]) > 0
    ):
        return f"BitVec{value[2]}"
    if (
        isinstance(value, list)
        and len(value) == 3
        and value[0] == "Array"
    ):
        index_sort = _normalize_model_sort(value[1])
        element_sort = _normalize_model_sort(value[2])
        if index_sort not in {"Int", "BitVec64"}:
            raise Z3ModelError("owned array model index sort must be Int or BitVec64")
        if element_sort == "Bool" or element_sort.startswith("Array["):
            raise Z3ModelError("owned array model element sort must be integer")
        return f"Array[{index_sort},{element_sort}]"
    raise Z3ModelError(f"unsupported model sort {value!r}")


def _parse_model_value(
    value: object,
    sort: str,
    expected_type: str | None = None,
) -> EvidenceValue:
    if sort.startswith("Array["):
        if expected_type is None or not is_array_type(expected_type):
            raise Z3ModelError("array model parsing requires an expected array type")
        profile = array_type(expected_type)
        index_sort, element_sort = _array_sort_parts(sort)
        default, updates = _parse_array_value(
            value, sort, index_sort, element_sort
        )
        return tuple(
            int(updates.get(index, default))
            for index in range(profile.length)
        )
    if sort == "Bool":
        if value == "true":
            return True
        if value == "false":
            return False
        raise Z3ModelError(f"unsupported Bool model value {value!r}")
    if sort.startswith("BitVec"):
        width = int(sort.removeprefix("BitVec"))
        parsed: int | None = None
        if isinstance(value, str) and value.startswith("#x"):
            digits = value[2:]
            if digits and all(character in "0123456789abcdefABCDEF" for character in digits):
                parsed = int(digits, 16)
        elif isinstance(value, str) and value.startswith("#b"):
            digits = value[2:]
            if digits and all(character in "01" for character in digits):
                parsed = int(digits, 2)
        elif (
            isinstance(value, list)
            and len(value) == 3
            and value[0] == "_"
            and isinstance(value[1], str)
            and value[1].startswith("bv")
            and value[1][2:].isdecimal()
            and value[2] == str(width)
        ):
            parsed = int(value[1][2:])
        if parsed is None or not 0 <= parsed < 2**width:
            raise Z3ModelError(f"unsupported {sort} model value {value!r}")
        return parsed
    if sort != "Int":
        raise Z3ModelError(f"unsupported model sort {sort!r}")
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    if (
        isinstance(value, list)
        and len(value) == 2
        and value[0] == "-"
        and isinstance(value[1], str)
        and value[1].isdecimal()
    ):
        return -int(value[1])
    raise Z3ModelError(f"unsupported Int model value {value!r}")


def _array_sort_parts(sort: str) -> tuple[str, str]:
    if not sort.startswith("Array[") or not sort.endswith("]"):
        raise Z3ModelError(f"malformed array sort {sort!r}")
    payload = sort[6:-1]
    index_sort, separator, element_sort = payload.partition(",")
    if not separator or not index_sort or not element_sort:
        raise Z3ModelError(f"malformed array sort {sort!r}")
    return index_sort, element_sort


def _parse_array_value(
    value: object,
    sort: str,
    index_sort: str,
    element_sort: str,
) -> tuple[int, dict[int, int]]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], list)
        and value[0] == ["as", "const", _model_sort_expression(sort)]
    ):
        default = _parse_model_value(value[1], element_sort)
        if type(default) is not int:
            raise Z3ModelError("array default must be an integer")
        return default, {}
    if (
        isinstance(value, list)
        and len(value) == 4
        and value[0] == "store"
    ):
        default, updates = _parse_array_value(
            value[1], sort, index_sort, element_sort
        )
        index = _parse_model_value(value[2], index_sort)
        element = _parse_model_value(value[3], element_sort)
        if type(index) is not int or type(element) is not int:
            raise Z3ModelError("array store model terms must be integers")
        updated = dict(updates)
        updated[index] = element
        return default, updated
    raise Z3ModelError(f"unsupported array model value {value!r}")


def _model_sort_expression(sort: str) -> object:
    if sort == "Int":
        return "Int"
    if sort == "Bool":
        return "Bool"
    if sort.startswith("BitVec"):
        return ["_", "BitVec", sort.removeprefix("BitVec")]
    index_sort, element_sort = _array_sort_parts(sort)
    return [
        "Array",
        _model_sort_expression(index_sort),
        _model_sort_expression(element_sort),
    ]


def _variable_types(expressions: tuple[Expr | None, ...]) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(expression: Expr) -> None:
        if expression.kind == "variable":
            name = str(expression.value)
            previous = result.get(name)
            if previous is not None and previous != expression.type:
                raise Z3ModelError(f"conflicting types for model variable {name!r}")
            result[name] = expression.type
        for argument in expression.args:
            visit(argument)

    for expression in expressions:
        if expression is not None:
            visit(expression)
    return result


def _human_counterexample(
    model: Mapping[str, EvidenceValue],
) -> dict[str, EvidenceValue]:
    result: dict[str, EvidenceValue] = {}
    for name in sorted(model):
        base, separator, version = name.partition("#")
        shown = base if separator and version == "0" else name
        if shown in result:
            shown = name
        result[shown] = model[name]
    return result


def _obligation_result(
    obligation: Obligation,
    status: VerificationStatus,
    message: str,
    counterexample: Mapping[str, EvidenceValue] | None = None,
    trace: tuple[TraceStep, ...] = (),
) -> VerificationResult:
    return VerificationResult(
        obligation_id=obligation.id,
        function=obligation.function,
        kind=obligation.kind,
        status=status,
        location=obligation.location,
        message=message,
        counterexample=counterexample,
        trace=trace,
    )
