"""Owned Semantic IR and verification-result data model.

Nothing in this module knows about Clang. Frontend-specific identities never
escape into the serialized IR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Iterable, Mapping

from .array_types import array_type, make_array_type
from .record_types import RecordType, RecordValue, record_type
from .integer_types import I32, canonical_decimal, is_fixed_integer_type


SCHEMA = "codeskeptic.semantic-verification/v6"
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
    def cast(arg: "Expr", type_name: str) -> "Expr":
        if arg.type == type_name:
            return arg
        return Expr("cast", type_name, op="integral", args=(arg,))

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

    @staticmethod
    def predicate(op: str, *args: "Expr") -> "Expr":
        return Expr("predicate", "bool", op=op, args=tuple(args))

    @staticmethod
    def array(elements: Iterable["Expr"], element_type: str) -> "Expr":
        values = tuple(elements)
        type_name = make_array_type(element_type, len(values))
        if any(value.type != element_type for value in values):
            raise ValueError("array elements must have the declared element type")
        return Expr("array", type_name, args=values)

    @staticmethod
    def record(values: Iterable["Expr"], type_name: str) -> "Expr":
        profile = record_type(type_name)
        fields = tuple(values)
        if len(fields) != len(profile.fields) or any(
            value.type != field.type
            for value, field in zip(fields, profile.fields)
        ):
            raise ValueError("record fields do not match the declared type")
        return Expr("record", type_name, args=fields)

    @staticmethod
    def project(value: "Expr", field_name: str) -> "Expr":
        field = record_type(value.type).field(field_name)
        return Expr("project", field.type, value=field_name, args=(value,))

    @staticmethod
    def update(value: "Expr", field_name: str, replacement: "Expr") -> "Expr":
        field = record_type(value.type).field(field_name)
        if replacement.type != field.type:
            raise ValueError("record update value has the wrong field type")
        return Expr(
            "update",
            value.type,
            value=field_name,
            args=(value, replacement),
        )

    @staticmethod
    def select(array: "Expr", index: "Expr") -> "Expr":
        profile = array_type(array.type)
        if not is_fixed_integer_type(index.type):
            raise ValueError("array index must be a fixed-width integer")
        return Expr("select", profile.element_type, args=(array, index))

    @staticmethod
    def store(array: "Expr", index: "Expr", value: "Expr") -> "Expr":
        profile = array_type(array.type)
        if not is_fixed_integer_type(index.type):
            raise ValueError("array index must be a fixed-width integer")
        if value.type != profile.element_type:
            raise ValueError("array store value has the wrong element type")
        return Expr("store", array.type, args=(array, index, value))

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
        if self.kind == "cast":
            return f"(({self.type}) {self.args[0].text()})"
        if self.kind == "binary":
            return f"({self.args[0].text()} {self.op} {self.args[1].text()})"
        if self.kind == "predicate":
            arguments = ", ".join(argument.text() for argument in self.args)
            return f"{self.op}({arguments})"
        if self.kind == "array":
            return "{" + ", ".join(argument.text() for argument in self.args) + "}"
        if self.kind == "record":
            profile = record_type(self.type)
            fields = ", ".join(
                f"{field.name}={value.text()}"
                for field, value in zip(profile.fields, self.args)
            )
            return f"{profile.source_name}{{{fields}}}"
        if self.kind == "project":
            return f"{self.args[0].text()}.{self.value}"
        if self.kind == "update":
            return (
                f"update({self.args[0].text()}, {self.value}, "
                f"{self.args[1].text()})"
            )
        if self.kind == "select":
            return f"{self.args[0].text()}[{self.args[1].text()}]"
        if self.kind == "store":
            return (
                f"store({self.args[0].text()}, {self.args[1].text()}, "
                f"{self.args[2].text()})"
            )
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
class ReferencePathStep:
    kind: str
    value: str
    type: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"field", "index"}:
            raise ValueError("reference path step kind is unsupported")
        if not self.value:
            raise ValueError("reference path step value must be non-empty")
        if (self.kind == "index") != (self.type is not None):
            raise ValueError("only reference index steps carry a type")

    def to_dict(self) -> dict[str, str]:
        result = {"kind": self.kind, "value": self.value}
        if self.type is not None:
            result["type"] = self.type
        return result


@dataclass(frozen=True, slots=True)
class FrameLocation:
    root: str
    path: tuple[ReferencePathStep, ...]
    type: str

    def __post_init__(self) -> None:
        if not self.root or not self.type:
            raise ValueError("frame location root and type must be non-empty")
        if any(step.kind != "field" for step in self.path):
            raise ValueError("only field frame paths are supported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": [step.to_dict() for step in self.path],
            "root": self.root,
            "type": self.type,
        }


@dataclass(frozen=True, slots=True)
class FrameContract:
    targets: tuple[FrameLocation, ...]
    location: SourceLocation
    text: str
    machine_proposed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location.to_dict(),
            "machine_proposed": self.machine_proposed,
            "targets": [target.to_dict() for target in self.targets],
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class CallFrameEffect:
    root: str
    type: str
    before: str
    after: str
    modified: tuple[FrameLocation, ...]

    def __post_init__(self) -> None:
        if not self.modified:
            raise ValueError("call frame effect must modify at least one location")
        if any(location.root != self.root for location in self.modified):
            raise ValueError("call frame effect locations must share one root")

    def to_dict(self) -> dict[str, Any]:
        return {
            "after": self.after,
            "before": self.before,
            "modified": [location.to_dict() for location in self.modified],
            "root": self.root,
            "type": self.type,
        }


@dataclass(frozen=True, slots=True)
class ReferenceBinding:
    id: str
    name: str
    type: str
    target: str
    path: tuple[ReferencePathStep, ...]
    mutable: bool
    location: SourceLocation
    lifetime: str = "enclosing_lexical_scope"

    def __post_init__(self) -> None:
        if self.lifetime != "enclosing_lexical_scope":
            raise ValueError("reference lifetime policy is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lifetime": self.lifetime,
            "location": self.location.to_dict(),
            "mutable": self.mutable,
            "name": self.name,
            "path": [step.to_dict() for step in self.path],
            "target": self.target,
            "type": self.type,
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
    passing: str | None = None

    def __post_init__(self) -> None:
        if self.passing not in {None, "value", "const_reference", "mutable_reference"}:
            raise ValueError("symbol passing mode is unsupported")

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
        if self.passing is not None:
            result["passing"] = self.passing
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
    post_arguments: tuple[Expr, ...] = ()
    frame_effects: tuple[CallFrameEffect, ...] = ()
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
        if self.post_arguments:
            result["post_arguments"] = [arg.to_dict() for arg in self.post_arguments]
        if self.frame_effects:
            result["frame_effects"] = [effect.to_dict() for effect in self.frame_effects]
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
    references: tuple[ReferenceBinding, ...] = ()
    frame: FrameContract | None = None
    has_body: bool = True
    link_name: str | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.link_name or self.name, len(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "body": [node.to_dict() for node in self.body],
            "contracts": [contract.to_dict() for contract in self.contracts],
            "frame": self.frame.to_dict() if self.frame is not None else None,
            "has_body": self.has_body,
            "id": self.id,
            "locals": [symbol.to_dict() for symbol in self.locals],
            "location": self.location.to_dict(),
            "name": self.name,
            "parameters": [symbol.to_dict() for symbol in self.parameters],
            "references": [binding.to_dict() for binding in self.references],
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
    records: tuple[RecordType, ...] = ()
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "functions": [function.to_dict() for function in self.functions],
            "records": [record.to_dict() for record in self.records],
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
    counterexample: Mapping[str, int | bool | tuple[int, ...] | RecordValue] | None = None
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
                key: serialize_evidence_value(self.counterexample[key])
                for key in sorted(self.counterexample)
            }
        if self.trace:
            result["trace"] = [step.to_dict() for step in self.trace]
        return result



def serialize_evidence_value(
    value: int | bool | tuple[int, ...] | RecordValue,
) -> str | bool | list[str] | dict[str, Any]:
    if type(value) is bool:
        return value
    if type(value) is int:
        return canonical_decimal(value)
    if isinstance(value, tuple) and all(type(item) is int for item in value):
        return [canonical_decimal(item) for item in value]
    if isinstance(value, RecordValue):
        profile = record_type(value.type)
        return {
            field.name: serialize_evidence_value(field_value)
            for field, field_value in zip(profile.fields, value.fields)
        }
    raise TypeError("counterexample evidence has an unsupported value")


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
