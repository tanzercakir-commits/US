"""Owned Semantic IR and verification-result data model.

Nothing in this module knows about Clang. Frontend-specific identities never
escape into the serialized IR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Iterable, Mapping

from .integer_types import I32, canonical_decimal, is_fixed_integer_type


SCHEMA = "codeskeptic.semantic-verification/v2"
INT_MIN = I32.minimum
INT_MAX = I32.maximum


@dataclass(frozen=True, order=True, slots=True)
class SourceLocation:
    file: str
    line: int
    column: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "column": self.column}


@dataclass(frozen=True, slots=True)
class Expr:
    """A typed expression in the logic-facing IR."""

    kind: str
    type: str
    value: int | bool | str | None = None
    op: str | None = None
    args: tuple["Expr", ...] = ()

    @staticmethod
    def integer(value: int, type_name: str = "i32") -> "Expr":
        if not is_fixed_integer_type(type_name):
            raise ValueError(f"unsupported fixed-width integer type {type_name!r}")
        return Expr("constant", type_name, value=value)

    @staticmethod
    def boolean(value: bool) -> "Expr":
        return Expr("constant", "bool", value=value)

    @staticmethod
    def variable(name: str, type_name: str = "i32") -> "Expr":
        return Expr("variable", type_name, value=name)

    @staticmethod
    def unary(op: str, arg: "Expr", type_name: str | None = None) -> "Expr":
        return Expr("unary", type_name or arg.type, op=op, args=(arg,))

    @staticmethod
    def binary(
        op: str, left: "Expr", right: "Expr", type_name: str | None = None
    ) -> "Expr":
        if type_name is None:
            type_name = (
                "bool"
                if op in {"==", "!=", "<", "<=", ">", ">=", "&&", "||"}
                else left.type
            )
        return Expr("binary", type_name, op=op, args=(left, right))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": self.kind, "type": self.type}
        if self.value is not None:
            result["value"] = (
                canonical_decimal(self.value)
                if self.kind == "constant" and is_fixed_integer_type(self.type)
                else self.value
            )
        if self.op is not None:
            result["op"] = self.op
        if self.args:
            result["args"] = [arg.to_dict() for arg in self.args]
        return result

    def variables(self) -> set[str]:
        if self.kind == "variable":
            return {str(self.value)}
        found: set[str] = set()
        for arg in self.args:
            found.update(arg.variables())
        return found

    def substitute(self, replacements: Mapping[str, "Expr"]) -> "Expr":
        if self.kind == "variable" and str(self.value) in replacements:
            return replacements[str(self.value)]
        if not self.args:
            return self
        new_args = tuple(arg.substitute(replacements) for arg in self.args)
        if new_args == self.args:
            return self
        return Expr(self.kind, self.type, self.value, self.op, new_args)

    def text(self) -> str:
        if self.kind == "constant":
            if self.type == "bool":
                return "true" if self.value else "false"
            return str(self.value)
        if self.kind == "variable":
            return str(self.value)
        if self.kind == "unary":
            return f"({self.op}{self.args[0].text()})"
        if self.kind == "binary":
            return f"({self.args[0].text()} {self.op} {self.args[1].text()})"
        return f"<{self.kind}>"


@dataclass(frozen=True, slots=True)
class Contract:
    kind: str
    expression: Expr
    location: SourceLocation
    text: str
    machine_proposed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression.to_dict(),
            "kind": self.kind,
            "location": self.location.to_dict(),
            "machine_proposed": self.machine_proposed,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class Symbol:
    id: str
    # Stable verifier identity; may differ from the source spelling when a
    # later declaration reuses a name in a disjoint lexical scope.
    name: str
    type: str
    versioned_name: str
    location: SourceLocation
    source_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "location": self.location.to_dict(),
            "name": self.source_name or self.name,
            "type": self.type,
            "versioned_name": self.versioned_name,
        }
        if self.source_name is not None and self.source_name != self.name:
            result["ir_name"] = self.name
        return result


@dataclass(frozen=True, slots=True)
class LoopVariable:
    """SSA state carried across a loop back edge and its nondeterministic exit."""

    name: str
    type: str
    entry: str
    head: str
    back_edge: str
    exit: str

    def to_dict(self) -> dict[str, str]:
        return {
            "back_edge": self.back_edge,
            "entry": self.entry,
            "exit": self.exit,
            "head": self.head,
            "name": self.name,
            "type": self.type,
        }


@dataclass(frozen=True, slots=True)
class IRNode:
    id: str
    kind: str
    location: SourceLocation
    target: str | None = None
    result_type: str | None = None
    expression: Expr | None = None
    origin: str | None = None
    callee: str | None = None
    arguments: tuple[Expr, ...] = ()
    invariants: tuple[Contract, ...] = ()
    loop_variables: tuple[LoopVariable, ...] = ()
    body: tuple["IRNode", ...] = ()
    then_body: tuple["IRNode", ...] = ()
    else_body: tuple["IRNode", ...] = ()
    merges: tuple["IRNode", ...] = ()
    incoming_true: Expr | None = None
    incoming_false: Expr | None = None
    reason: str | None = None
    termination: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "location": self.location.to_dict(),
        }
        for key, value in {
            "target": self.target,
            "result_type": self.result_type,
            "origin": self.origin,
            "callee": self.callee,
            "reason": self.reason,
            "termination": self.termination,
        }.items():
            if value is not None:
                result[key] = value
        if self.expression is not None:
            result["expression"] = self.expression.to_dict()
        if self.arguments:
            result["arguments"] = [arg.to_dict() for arg in self.arguments]
        if self.kind == "loop":
            result["body"] = [node.to_dict() for node in self.body]
            result["invariants"] = [
                invariant.to_dict() for invariant in self.invariants
            ]
            result["loop_variables"] = [
                variable.to_dict() for variable in self.loop_variables
            ]
        if self.then_body:
            result["then"] = [node.to_dict() for node in self.then_body]
        if self.else_body:
            result["else"] = [node.to_dict() for node in self.else_body]
        if self.merges:
            result["merges"] = [node.to_dict() for node in self.merges]
        if self.incoming_true is not None:
            result["incoming_true"] = self.incoming_true.to_dict()
        if self.incoming_false is not None:
            result["incoming_false"] = self.incoming_false.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class FunctionIR:
    id: str
    name: str
    return_type: str
    location: SourceLocation
    parameters: tuple[Symbol, ...]
    locals: tuple[Symbol, ...]
    contracts: tuple[Contract, ...]
    body: tuple[IRNode, ...]
    has_body: bool = True
    link_name: str | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.link_name or self.name, len(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "body": [node.to_dict() for node in self.body],
            "contracts": [contract.to_dict() for contract in self.contracts],
            "has_body": self.has_body,
            "id": self.id,
            "locals": [symbol.to_dict() for symbol in self.locals],
            "location": self.location.to_dict(),
            "name": self.name,
            "parameters": [symbol.to_dict() for symbol in self.parameters],
            "return_type": self.return_type,
        }
        if self.link_name is not None and self.link_name != self.name:
            result["link_name"] = self.link_name
        return result


@dataclass(frozen=True, slots=True)
class ModuleIR:
    source: str
    functions: tuple[FunctionIR, ...]
    unsupported: tuple[IRNode, ...] = ()
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "functions": [function.to_dict() for function in self.functions],
            "schema": self.schema,
            "source": self.source,
            "unsupported": [node.to_dict() for node in self.unsupported],
        }


@dataclass(frozen=True, slots=True)
class TraceTemplate:
    kind: str
    condition: Expr
    guard: tuple[Expr, ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class TraceStep:
    kind: str
    condition: Expr
    taken: bool
    location: SourceLocation

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition.to_dict(),
            "kind": self.kind,
            "location": self.location.to_dict(),
            "taken": self.taken,
        }

    def text(self) -> str:
        label = {
            "branch": "branch condition",
            "loop_condition": "loop condition",
            "short_circuit": "short-circuit condition",
        }.get(self.kind, self.kind.replace("_", " "))
        value = "true" if self.taken else "false"
        return f"when {label} {self.condition.text()} is {value}"


@dataclass(frozen=True, slots=True)
class Obligation:
    id: str
    function: str
    kind: str
    assumptions: tuple[Expr, ...]
    conclusion: Expr | None
    location: SourceLocation
    description: str
    unsupported_reason: str | None = None
    mode: str = "validity"
    trace_templates: tuple[TraceTemplate, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "assumptions": [expr.to_dict() for expr in self.assumptions],
            "description": self.description,
            "function": self.function,
            "id": self.id,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "mode": self.mode,
        }
        if self.conclusion is not None:
            result["conclusion"] = self.conclusion.to_dict()
        if self.unsupported_reason is not None:
            result["unsupported_reason"] = self.unsupported_reason
        return result

    def formula_text(self) -> str:
        premise = " && ".join(expr.text() for expr in self.assumptions) or "true"
        if self.mode == "satisfiable":
            return f"satisfiable({premise})"
        if self.mode == "well_formed":
            expression = self.conclusion.text() if self.conclusion else "<missing>"
            return f"well_formed({expression})"
        goal = self.conclusion.text() if self.conclusion else "<unsupported>"
        return f"({premise}) -> {goal}"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    VIOLATED = "violated"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    SOLVER_ERROR = "solver_error"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    obligation_id: str
    function: str
    kind: str
    status: VerificationStatus
    location: SourceLocation
    message: str
    counterexample: Mapping[str, int | bool] | None = None
    trace: tuple[TraceStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "function": self.function,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "message": self.message,
            "obligation": self.obligation_id,
            "status": self.status.value,
        }
        if self.counterexample is not None:
            result["counterexample"] = {
                key: (
                    self.counterexample[key]
                    if type(self.counterexample[key]) is bool
                    else canonical_decimal(self.counterexample[key])
                )
                for key in sorted(self.counterexample)
            }
        if self.trace:
            result["trace"] = [step.to_dict() for step in self.trace]
        return result


@dataclass(frozen=True, slots=True)
class NonGoalRecord:
    kind: str
    location: SourceLocation
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "kind": self.kind,
            "location": self.location.to_dict(),
        }

@dataclass(frozen=True, slots=True)
class VerificationReport:
    module: ModuleIR
    obligations: tuple[Obligation, ...]
    results: tuple[VerificationResult, ...]

    def summary(self) -> dict[str, int]:
        counts = {status.value: 0 for status in VerificationStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts

    def non_goals(self) -> tuple[NonGoalRecord, ...]:
        records: list[NonGoalRecord] = []
        for function in self.module.functions:
            for node in nodes_in(function.body):
                if node.kind != "loop" or node.termination != "non_goal":
                    continue
                records.append(
                    NonGoalRecord(
                        kind="loop_termination",
                        location=node.location,
                        description=(
                            "termination is not checked; verified loop "
                            "obligations establish partial correctness only"
                        ),
                    )
                )
        return tuple(records)

    def to_dict(self, include_ir: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "non_goals": [item.to_dict() for item in self.non_goals()],
            "obligations": [item.to_dict() for item in self.obligations],
            "results": [item.to_dict() for item in self.results],
            "schema": SCHEMA,
            "source": self.module.source,
            "summary": self.summary(),
        }
        if include_ir:
            result["semantic_ir"] = self.module.to_dict()
        return result

    def to_json(self, include_ir: bool = True) -> str:
        return (
            json.dumps(
                self.to_dict(include_ir=include_ir),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )


def nodes_in(nodes: Iterable[IRNode]) -> Iterable[IRNode]:
    for node in nodes:
        yield node
        yield from nodes_in(node.body)
        yield from nodes_in(node.then_body)
        yield from nodes_in(node.else_body)
        yield from nodes_in(node.merges)

def expressions_in(nodes: Iterable[IRNode]) -> Iterable[Expr]:
    for node in nodes:
        if node.expression is not None:
            yield node.expression
        yield from node.arguments
        if node.incoming_true is not None:
            yield node.incoming_true
        if node.incoming_false is not None:
            yield node.incoming_false
        for invariant in node.invariants:
            yield invariant.expression
        yield from expressions_in(node.body)
        yield from expressions_in(node.then_body)
        yield from expressions_in(node.else_body)
        yield from expressions_in(node.merges)
