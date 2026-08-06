"""Deterministic homogeneous QF_LIA/QF_BV/QF_ARRAY emission.

Unsupported or malformed expressions fail closed before any solver process is
started.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .array_types import array_type, is_array_type
from .integer_types import integer_type, is_fixed_integer_type
from .model import Expr, Obligation
from .query_fragment import QueryFragment, classify_expressions


class SmtLibEmissionError(ValueError):
    """Raised when an obligation cannot be represented faithfully."""


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
    fragment = classify_expressions(expressions)
    if fragment == QueryFragment.QF_BV:
        return _emit_bv_query(obligation, expressions)
    if fragment == QueryFragment.QF_ARRAY and _array_requires_bv(expressions):
        return _emit_bv_query(obligation, expressions, logic="QF_ABV")
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

    logic = "QF_ALIA" if fragment == QueryFragment.QF_ARRAY else "QF_LIA"
    lines = [f"(set-logic {logic})"]
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


def _array_requires_bv(expressions: Iterable[Expr]) -> bool:
    pending = list(expressions)
    while pending:
        expression = pending.pop()
        type_name = expression.type
        if is_array_type(type_name):
            type_name = array_type(type_name).element_type
        if (
            is_fixed_integer_type(type_name)
            and not integer_type(type_name).signed
        ) or expression.op in {
            "~",
            "&",
            "|",
            "^",
            "<<",
            ">>",
            "signed_left_shift_defined",
        }:
            return True
        pending.extend(expression.args)
    return False


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
    if type_name in {"i32", "i64"}:
        return "Int"
    if type_name == "bool":
        return "Bool"
    if is_array_type(type_name):
        profile = array_type(type_name)
        if profile.element_type not in {"i32", "i64"}:
            raise SmtLibEmissionError(
                "QF_ALIA requires signed array elements"
            )
        return "(Array Int Int)"
    raise SmtLibEmissionError(f"unsupported expression type {type_name!r}")


def _emit_expr(expression: Expr) -> str:
    if expression.kind == "constant":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed constant expression")
        if expression.type == "bool" and isinstance(expression.value, bool):
            return "true" if expression.value else "false"
        if expression.type in {"i32", "i64"} and type(expression.value) is int:
            return _emit_integer(int(expression.value))
        raise SmtLibEmissionError("constant value does not match its declared type")

    if expression.kind == "variable":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed variable expression")
        _emit_sort(expression.type)
        if not isinstance(expression.value, str):
            raise SmtLibEmissionError("variable value must be a string name")
        return encode_symbol(expression.value)

    if expression.kind == "array":
        profile = array_type(expression.type)
        if (
            len(expression.args) != profile.length
            or any(item.type != profile.element_type for item in expression.args)
        ):
            raise SmtLibEmissionError("malformed array initializer expression")
        sort = _emit_sort(expression.type)
        result = f"((as const {sort}) 0)"
        for index, item in enumerate(expression.args):
            result = f"(store {result} {index} {_emit_expr(item)})"
        return result

    if expression.kind == "select":
        if len(expression.args) != 2:
            raise SmtLibEmissionError("malformed array select expression")
        array, index = expression.args
        profile = array_type(array.type)
        if expression.type != profile.element_type or index.type not in {"i32", "i64"}:
            raise SmtLibEmissionError("array select types are inconsistent")
        return f"(select {_emit_expr(array)} {_emit_expr(index)})"

    if expression.kind == "store":
        if len(expression.args) != 3:
            raise SmtLibEmissionError("malformed array store expression")
        array, index, value = expression.args
        profile = array_type(array.type)
        if (
            expression.type != array.type
            or index.type not in {"i32", "i64"}
            or value.type != profile.element_type
        ):
            raise SmtLibEmissionError("array store types are inconsistent")
        return (
            f"(store {_emit_expr(array)} {_emit_expr(index)} "
            f"{_emit_expr(value)})"
        )

    if expression.kind == "cast":
        if expression.op != "integral" or len(expression.args) != 1:
            raise SmtLibEmissionError("malformed integral cast expression")
        operand = expression.args[0]
        emitted = _emit_expr(operand)
        if operand.type == "bool" and expression.type == "i32":
            return f"(ite {emitted} 1 0)"
        if operand.type == "i32" and expression.type == "i64":
            return emitted
        if operand.type == "i64" and expression.type == "i32":
            offset = 2**31
            modulus = 2**32
            return f"(- (mod (+ {emitted} {offset}) {modulus}) {offset})"
        raise SmtLibEmissionError(
            f"unsupported integral cast {operand.type!r} to {expression.type!r}"
        )

    if expression.kind == "predicate":
        operation = _signed_no_overflow_operation(expression)
        profile = integer_type(operation.type)
        emitted = _emit_expr(operation)
        return (
            f"(and (>= {emitted} {_emit_integer(profile.minimum)}) "
            f"(<= {emitted} {_emit_integer(profile.maximum)}))"
        )

    if expression.kind == "unary":
        if len(expression.args) != 1:
            raise SmtLibEmissionError("unary expressions must have one operand")
        operand = expression.args[0]
        if expression.op == "!":
            _require_types(expression, "bool", (operand, "bool"))
            return f"(not {_emit_expr(operand)})"
        if expression.op == "-" and expression.type in {"i32", "i64"}:
            _require_types(expression, expression.type, (operand, expression.type))
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
        if (
            (
                left.type not in {"i32", "i64", "bool"}
                and not is_array_type(left.type)
            )
            or left.type != right.type
        ):
            raise SmtLibEmissionError(
                f"operator {op!r} requires same-typed signed integer or bool operands"
            )
        _require_types(expression, "bool")
        smt_op = "=" if op == "==" else "distinct"
    elif op in {"<", "<=", ">", ">="}:
        if left.type not in {"i32", "i64"} or left.type != right.type:
            raise SmtLibEmissionError(
                f"operator {op!r} requires matching signed integer operands"
            )
        _require_types(expression, "bool")
        smt_op = op
    elif op in {"+", "-", "*", "/", "%"}:
        if expression.type not in {"i32", "i64"}:
            raise SmtLibEmissionError(
                f"operator {op!r} requires a signed integer result"
            )
        _require_types(
            expression,
            expression.type,
            (left, expression.type),
            (right, expression.type),
        )
        if op == "*" and not (
            _is_integer_literal(left) or _is_integer_literal(right)
        ):
            raise SmtLibEmissionError(
                "variable-by-variable multiplication is outside QF_LIA"
            )
        if op in {"/", "%"}:
            if not _is_integer_literal(right):
                raise SmtLibEmissionError(
                    f"operator {op!r} requires a literal divisor in QF_LIA"
                )
            numerator = _emit_expr(left)
            denominator = _integer_literal_value(right)
            if denominator == 0:
                raise SmtLibEmissionError("literal divisor must be non-zero")
            return (
                _emit_cxx_div_by_literal(numerator, denominator)
                if op == "/"
                else _emit_cxx_remainder_by_literal(numerator, denominator)
            )
        smt_op = op
    else:
        raise SmtLibEmissionError(f"unsupported binary operator {op!r}")
    return f"({smt_op} {_emit_expr(left)} {_emit_expr(right)})"


def _emit_cxx_div_by_literal(numerator: str, denominator: int) -> str:
    absolute_numerator = f"(ite (< {numerator} 0) (- {numerator}) {numerator})"
    magnitude = f"(div {absolute_numerator} {abs(denominator)})"
    negative = f"(< {numerator} 0)"
    return (
        f"(ite {negative} (- {magnitude}) {magnitude})"
        if denominator > 0
        else f"(ite {negative} {magnitude} (- {magnitude}))"
    )


def _emit_cxx_remainder_by_literal(numerator: str, denominator: int) -> str:
    absolute_numerator = f"(ite (< {numerator} 0) (- {numerator}) {numerator})"
    magnitude = f"(mod {absolute_numerator} {abs(denominator)})"
    return f"(ite (< {numerator} 0) (- {magnitude}) {magnitude})"


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
        return expression.type in {"i32", "i64"} and type(expression.value) is int
    return (
        expression.kind == "unary"
        and expression.op == "-"
        and expression.type in {"i32", "i64"}
        and len(expression.args) == 1
        and _is_integer_literal(expression.args[0])
    )


def _integer_literal_value(expression: Expr) -> int:
    if expression.kind == "constant":
        return int(expression.value)
    if expression.kind == "unary" and expression.op == "-":
        return -_integer_literal_value(expression.args[0])
    raise SmtLibEmissionError("expression is not an integer literal")


def _emit_integer(value: int) -> str:
    return str(value) if value >= 0 else f"(- {abs(value)})"

def _emit_bv_query(
    obligation: Obligation,
    expressions: list[Expr],
    *,
    logic: str = "QF_BV",
) -> str:
    variable_types = _collect_variable_types(expressions)
    for assumption in obligation.assumptions:
        if assumption.type != "bool":
            raise SmtLibEmissionError("obligation assumptions must have bool type")
        _emit_bv_expr(assumption)
    if obligation.conclusion is not None:
        if obligation.conclusion.type != "bool":
            raise SmtLibEmissionError("obligation conclusion must have bool type")
        _emit_bv_expr(obligation.conclusion)

    declarations = sorted(
        (encode_symbol(source_name), type_name, source_name)
        for source_name, type_name in variable_types.items()
    )
    encoded_names = [encoded for encoded, _, _ in declarations]
    if len(set(encoded_names)) != len(encoded_names):
        raise SmtLibEmissionError("variable names collide after SMT encoding")

    lines = [f"(set-logic {logic})"]
    for encoded, type_name, _ in declarations:
        lines.append(f"(declare-fun {encoded} () {_emit_bv_sort(type_name)})")
    if obligation.assumptions:
        lines.extend(
            f"(assert {_emit_bv_expr(assumption)})"
            for assumption in obligation.assumptions
        )
    elif obligation.mode == "satisfiable":
        lines.append("(assert true)")
    if obligation.mode == "validity":
        assert obligation.conclusion is not None
        lines.append(f"(assert (not {_emit_bv_expr(obligation.conclusion)}))")
    lines.append("(check-sat)")
    return "\n".join(lines) + "\n"


def _emit_bv_sort(type_name: str) -> str:
    if type_name == "bool":
        return "Bool"
    if is_fixed_integer_type(type_name):
        return f"(_ BitVec {integer_type(type_name).width})"
    if is_array_type(type_name):
        profile = array_type(type_name)
        element_sort = _emit_bv_sort(profile.element_type)
        return f"(Array (_ BitVec 64) {element_sort})"
    raise SmtLibEmissionError(f"unsupported expression type {type_name!r}")


def _emit_bv_expr(expression: Expr) -> str:
    if expression.kind == "constant":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed constant expression")
        if expression.type == "bool" and isinstance(expression.value, bool):
            return "true" if expression.value else "false"
        if is_fixed_integer_type(expression.type) and type(expression.value) is int:
            profile = integer_type(expression.type)
            if not profile.contains(expression.value):
                raise SmtLibEmissionError("integer constant is outside its declared type")
            encoded = int(expression.value) % (2**profile.width)
            return f"(_ bv{encoded} {profile.width})"
        raise SmtLibEmissionError("constant value does not match its declared type")

    if expression.kind == "variable":
        if expression.args or expression.op is not None:
            raise SmtLibEmissionError("malformed variable expression")
        if not isinstance(expression.value, str):
            raise SmtLibEmissionError("variable value must be a string name")
        _emit_bv_sort(expression.type)
        return encode_symbol(expression.value)

    if expression.kind == "array":
        profile = array_type(expression.type)
        if (
            len(expression.args) != profile.length
            or any(item.type != profile.element_type for item in expression.args)
        ):
            raise SmtLibEmissionError("malformed array initializer expression")
        sort = _emit_bv_sort(expression.type)
        width = integer_type(profile.element_type).width
        result = f"((as const {sort}) (_ bv0 {width}))"
        for index, item in enumerate(expression.args):
            result = (
                f"(store {result} (_ bv{index} 64) "
                f"{_emit_bv_expr(item)})"
            )
        return result

    if expression.kind == "select":
        if len(expression.args) != 2:
            raise SmtLibEmissionError("malformed array select expression")
        array, index = expression.args
        profile = array_type(array.type)
        if (
            expression.type != profile.element_type
            or not is_fixed_integer_type(index.type)
        ):
            raise SmtLibEmissionError("array select types are inconsistent")
        return (
            f"(select {_emit_bv_expr(array)} "
            f"{_emit_bv_array_index(index)})"
        )

    if expression.kind == "store":
        if len(expression.args) != 3:
            raise SmtLibEmissionError("malformed array store expression")
        array, index, value = expression.args
        profile = array_type(array.type)
        if (
            expression.type != array.type
            or not is_fixed_integer_type(index.type)
            or value.type != profile.element_type
        ):
            raise SmtLibEmissionError("array store types are inconsistent")
        return (
            f"(store {_emit_bv_expr(array)} "
            f"{_emit_bv_array_index(index)} {_emit_bv_expr(value)})"
        )
    if expression.kind == "cast":
        if expression.op != "integral" or len(expression.args) != 1:
            raise SmtLibEmissionError("malformed integral cast expression")
        operand = expression.args[0]
        if operand.type == "bool" and is_fixed_integer_type(expression.type):
            width = integer_type(expression.type).width
            emitted = _emit_bv_expr(operand)
            return f"(ite {emitted} (_ bv1 {width}) (_ bv0 {width}))"
        if not (
            is_fixed_integer_type(operand.type)
            and is_fixed_integer_type(expression.type)
        ):
            raise SmtLibEmissionError(
                f"unsupported integral cast {operand.type!r} to {expression.type!r}"
            )
        source = integer_type(operand.type)
        target = integer_type(expression.type)
        emitted = _emit_bv_expr(operand)
        if source.width == target.width:
            return emitted
        if source.width < target.width:
            extension = "sign_extend" if source.signed else "zero_extend"
            return f"((_ {extension} {target.width - source.width}) {emitted})"
        return f"((_ extract {target.width - 1} 0) {emitted})"

    if expression.kind == "predicate":
        if expression.op == "signed_no_overflow":
            operation = _signed_no_overflow_operation(expression)
            profile = integer_type(operation.type)
            left, right = operation.args
            extended_left = (
                f"((_ sign_extend {profile.width}) {_emit_bv_expr(left)})"
            )
            extended_right = (
                f"((_ sign_extend {profile.width}) {_emit_bv_expr(right)})"
            )
            wide_op = {"+": "bvadd", "-": "bvsub", "*": "bvmul"}[
                operation.op
            ]
            wide_result = f"({wide_op} {extended_left} {extended_right})"
            wrapped = _emit_bv_expr(operation)
            extended_wrapped = (
                f"((_ sign_extend {profile.width}) {wrapped})"
            )
            return f"(= {wide_result} {extended_wrapped})"
        if expression.op == "signed_left_shift_defined":
            operation = _signed_left_shift_operation(expression)
            profile = integer_type(operation.type)
            left, right = operation.args
            extended_left = (
                f"((_ zero_extend {profile.width}) {_emit_bv_expr(left)})"
            )
            extended_right = _emit_bv_shift_count(right, profile.width * 2)
            wide_result = f"(bvshl {extended_left} {extended_right})"
            wrapped = _emit_bv_expr(operation)
            extended_wrapped = (
                f"((_ zero_extend {profile.width}) {wrapped})"
            )
            count_defined = _emit_bv_shift_count_defined(right, profile.width)
            nonnegative = (
                f"(bvsge {_emit_bv_expr(left)} (_ bv0 {profile.width}))"
            )
            return (
                f"(and {count_defined} {nonnegative} "
                f"(= {wide_result} {extended_wrapped}))"
            )
        raise SmtLibEmissionError(
            f"unsupported predicate {expression.op!r}"
        )

    if expression.kind == "unary":
        if len(expression.args) != 1:
            raise SmtLibEmissionError("unary expressions must have one operand")
        operand = expression.args[0]
        if expression.op == "!":
            _require_types(expression, "bool", (operand, "bool"))
            return f"(not {_emit_bv_expr(operand)})"
        if expression.op == "-" and is_fixed_integer_type(expression.type):
            _require_types(expression, expression.type, (operand, expression.type))
            return f"(bvneg {_emit_bv_expr(operand)})"
        if expression.op == "~" and is_fixed_integer_type(expression.type):
            _require_types(expression, expression.type, (operand, expression.type))
            return f"(bvnot {_emit_bv_expr(operand)})"
        raise SmtLibEmissionError(f"unsupported unary operator {expression.op!r}")

    if expression.kind != "binary" or len(expression.args) != 2:
        raise SmtLibEmissionError(
            f"unsupported expression kind {expression.kind!r}"
        )
    left, right = expression.args
    op = expression.op
    if op in {"&&", "||"}:
        _require_types(expression, "bool", (left, "bool"), (right, "bool"))
        smt_op = "and" if op == "&&" else "or"
    elif op in {"==", "!="}:
        if left.type != right.type or not (
            left.type == "bool"
            or is_fixed_integer_type(left.type)
            or is_array_type(left.type)
        ):
            raise SmtLibEmissionError(
                f"operator {op!r} requires matching fixed-width or bool operands"
            )
        _require_types(expression, "bool")
        smt_op = "=" if op == "==" else "distinct"
    elif op in {"<", "<=", ">", ">="}:
        if left.type != right.type or not is_fixed_integer_type(left.type):
            raise SmtLibEmissionError(
                f"operator {op!r} requires matching fixed-width operands"
            )
        _require_types(expression, "bool")
        signed = integer_type(left.type).signed
        smt_op = {
            "<": "bvslt" if signed else "bvult",
            "<=": "bvsle" if signed else "bvule",
            ">": "bvsgt" if signed else "bvugt",
            ">=": "bvsge" if signed else "bvuge",
        }[op]
    elif op in {"+", "-", "*", "/", "%", "&", "|", "^"}:
        if not is_fixed_integer_type(expression.type):
            raise SmtLibEmissionError(
                f"operator {op!r} requires a fixed-width result"
            )
        _require_types(
            expression,
            expression.type,
            (left, expression.type),
            (right, expression.type),
        )
        if op in {"/", "%"} and _is_fixed_literal(right):
            if _fixed_literal_value(right) == 0:
                raise SmtLibEmissionError("literal divisor must be non-zero")
        signed = integer_type(expression.type).signed
        smt_op = {
            "+": "bvadd",
            "-": "bvsub",
            "*": "bvmul",
            "/": "bvsdiv" if signed else "bvudiv",
            "%": "bvsrem" if signed else "bvurem",
            "&": "bvand",
            "|": "bvor",
            "^": "bvxor",
        }[op]
    elif op in {"<<", ">>"}:
        if (
            not is_fixed_integer_type(expression.type)
            or left.type != expression.type
            or not is_fixed_integer_type(right.type)
        ):
            raise SmtLibEmissionError(
                f"operator {op!r} requires promoted fixed-width operands"
            )
        emitted_left = _emit_bv_expr(left)
        emitted_right = _emit_bv_shift_count(
            right, integer_type(expression.type).width
        )
        if op == "<<":
            return f"(bvshl {emitted_left} {emitted_right})"
        smt_op = (
            "bvashr" if integer_type(expression.type).signed else "bvlshr"
        )
        return f"({smt_op} {emitted_left} {emitted_right})"
    else:
        raise SmtLibEmissionError(f"unsupported binary operator {op!r}")
    return f"({smt_op} {_emit_bv_expr(left)} {_emit_bv_expr(right)})"


def _is_fixed_literal(expression: Expr) -> bool:
    if expression.kind == "constant":
        return is_fixed_integer_type(expression.type) and type(expression.value) is int
    return (
        expression.kind == "unary"
        and expression.op == "-"
        and is_fixed_integer_type(expression.type)
        and len(expression.args) == 1
        and _is_fixed_literal(expression.args[0])
    )


def _fixed_literal_value(expression: Expr) -> int:
    if expression.kind == "constant":
        return int(expression.value)
    if expression.kind == "unary" and expression.op == "-":
        return -_fixed_literal_value(expression.args[0])
    raise SmtLibEmissionError("expression is not a fixed-width literal")


def _emit_bv_array_index(expression: Expr) -> str:
    if not is_fixed_integer_type(expression.type):
        raise SmtLibEmissionError("array index must be fixed-width")
    profile = integer_type(expression.type)
    emitted = _emit_bv_expr(expression)
    if profile.width == 64:
        return emitted
    extension = "sign_extend" if profile.signed else "zero_extend"
    return f"((_ {extension} {64 - profile.width}) {emitted})"


def _emit_bv_shift_count(expression: Expr, target_width: int) -> str:
    if not is_fixed_integer_type(expression.type):
        raise SmtLibEmissionError("shift count must be fixed-width")
    source = integer_type(expression.type)
    emitted = _emit_bv_expr(expression)
    if source.width == target_width:
        return emitted
    if source.width < target_width:
        extension = "sign_extend" if source.signed else "zero_extend"
        return f"((_ {extension} {target_width - source.width}) {emitted})"
    return f"((_ extract {target_width - 1} 0) {emitted})"


def _emit_bv_shift_count_defined(expression: Expr, left_width: int) -> str:
    profile = integer_type(expression.type)
    emitted = _emit_bv_expr(expression)
    lower = (
        f"(bvsge {emitted} (_ bv0 {profile.width}))"
        if profile.signed
        else "true"
    )
    upper_op = "bvslt" if profile.signed else "bvult"
    upper = f"({upper_op} {emitted} (_ bv{left_width} {profile.width}))"
    return f"(and {lower} {upper})"


def _signed_no_overflow_operation(expression: Expr) -> Expr:
    if (
        expression.type != "bool"
        or expression.op != "signed_no_overflow"
        or len(expression.args) != 1
    ):
        raise SmtLibEmissionError("malformed signed-overflow predicate")
    operation = expression.args[0]
    if (
        operation.kind != "binary"
        or operation.op not in {"+", "-", "*"}
        or operation.type not in {"i32", "i64"}
        or len(operation.args) != 2
        or any(argument.type != operation.type for argument in operation.args)
    ):
        raise SmtLibEmissionError(
            "signed-overflow predicate requires a matching signed operation"
        )
    return operation


def _signed_left_shift_operation(expression: Expr) -> Expr:
    if (
        expression.type != "bool"
        or expression.op != "signed_left_shift_defined"
        or len(expression.args) != 1
    ):
        raise SmtLibEmissionError("malformed signed-left-shift predicate")
    operation = expression.args[0]
    if (
        operation.kind != "binary"
        or operation.op != "<<"
        or operation.type not in {"i32", "i64"}
        or len(operation.args) != 2
        or operation.args[0].type != operation.type
        or not is_fixed_integer_type(operation.args[1].type)
    ):
        raise SmtLibEmissionError(
            "signed-left-shift predicate requires promoted fixed-width operands"
        )
    return operation
