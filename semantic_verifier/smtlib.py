"""Deterministic SMT-LIB2 emission for supported verification obligations.

The emitter is deliberately limited to quantifier-free linear integer
arithmetic and booleans.  Unsupported or malformed expressions fail closed
before any solver process is started.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .model import Expr, Obligation


class SmtLibEmissionError(ValueError):
    """Raised when an obligation cannot be represented faithfully in QF_LIA."""


_SSA_SUFFIX = re.compile(r"#([0-9]+)$")
_ESCAPE = re.compile(r"_u([0-9A-F]{6})x")
_VERSION_SUFFIX = re.compile(r"_v([0-9]+)$")
_RESERVED_SYMBOLS = frozenset(
    {
        "!",
        "_",
        "abs",
        "and",
        "as",
        "assert",
        "Bool",
        "check-sat",
        "declare-fun",
        "declare-sort",
        "define-fun",
        "define-sort",
        "distinct",
        "div",
        "exists",
        "false",
        "forall",
        "get-model",
        "Int",
        "is_int",
        "ite",
        "let",
        "match",
        "mod",
        "not",
        "or",
        "par",
        "set-info",
        "set-logic",
        "set-option",
        "to_int",
        "to_real",
        "true",
        "xor",
    }
)


def encode_symbol(name: str) -> str:
    """Encode an IR name as an injective SMT-LIB simple symbol.

    SSA suffixes retain the documented readable form (``y#0`` becomes
    ``y_v0``).  Underscores and all non-ASCII identifier characters are
    escaped, reserving ``_v``, ``_n`` and ``_r`` for unambiguous decoding.
    """

    if not isinstance(name, str) or not name:
        raise SmtLibEmissionError("variable names must be non-empty strings")

    match = _SSA_SUFFIX.search(name)
    if match is None:
        base = name
        suffix = ""
    else:
        base = name[: match.start()]
        suffix = f"_v{match.group(1)}"

    encoded_base = "".join(
        character
        if character.isascii() and character.isalnum()
        else f"_u{ord(character):06X}x"
        for character in base
    )
    encoded = encoded_base + suffix
    if not encoded:
        raise SmtLibEmissionError(f"variable name {name!r} has no encodable base")
    if encoded[0].isdigit():
        encoded = "_n" + encoded
    if encoded in _RESERVED_SYMBOLS:
        encoded = "_r" + encoded
    return encoded


def decode_symbol(name: str) -> str:
    """Reverse :func:`encode_symbol` for model projection."""

    if not isinstance(name, str) or not name:
        raise SmtLibEmissionError("SMT symbols must be non-empty strings")
    encoded_name = name
    if name.startswith("_r") and name[2:] in _RESERVED_SYMBOLS:
        name = name[2:]
    if name.startswith("_n") and len(name) > 2 and name[2].isdigit():
        name = name[2:]

    match = _VERSION_SUFFIX.search(name)
    if match is None:
        base = name
        suffix = ""
    else:
        base = name[: match.start()]
        suffix = f"#{match.group(1)}"

    def decode_escape(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    decoded = _ESCAPE.sub(decode_escape, base) + suffix
    if encode_symbol(decoded) != encoded_name:
        # The public decoder accepts only names produced by this codec.  This
        # protects model parsing from silently inventing source identities.
        raise SmtLibEmissionError(f"invalid encoded SMT symbol {encoded_name!r}")
    return decoded


def emit_smtlib(obligation: Obligation) -> str:
    """Return a deterministic SMT-LIB2 query for *obligation*.

    A validity obligation asks whether all assumptions and the negated
    conclusion are satisfiable.  A satisfiability obligation asserts its
    assumptions directly.  Other modes have no solver-query semantics here.
    """

    if obligation.unsupported_reason is not None:
        raise SmtLibEmissionError(
            f"unsupported obligation: {obligation.unsupported_reason}"
        )
    if obligation.mode not in {"validity", "satisfiable"}:
        raise SmtLibEmissionError(
            f"obligation mode {obligation.mode!r} is not an SMT query"
        )
    if obligation.mode == "satisfiable" and obligation.conclusion is not None:
        raise SmtLibEmissionError(
            "satisfiability obligation must not have a conclusion"
        )
    if obligation.mode == "validity" and obligation.conclusion is None:
        raise SmtLibEmissionError("validity obligation is missing its conclusion")

    expressions = list(obligation.assumptions)
    if obligation.conclusion is not None:
        expressions.append(obligation.conclusion)
    variable_types = _collect_variable_types(expressions)

    for assumption in obligation.assumptions:
        if assumption.type != "bool":
            raise SmtLibEmissionError("obligation assumptions must have bool type")
        _emit_expr(assumption)
    if obligation.conclusion is not None:
        if obligation.conclusion.type != "bool":
            raise SmtLibEmissionError("obligation conclusion must have bool type")
        _emit_expr(obligation.conclusion)

    declarations = sorted(
        (encode_symbol(source_name), type_name, source_name)
        for source_name, type_name in variable_types.items()
    )
    encoded_names = [encoded for encoded, _, _ in declarations]
    if len(set(encoded_names)) != len(encoded_names):
        raise SmtLibEmissionError("variable names collide after SMT encoding")

    lines = ["(set-logic QF_LIA)"]
    for encoded, type_name, _ in declarations:
        lines.append(f"(declare-fun {encoded} () {_emit_sort(type_name)})")

    if obligation.assumptions:
        lines.extend(
            f"(assert {_emit_expr(assumption)})"
            for assumption in obligation.assumptions
        )
    elif obligation.mode == "satisfiable":
        lines.append("(assert true)")

    if obligation.mode == "validity":
        assert obligation.conclusion is not None
        lines.append(f"(assert (not {_emit_expr(obligation.conclusion)}))")
    lines.append("(check-sat)")
    return "\n".join(lines) + "\n"


def _collect_variable_types(expressions: Iterable[Expr]) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(expression: Expr) -> None:
        if expression.kind == "variable":
            name = str(expression.value)
            previous = result.get(name)
            if previous is not None and previous != expression.type:
                raise SmtLibEmissionError(
                    f"variable {name!r} has conflicting types {previous!r} "
                    f"and {expression.type!r}"
                )
            result[name] = expression.type
        for argument in expression.args:
            visit(argument)

    for expression in expressions:
        visit(expression)
    return result


def _emit_sort(type_name: str) -> str:
    if type_name == "i32":
        return "Int"
    if type_name == "bool":
        return "Bool"
    raise SmtLibEmissionError(f"unsupported expression type {type_name!r}")


def _emit_expr(expression: Expr) -> str:
    if expression.kind == "constant":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed constant expression")
        if expression.type == "bool" and isinstance(expression.value, bool):
            return "true" if expression.value else "false"
        if expression.type == "i32" and type(expression.value) is int:
            return _emit_integer(int(expression.value))
        raise SmtLibEmissionError("constant value does not match its declared type")

    if expression.kind == "variable":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed variable expression")
        _emit_sort(expression.type)
        if not isinstance(expression.value, str):
            raise SmtLibEmissionError("variable value must be a string name")
        return encode_symbol(expression.value)

    if expression.kind == "unary":
        if len(expression.args) != 1:
            raise SmtLibEmissionError("unary expressions must have one operand")
        operand = expression.args[0]
        if expression.op == "!":
            _require_types(expression, "bool", (operand, "bool"))
            return f"(not {_emit_expr(operand)})"
        if expression.op == "-":
            _require_types(expression, "i32", (operand, "i32"))
            return f"(- {_emit_expr(operand)})"
        raise SmtLibEmissionError(f"unsupported unary operator {expression.op!r}")

    if expression.kind != "binary" or len(expression.args) != 2:
        raise SmtLibEmissionError(f"unsupported expression kind {expression.kind!r}")

    left, right = expression.args
    op = expression.op
    if op in {"&&", "||"}:
        _require_types(expression, "bool", (left, "bool"), (right, "bool"))
        smt_op = "and" if op == "&&" else "or"
    elif op in {"==", "!="}:
        if left.type not in {"i32", "bool"} or left.type != right.type:
            raise SmtLibEmissionError(
                f"operator {op!r} requires same-typed int or bool operands"
            )
        _require_types(expression, "bool")
        smt_op = "=" if op == "==" else "distinct"
    elif op in {"<", "<=", ">", ">="}:
        _require_types(expression, "bool", (left, "i32"), (right, "i32"))
        smt_op = op
    elif op in {"+", "-"}:
        _require_types(expression, "i32", (left, "i32"), (right, "i32"))
        smt_op = op
    elif op == "*":
        _require_types(expression, "i32", (left, "i32"), (right, "i32"))
        if not (_is_integer_literal(left) or _is_integer_literal(right)):
            raise SmtLibEmissionError(
                "variable-by-variable multiplication is outside QF_LIA"
            )
        smt_op = "*"
    else:
        raise SmtLibEmissionError(f"unsupported binary operator {op!r}")
    return f"({smt_op} {_emit_expr(left)} {_emit_expr(right)})"


def _require_types(
    expression: Expr,
    result_type: str,
    *operands: tuple[Expr, str],
) -> None:
    if expression.type != result_type:
        raise SmtLibEmissionError(
            f"operator {expression.op!r} result must have type {result_type!r}"
        )
    for operand, expected in operands:
        if operand.type != expected:
            raise SmtLibEmissionError(
                f"operator {expression.op!r} operand must have type {expected!r}"
            )


def _is_integer_literal(expression: Expr) -> bool:
    if expression.kind == "constant":
        return expression.type == "i32" and type(expression.value) is int
    return (
        expression.kind == "unary"
        and expression.op == "-"
        and expression.type == "i32"
        and len(expression.args) == 1
        and _is_integer_literal(expression.args[0])
    )


def _emit_integer(value: int) -> str:
    return str(value) if value >= 0 else f"(- {abs(value)})"
