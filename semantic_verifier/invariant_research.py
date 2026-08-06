"""Deterministic, proposal-only CHC invariant research support.

This module is deliberately isolated from the verification pipeline.  A solver
may propose a loop invariant, but only the ordinary verifier may accept it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from .backend import create_backend
from .model import VerificationStatus, nodes_in
from .pipeline import VerificationPipeline
from .z3_backend import Z3DiscoveryError, discover_z3


ARTIFACT_SCHEMA = "codeskeptic.invariant-candidates/v0"
BENCHMARK_SCHEMA = "codeskeptic.invariant-research-benchmarks/v0"
PINNED_Z3_VERSION = "Z3 version 5.0.0 - 64 bit"
CANDIDATE_MARKER = "// cs: candidate"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_CASE_ID = re.compile(r"[a-z][a-z0-9_]*\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_OPERATORS = frozenset(
    {"and", "or", "not", "=>", "=", "distinct", "<", "<=", ">", ">=", "+", "-", "*"}
)


SExpr = str | tuple["SExpr", ...]
Executor = Callable[..., subprocess.CompletedProcess[str]]


class ResearchInputError(ValueError):
    """Raised for malformed or unsupported research inputs."""


@dataclass(frozen=True, slots=True)
class HornProblem:
    case_id: str
    variables: tuple[str, ...]
    init: SExpr
    transition: SExpr
    bad: SExpr
    source: str | None = None
    timeout_seconds: float | None = None

    @property
    def relation(self) -> str:
        return f"Inv_{self.case_id}"

    @property
    def failure_relation(self) -> str:
        return f"fail_{self.case_id}"


@dataclass(frozen=True, slots=True)
class ResearchBudget:
    """Deterministic count budget for solver-backed corpus cases."""

    max_solver_cases: int | None = None

    def __post_init__(self) -> None:
        if self.max_solver_cases is not None and self.max_solver_cases < 0:
            raise ValueError("max_solver_cases must be non-negative or None")


@dataclass(frozen=True, slots=True)
class SolverProposal:
    status: str
    reason: str
    query: str
    stdout: str = ""
    candidate: str | None = None
    certificate: str | None = None


class SExprParser:
    """Strict parser for the small symbolic fragment used by this spike."""

    def parse(self, text: str) -> SExpr:
        if not isinstance(text, str) or not text.strip():
            raise ResearchInputError("expression must be non-empty text")
        tokens = re.findall(r"\(|\)|[^\s()]+", text)
        if "".join(tokens).replace("(", "").replace(")", "") == "":
            raise ResearchInputError("expression has no atoms")
        value, index = self._parse_at(tokens, 0)
        if index != len(tokens):
            raise ResearchInputError("expression has trailing tokens")
        return value

    def _parse_at(self, tokens: Sequence[str], index: int) -> tuple[SExpr, int]:
        if index >= len(tokens):
            raise ResearchInputError("expression has an unclosed list")
        token = tokens[index]
        if token == ")":
            raise ResearchInputError("expression has an unexpected closing parenthesis")
        if token != "(":
            return token, index + 1
        values: list[SExpr] = []
        index += 1
        while True:
            if index >= len(tokens):
                raise ResearchInputError("expression has an unclosed list")
            if tokens[index] == ")":
                if not values:
                    raise ResearchInputError("empty lists are unsupported")
                return tuple(values), index + 1
            value, index = self._parse_at(tokens, index)
            values.append(value)


def parse_sexpr(text: str) -> SExpr:
    return SExprParser().parse(text)


def emit_sexpr(expression: SExpr) -> str:
    if isinstance(expression, str):
        return expression
    return "(" + " ".join(emit_sexpr(item) for item in expression) + ")"


def parse_problem(raw: Mapping[str, Any]) -> HornProblem:
    required = ("id", "variables", "init", "transition", "bad")
    missing = [name for name in required if name not in raw]
    if missing:
        raise ResearchInputError("missing required fields: " + ", ".join(missing))
    case_id = raw["id"]
    if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
        raise ResearchInputError("id must match [a-z][a-z0-9_]*")
    profile = raw.get("profile", "i32")
    if profile != "i32":
        raise ResearchInputError(f"unsupported profile {profile!r}; only i32 LIA is admitted")
    raw_variables = raw["variables"]
    if not isinstance(raw_variables, list) or not 1 <= len(raw_variables) <= 8:
        raise ResearchInputError("variables must contain between one and eight names")
    if any(not isinstance(name, str) or not _IDENTIFIER.fullmatch(name) for name in raw_variables):
        raise ResearchInputError("variable names must be simple identifiers")
    variables = tuple(raw_variables)
    if len(set(variables)) != len(variables):
        raise ResearchInputError("variable names must be unique")
    if tuple(sorted(variables)) != variables:
        raise ResearchInputError("variable names must be sorted")

    expressions = {
        name: parse_sexpr(raw[name])
        for name in ("init", "transition", "bad")
        if isinstance(raw[name], str)
    }
    if len(expressions) != 3:
        raise ResearchInputError("init, transition, and bad must be text expressions")
    _validate_expression(expressions["init"], variables, allow_next=False)
    _validate_expression(expressions["transition"], variables, allow_next=True)
    _validate_expression(expressions["bad"], variables, allow_next=False)

    source = raw.get("source")
    if source is not None and (not isinstance(source, str) or not source):
        raise ResearchInputError("source must be a non-empty relative path")
    if source is not None and (Path(source).is_absolute() or ".." in Path(source).parts):
        raise ResearchInputError("source must remain inside the benchmark directory")
    timeout = raw.get("timeout_seconds")
    if timeout is not None and (type(timeout) not in {int, float} or timeout <= 0):
        raise ResearchInputError("timeout_seconds must be positive")
    return HornProblem(
        case_id=case_id,
        variables=variables,
        init=expressions["init"],
        transition=expressions["transition"],
        bad=expressions["bad"],
        source=source,
        timeout_seconds=float(timeout) if timeout is not None else None,
    )


def _validate_expression(expression: SExpr, variables: tuple[str, ...], *, allow_next: bool) -> None:
    allowed_atoms = set(variables) | {"true", "false"}
    if allow_next:
        allowed_atoms.update(f"{name}_next" for name in variables)

    def visit(node: SExpr) -> None:
        if isinstance(node, str):
            if node not in allowed_atoms and not _INTEGER.fullmatch(node):
                raise ResearchInputError(f"unsupported expression atom {node!r}")
            return
        head = node[0]
        if not isinstance(head, str) or head not in _OPERATORS:
            raise ResearchInputError(f"unsupported expression operator {emit_sexpr(head)!r}")
        arguments = node[1:]
        arity = len(arguments)
        if head == "not" and arity != 1:
            raise ResearchInputError("not requires one argument")
        if head in {"=>", "=", "distinct", "<", "<=", ">", ">="} and arity != 2:
            raise ResearchInputError(f"{head} requires two arguments")
        if head in {"and", "or", "+", "*"} and arity < 2:
            raise ResearchInputError(f"{head} requires at least two arguments")
        if head == "-" and arity not in {1, 2}:
            raise ResearchInputError("- requires one or two arguments")
        for argument in arguments:
            visit(argument)

    visit(expression)


def emit_horn(problem: HornProblem) -> str:
    sorts = " ".join("Int" for _ in problem.variables)
    current = " ".join(problem.variables)
    next_values = " ".join(f"{name}_next" for name in problem.variables)
    lines = [
        "(set-logic HORN)",
        "(set-option :fp.engine spacer)",
        f"(declare-rel {problem.relation} ({sorts}))",
        f"(declare-rel {problem.failure_relation} ())",
    ]
    for name in problem.variables:
        lines.append(f"(declare-var {name} Int)")
        lines.append(f"(declare-var {name}_next Int)")
    lines.extend(
        (
            f"(rule (=> {emit_sexpr(problem.init)} ({problem.relation} {current})))",
            f"(rule (=> (and ({problem.relation} {current}) {emit_sexpr(problem.transition)}) "
            f"({problem.relation} {next_values})))",
            f"(rule (=> (and ({problem.relation} {current}) {emit_sexpr(problem.bad)}) "
            f"{problem.failure_relation}))",
            f"(query {problem.failure_relation} :print-certificate true)",
        )
    )
    return "\n".join(lines) + "\n"


class SpacerRunner:
    """Pinned Z3/Spacer subprocess runner with deterministic command settings."""

    def __init__(
        self,
        z3: str | None = None,
        timeout_seconds: float = 2.0,
        *,
        expected_version: str = PINNED_Z3_VERSION,
        executor: Executor = subprocess.run,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._configured_z3 = z3
        self.timeout_seconds = float(timeout_seconds)
        self.expected_version = expected_version
        self._executor = executor
        self._executable: str | None = None
        self._version: str | None = None

    @property
    def executable(self) -> str:
        if self._executable is None:
            self._executable = discover_z3(self._configured_z3)
        return self._executable

    def version(self) -> str:
        if self._version is not None:
            return self._version
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        completed = self._executor(
            [self.executable, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1.0, self.timeout_seconds),
            creationflags=flags,
        )
        version = completed.stdout.strip()
        if completed.returncode != 0 or version != self.expected_version:
            shown = version or completed.stderr.strip() or f"exit {completed.returncode}"
            raise ResearchInputError(
                f"solver version mismatch: expected {self.expected_version!r}, got {shown!r}"
            )
        self._version = version
        return version

    def run(self, problem: HornProblem) -> SolverProposal:
        query = emit_horn(problem)
        timeout = problem.timeout_seconds or self.timeout_seconds
        try:
            self.version()
            timeout_ms = max(1, math.ceil(timeout * 1000))
            command = [
                self.executable,
                "-in",
                "-smt2",
                f"timeout={timeout_ms}",
                "smt.random_seed=0",
                "sat.random_seed=0",
                "parallel.enable=false",
                "fp.spacer.random_seed=0",
            ]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            completed = self._executor(
                command,
                input=query,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=flags,
            )
        except subprocess.TimeoutExpired:
            return SolverProposal("timeout", "solver process timeout", query)
        except (OSError, Z3DiscoveryError, ResearchInputError) as error:
            return SolverProposal("malformed", f"solver error: {error}", query)

        stdout = completed.stdout.replace("\r\n", "\n")
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            reason = stderr or stdout.strip() or f"solver exited {completed.returncode}"
            return SolverProposal("malformed", f"solver error: {reason}", query, stdout)
        lines = stdout.splitlines()
        if not lines:
            return SolverProposal("malformed", "solver returned empty output", query, stdout)
        outcome = lines[0].strip()
        if outcome in {"sat", "unknown"}:
            return SolverProposal("no_candidate", f"Spacer returned {outcome}", query, stdout)
        if outcome != "unsat":
            return SolverProposal("malformed", f"unexpected solver outcome {outcome!r}", query, stdout)
        certificate = "\n".join(lines[1:]).strip()
        if not certificate:
            return SolverProposal("malformed", "unsat result omitted a certificate", query, stdout)
        try:
            candidate = extract_candidate(certificate, problem.relation, problem.variables)
        except ResearchInputError as error:
            return SolverProposal("malformed", f"unsupported certificate: {error}", query, stdout, certificate=certificate)
        return SolverProposal(
            "candidate",
            "Spacer produced a candidate",
            query,
            stdout,
            candidate,
            certificate,
        )


def extract_candidate(certificate: str, relation: str, variables: tuple[str, ...]) -> str:
    root = parse_sexpr(certificate)
    definition = _find_relation_definition(root, relation)
    if definition is None:
        raise ResearchInputError(f"certificate does not define {relation}")
    arguments, body, environment = definition
    if len(arguments) != len(variables):
        raise ResearchInputError("certificate relation arity changed")
    mapping = dict(environment)
    for argument, variable in zip(arguments, variables):
        if not isinstance(argument, str) or not _IDENTIFIER.fullmatch(argument):
            raise ResearchInputError("certificate relation arguments must be symbols")
        mapping[argument] = variable
    rendered = _render_candidate(body, mapping)
    if not rendered:
        raise ResearchInputError("certificate produced an empty candidate")
    return rendered


def _find_relation_definition(
    node: SExpr,
    relation: str,
    environment: Mapping[str, SExpr] | None = None,
) -> tuple[tuple[SExpr, ...], SExpr, Mapping[str, SExpr]] | None:
    env: dict[str, SExpr] = dict(environment or {})
    if isinstance(node, str):
        return None
    if node[0] == "forall" and len(node) == 3:
        return _find_relation_definition(node[2], relation, env)
    if node[0] == "!" and len(node) >= 2:
        return _find_relation_definition(node[1], relation, env)
    if node[0] == "let" and len(node) == 3:
        bindings = node[1]
        if not isinstance(bindings, tuple):
            raise ResearchInputError("malformed let bindings")
        additions: dict[str, SExpr] = {}
        for binding in bindings:
            if not isinstance(binding, tuple) or len(binding) != 2 or not isinstance(binding[0], str):
                raise ResearchInputError("malformed let binding")
            additions[binding[0]] = _substitute(binding[1], env)
        env.update(additions)
        return _find_relation_definition(node[2], relation, env)
    if node[0] == "=" and len(node) == 3:
        for call, body in ((node[1], node[2]), (node[2], node[1])):
            if isinstance(call, tuple) and call and call[0] == relation:
                return tuple(call[1:]), body, env
    for child in node[1:]:
        found = _find_relation_definition(child, relation, env)
        if found is not None:
            return found
    return None


def _substitute(node: SExpr, environment: Mapping[str, SExpr]) -> SExpr:
    if isinstance(node, str):
        replacement = environment.get(node)
        return node if replacement is None else _substitute(replacement, environment)
    return tuple(_substitute(item, environment) for item in node)


def _render_candidate(node: SExpr, environment: Mapping[str, SExpr]) -> str:
    node = _substitute(node, environment)
    if isinstance(node, str):
        if node in {"true", "false"} or _INTEGER.fullmatch(node) or _IDENTIFIER.fullmatch(node):
            return node
        raise ResearchInputError(f"unsupported certificate atom {node!r}")
    head = node[0]
    arguments = node[1:]
    if not isinstance(head, str):
        raise ResearchInputError("certificate operator must be a symbol")
    rendered = [_render_candidate(argument, environment) for argument in arguments]
    if head == "not" and len(rendered) == 1:
        return f"!({rendered[0]})"
    if head in {"and", "or"} and len(rendered) >= 2:
        separator = " && " if head == "and" else " || "
        return "(" + separator.join(rendered) + ")"
    if head in {"=", "<", "<=", ">", ">="} and len(rendered) == 2:
        operator = "==" if head == "=" else head
        return f"({rendered[0]} {operator} {rendered[1]})"
    if head in {"+", "*"} and len(rendered) >= 2:
        return "(" + f" {head} ".join(rendered) + ")"
    if head == "-" and len(rendered) == 1:
        value = rendered[0]
        return f"-{value}" if _INTEGER.fullmatch(value) else f"(-{value})"
    if head == "-" and len(rendered) == 2:
        return f"({rendered[0]} - {rendered[1]})"
    raise ResearchInputError(f"unsupported certificate operator {head!r}")


def attach_candidate(source: str, candidate: str) -> str:
    count = source.count(CANDIDATE_MARKER)
    if count != 1:
        raise ResearchInputError(
            f"benchmark source must contain exactly one {CANDIDATE_MARKER!r} marker"
        )
    return source.replace(CANDIDATE_MARKER, f"// cs: ai invariant {candidate}")


def validate_candidate(
    source_path: Path,
    candidate: str,
    *,
    z3: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    proposed_source = attach_candidate(source_path.read_text(encoding="utf-8"), candidate)
    checker = create_backend("both", z3=z3, timeout_seconds=timeout_seconds)
    report = VerificationPipeline(checker=checker).verify_source(
        proposed_source, source_path.as_posix()
    )
    invariant_results = [
        result
        for result in report.results
        if result.kind in {"loop_invariant_entry", "loop_invariant_preservation"}
    ]
    proposed = any(
        invariant.machine_proposed
        for function in report.module.functions
        for node in nodes_in(function.body)
        for invariant in node.invariants
    )
    inductive = bool(invariant_results) and all(
        result.status == VerificationStatus.VERIFIED for result in invariant_results
    )
    accepted = proposed and inductive and all(
        result.status == VerificationStatus.VERIFIED for result in report.results
    )
    return {
        "accepted": accepted,
        "inductive": inductive,
        "machine_proposed": proposed,
        "results": [
            {"kind": result.kind, "status": result.status.value}
            for result in report.results
        ],
        "summary": report.summary(),
    }


def run_corpus(
    manifest_path: str | Path,
    *,
    runner: SpacerRunner | None = None,
    budget: ResearchBudget = ResearchBudget(),
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    raw_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResearchInputError(f"manifest is not valid UTF-8 JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != BENCHMARK_SCHEMA:
        raise ResearchInputError(f"manifest schema must be {BENCHMARK_SCHEMA!r}")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ResearchInputError("manifest cases must be a list")
    raw_ids = [item.get("id") for item in cases if isinstance(item, dict)]
    if len(raw_ids) != len(cases) or any(not isinstance(item, str) for item in raw_ids):
        raise ResearchInputError("every corpus case must have a text id")
    if len(set(raw_ids)) != len(raw_ids):
        raise ResearchInputError("corpus case ids must be unique")

    default_timeout = manifest.get("timeout_seconds", 2.0)
    if type(default_timeout) not in {int, float} or default_timeout <= 0:
        raise ResearchInputError("manifest timeout_seconds must be positive")
    selected_runner = runner or SpacerRunner(timeout_seconds=float(default_timeout))
    solver_version: str
    try:
        solver_version = selected_runner.version()
    except (ResearchInputError, Z3DiscoveryError, OSError) as error:
        solver_version = f"unavailable: {error}"

    records: list[dict[str, Any]] = []
    solver_count = 0
    for raw in sorted(cases, key=lambda item: item["id"]):
        case_id = raw["id"]
        record: dict[str, Any] = {"id": case_id}
        try:
            problem = parse_problem(raw)
        except ResearchInputError as error:
            status = "unsupported" if str(error).startswith("unsupported profile") else "malformed"
            record.update({"reason": str(error), "status": status})
            records.append(record)
            continue
        query = emit_horn(problem)
        record["query_sha256"] = _sha256_text(query)
        if budget.max_solver_cases is not None and solver_count >= budget.max_solver_cases:
            record.update({"reason": "deterministic solver-case budget exhausted", "status": "no_candidate"})
            records.append(record)
            continue
        solver_count += 1
        proposal = selected_runner.run(problem)
        record["reason"] = proposal.reason
        if proposal.certificate is not None:
            record["certificate_sha256"] = _sha256_text(proposal.certificate)
        if proposal.candidate is None:
            record["status"] = proposal.status
            records.append(record)
            continue
        record["candidate"] = proposal.candidate
        if problem.source is None:
            record.update({"reason": "candidate case omitted benchmark source", "status": "malformed"})
            records.append(record)
            continue
        source_path = (manifest_path.parent / problem.source).resolve()
        if manifest_path.parent not in source_path.parents:
            record.update({"reason": "benchmark source escaped corpus directory", "status": "malformed"})
            records.append(record)
            continue
        if not source_path.is_file():
            record.update({"reason": f"benchmark source not found: {problem.source}", "status": "malformed"})
            records.append(record)
            continue
        try:
            validation = validate_candidate(
                source_path,
                proposal.candidate,
                z3=selected_runner.executable,
                timeout_seconds=float(default_timeout),
            )
        except (OSError, ResearchInputError) as error:
            record.update({"reason": f"candidate validation failed: {error}", "status": "malformed"})
            records.append(record)
            continue
        record["source_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        record["validation"] = validation
        if not validation["inductive"] or not validation["machine_proposed"]:
            record.update({"reason": "ordinary verifier rejected the proposed invariant", "status": "malformed"})
        elif validation["accepted"]:
            record.update({"reason": "ordinary verifier accepted every obligation", "status": "useful"})
        else:
            record.update({"reason": "candidate is inductive but insufficient for full verification", "status": "insufficient"})
        records.append(record)

    return {
        "cases": records,
        "manifest_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "policy": {
            "max_solver_cases": budget.max_solver_cases,
            "timeout_seconds": float(default_timeout),
        },
        "schema": ARTIFACT_SCHEMA,
        "solver": {
            "command_policy": "z3-spacer-deterministic-seeds/v0",
            "required_version": PINNED_Z3_VERSION,
            "version": solver_version,
        },
    }


def render_artifact(artifact: Mapping[str, Any]) -> str:
    return json.dumps(artifact, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()