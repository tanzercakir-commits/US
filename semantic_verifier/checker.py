"""Small deterministic checker for boolean logic and affine signed-integer formulas.

Validity proofs come only from exact simplification and matching affine facts.
A finite deterministic search finds real counterexamples and satisfiability
witnesses; exhausting that search never becomes a proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from itertools import product
from math import gcd
from typing import Iterable, Mapping

from .array_types import array_type
from .backend import CheckerBackend
from .counterexample import minimize_counterexample
from .integer_types import (
    I32,
    I64,
    convert_integer,
    integer_type,
    is_fixed_integer_type,
    is_signed_integer_type,
    is_unsigned_integer_type,
)
from .model import (
    Expr,
    Obligation,
    TraceStep,
    TraceTemplate,
    VerificationResult,
    VerificationStatus,
)


@dataclass(frozen=True, slots=True)
class LinearForm:
    coefficients: tuple[tuple[str, int], ...]
    constant: int = 0

    @staticmethod
    def from_parts(coefficients: Mapping[str, int], constant: int = 0) -> "LinearForm":
        return LinearForm(
            tuple(sorted((name, value) for name, value in coefficients.items() if value)),
            constant,
        )

    def scale(self, factor: int) -> "LinearForm":
        return LinearForm(
            tuple((name, value * factor) for name, value in self.coefficients),
            self.constant * factor,
        )

    def add(self, other: "LinearForm") -> "LinearForm":
        coefficients = dict(self.coefficients)
        for name, value in other.coefficients:
            coefficients[name] = coefficients.get(name, 0) + value
        return LinearForm.from_parts(coefficients, self.constant + other.constant)


def linearize(expr: Expr) -> LinearForm | None:
    if expr.kind == "constant" and is_signed_integer_type(expr.type):
        return LinearForm((), int(expr.value))
    if expr.kind == "variable" and is_signed_integer_type(expr.type):
        return LinearForm(((str(expr.value), 1),), 0)
    if expr.kind == "cast" and len(expr.args) == 1:
        operand = expr.args[0]
        if operand.type == "i32" and expr.type == "i64":
            return linearize(operand)
        return None
    if expr.kind == "unary" and expr.op == "-" and is_signed_integer_type(expr.type):
        inner = linearize(expr.args[0])
        return inner.scale(-1) if inner is not None else None
    if expr.kind != "binary" or not is_signed_integer_type(expr.type):
        return None
    if any(argument.type != expr.type for argument in expr.args):
        return None
    left = linearize(expr.args[0])
    right = linearize(expr.args[1])
    if expr.op == "+" and left is not None and right is not None:
        return left.add(right)
    if expr.op == "-" and left is not None and right is not None:
        return left.add(right.scale(-1))
    if expr.op == "*":
        if left is not None and not left.coefficients and right is not None:
            return right.scale(left.constant)
        if right is not None and not right.coefficients and left is not None:
            return left.scale(right.constant)
    return None


def simplify(expr: Expr) -> Expr:
    if not expr.args:
        return expr
    args = tuple(simplify(argument) for argument in expr.args)
    if expr.kind == "cast":
        value = args[0]
        if value.kind == "constant":
            converted = (
                int(bool(value.value))
                if value.type == "bool"
                else convert_integer(int(value.value), expr.type)
            )
            return Expr.integer(converted, expr.type)
        return Expr(expr.kind, expr.type, expr.value, expr.op, args)

    if expr.kind == "array":
        return Expr.array(args, array_type(expr.type).element_type)

    if expr.kind == "select":
        array, index = args
        if index.kind == "constant":
            offset = int(index.value)
            if array.kind == "array" and 0 <= offset < len(array.args):
                return array.args[offset]
            if array.kind == "store":
                stored_index = array.args[1]
                if stored_index.kind == "constant":
                    if int(stored_index.value) == offset:
                        return array.args[2]
                    return simplify(Expr.select(array.args[0], index))
        if array.kind == "store" and array.args[1] == index:
            return array.args[2]
        return Expr.select(array, index)

    if expr.kind == "store":
        array, index, value = args
        if index.kind == "constant" and array.kind == "array":
            offset = int(index.value)
            if 0 <= offset < len(array.args):
                elements = list(array.args)
                elements[offset] = value
                return Expr.array(elements, array_type(array.type).element_type)
        return Expr.store(array, index, value)

    if expr.kind == "predicate":
        return Expr(expr.kind, expr.type, expr.value, expr.op, args)

    if expr.kind == "unary":
        value = args[0]
        if expr.op == "!" and value.kind == "constant":
            return Expr.boolean(not bool(value.value))
        if expr.op == "!" and value.kind == "unary" and value.op == "!":
            return value.args[0]
        if expr.op == "!" and value.kind == "binary":
            inverse = {
                "==": "!=",
                "!=": "==",
                "<": ">=",
                "<=": ">",
                ">": "<=",
                ">=": "<",
            }.get(value.op or "")
            if inverse:
                return Expr.binary(inverse, value.args[0], value.args[1], "bool")
        if expr.op == "-" and value.kind == "constant":
            return _integer_constant(-int(value.value), expr.type)
        if expr.op == "~" and value.kind == "constant":
            return Expr.integer(
                convert_integer(~int(value.value), expr.type), expr.type
            )
        return Expr(expr.kind, expr.type, expr.value, expr.op, args)

    left, right = args
    if expr.op == "&&":
        if left == Expr.boolean(False) or right == Expr.boolean(False):
            return Expr.boolean(False)
        if left == Expr.boolean(True):
            return right
        if right == Expr.boolean(True):
            return left
        if left == right:
            return left
    if expr.op == "||":
        if left == Expr.boolean(True) or right == Expr.boolean(True):
            return Expr.boolean(True)
        if left == Expr.boolean(False):
            return right
        if right == Expr.boolean(False):
            return left
        if left == right:
            return left
    if expr.op in {"==", "!="} and left == right:
        return Expr.boolean(expr.op == "==")
    if left.kind == "constant" and right.kind == "constant":
        try:
            return _constant_binary(expr.op or "", left, right, expr.type)
        except (ArithmeticError, TypeError, ValueError):
            pass
    if is_signed_integer_type(expr.type):
        zero = Expr.integer(0, expr.type)
        one = Expr.integer(1, expr.type)
        if expr.op in {"+", "-"} and right == zero:
            return left
        if expr.op == "*" and right == one:
            return left
        if expr.op == "*" and left == one:
            return right
        if expr.op == "*" and (left == zero or right == zero):
            return zero
    return Expr(expr.kind, expr.type, expr.value, expr.op, args)


def _integer_constant(value: int, type_name: str) -> Expr:
    if is_unsigned_integer_type(type_name):
        value = convert_integer(value, type_name)
    return Expr.integer(value, type_name)


def _constant_binary(
    op: str, left: Expr, right: Expr, type_name: str
) -> Expr:
    a, b = left.value, right.value
    if op == "+":
        return _integer_constant(int(a) + int(b), type_name)
    if op == "-":
        return _integer_constant(int(a) - int(b), type_name)
    if op == "*":
        return _integer_constant(int(a) * int(b), type_name)
    if op == "/":
        quotient = (
            int(a) // int(b)
            if is_unsigned_integer_type(type_name)
            else _cxx_div(int(a), int(b))
        )
        return _integer_constant(quotient, type_name)
    if op == "%":
        if is_unsigned_integer_type(type_name):
            return _integer_constant(int(a) % int(b), type_name)
        quotient = _cxx_div(int(a), int(b))
        return _integer_constant(int(a) - int(b) * quotient, type_name)
    if op in {"&", "|", "^"}:
        value = {
            "&": int(a) & int(b),
            "|": int(a) | int(b),
            "^": int(a) ^ int(b),
        }[op]
        return Expr.integer(convert_integer(value, type_name), type_name)
    if op in {"<<", ">>"}:
        count = int(b)
        if count < 0 or count >= integer_type(left.type).width:
            raise ValueError("shift count is outside the result width")
        value = int(a) << count if op == "<<" else int(a) >> count
        return Expr.integer(convert_integer(value, type_name), type_name)
    if op == "&&":
        return Expr.boolean(bool(a) and bool(b))
    if op == "||":
        return Expr.boolean(bool(a) or bool(b))
    comparisons = {
        "==": a == b,
        "!=": a != b,
        "<": a < b,
        "<=": a <= b,
        ">": a > b,
        ">=": a >= b,
    }
    if op in comparisons:
        return Expr.boolean(comparisons[op])
    raise ValueError(f"unknown constant operator {op} for {type_name}")


def _cxx_div(left: int, right: int) -> int:
    if right == 0:
        raise ZeroDivisionError
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


@dataclass(frozen=True, slots=True)
class Constraint:
    kind: str
    coefficients: tuple[tuple[str, int], ...] = ()
    bound: int = 0


def comparison_constraint(expr: Expr) -> Constraint | None:
    expr = simplify(expr)
    if expr.kind == "constant" and expr.type == "bool":
        return Constraint("true" if expr.value else "false")
    if expr.kind != "binary" or expr.op not in {"==", "!=", "<", "<=", ">", ">="}:
        return None
    left = linearize(expr.args[0])
    right = linearize(expr.args[1])
    if left is None or right is None:
        return None
    difference = left.add(right.scale(-1))
    coefficients = dict(difference.coefficients)
    constant = difference.constant
    if expr.op == ">=":
        return _normalize_constraint("lower", coefficients, -constant)
    if expr.op == ">":
        return _normalize_constraint("lower", coefficients, 1 - constant)
    if expr.op == "<=":
        return _normalize_constraint(
            "lower", {name: -value for name, value in coefficients.items()}, constant
        )
    if expr.op == "<":
        return _normalize_constraint(
            "lower",
            {name: -value for name, value in coefficients.items()},
            constant + 1,
        )
    kind = "equal" if expr.op == "==" else "not_equal"
    return _normalize_constraint(kind, coefficients, -constant)


def _normalize_constraint(
    kind: str, coefficients: Mapping[str, int], bound: int
) -> Constraint:
    cleaned = {name: value for name, value in coefficients.items() if value}
    if not cleaned:
        if kind == "lower":
            truth = 0 >= bound
        elif kind == "equal":
            truth = 0 == bound
        else:
            truth = 0 != bound
        return Constraint("true" if truth else "false")
    divisor = reduce(gcd, (abs(value) for value in cleaned.values()))
    if kind == "lower":
        cleaned = {name: value // divisor for name, value in cleaned.items()}
        # Keep normalization exact.  ``ceil(bound / divisor)`` first converts
        # arbitrary-size integers to float and can weaken a goal by one (or
        # more), which is enough to turn a false implication into a proof.
        bound = -(-bound // divisor)
    else:
        if bound % divisor:
            return Constraint("false" if kind == "equal" else "true")
        cleaned = {name: value // divisor for name, value in cleaned.items()}
        bound //= divisor
        first_value = next(iter(sorted(cleaned.items())))[1]
        if first_value < 0:
            cleaned = {name: -value for name, value in cleaned.items()}
            bound = -bound
    return Constraint(kind, tuple(sorted(cleaned.items())), bound)


def _integer_literal_expression(expr: Expr) -> bool:
    if expr.kind == "constant":
        return is_signed_integer_type(expr.type) and type(expr.value) is int
    return (
        expr.kind == "unary"
        and expr.op == "-"
        and len(expr.args) == 1
        and expr.args[0].type == expr.type
        and _integer_literal_expression(expr.args[0])
    )


def logic_supported(expr: Expr) -> bool:
    """Validate the original expression before any simplifying rewrite."""

    if is_signed_integer_type(expr.type):
        if expr.kind in {"constant", "variable"}:
            return True
        if expr.kind == "cast":
            if expr.op != "integral" or len(expr.args) != 1:
                return False
            operand = expr.args[0]
            return (
                (operand.type, expr.type)
                in {("bool", "i32"), ("i32", "i64"), ("i64", "i32")}
                and logic_supported(operand)
            )
        if expr.kind == "unary":
            return (
                expr.op == "-"
                and len(expr.args) == 1
                and expr.args[0].type == expr.type
                and logic_supported(expr.args[0])
            )
        if expr.kind != "binary" or expr.op not in {"+", "-", "*", "/", "%"}:
            return False
        if len(expr.args) != 2 or any(arg.type != expr.type for arg in expr.args):
            return False
        if not all(logic_supported(arg) for arg in expr.args):
            return False
        if expr.op == "*" and linearize(expr) is None:
            return False
        if expr.op in {"/", "%"} and not _integer_literal_expression(expr.args[1]):
            return False
        return True
    if expr.type != "bool":
        return False
    if expr.kind in {"constant", "variable"}:
        return True
    if expr.kind == "unary":
        return (
            expr.op == "!"
            and len(expr.args) == 1
            and expr.args[0].type == "bool"
            and logic_supported(expr.args[0])
        )
    if expr.kind != "binary" or len(expr.args) != 2:
        return False
    if expr.op in {"&&", "||"}:
        return all(
            argument.type == "bool" and logic_supported(argument)
            for argument in expr.args
        )
    if expr.op in {"<", "<=", ">", ">="}:
        return (
            is_signed_integer_type(expr.args[0].type)
            and expr.args[0].type == expr.args[1].type
            and all(logic_supported(argument) for argument in expr.args)
        )
    if expr.op in {"==", "!="}:
        if expr.args[0].type != expr.args[1].type:
            return False
        if is_signed_integer_type(expr.args[0].type):
            return all(logic_supported(argument) for argument in expr.args)
        if expr.args[0].type == "bool":
            return all(logic_supported(argument) for argument in expr.args)
        return False
    return False


def negate(expr: Expr) -> Expr:
    expr = simplify(expr)
    if expr.kind == "constant" and expr.type == "bool":
        return Expr.boolean(not bool(expr.value))
    if expr.kind == "unary" and expr.op == "!":
        return expr.args[0]
    if expr.kind == "binary":
        inverse = {
            "==": "!=",
            "!=": "==",
            "<": ">=",
            "<=": ">",
            ">": "<=",
            ">=": "<",
        }.get(expr.op or "")
        if inverse:
            return Expr.binary(inverse, expr.args[0], expr.args[1], "bool")
    return Expr.unary("!", expr, "bool")


def _substitute_fixed_point(expr: Expr, definitions: Mapping[str, Expr]) -> Expr:
    current = expr
    for _ in range(len(definitions) + 1):
        updated = current.substitute(definitions)
        if updated == current:
            break
        current = updated
    return simplify(current)


def prepare_formulas(
    assumptions: tuple[Expr, ...], conclusion: Expr
) -> tuple[tuple[Expr, ...], Expr]:
    definitions: dict[str, Expr] = {}
    for raw in assumptions:
        candidate = _substitute_fixed_point(raw, definitions)
        if candidate.kind != "binary" or candidate.op != "==":
            continue
        left, right = candidate.args
        if left.kind == "variable" and str(left.value) not in right.variables():
            definitions[str(left.value)] = right
        elif right.kind == "variable" and str(right.value) not in left.variables():
            definitions[str(right.value)] = left
    prepared_assumptions = tuple(
        _substitute_fixed_point(assumption, definitions) for assumption in assumptions
    )
    prepared_conclusion = _substitute_fixed_point(conclusion, definitions)
    return prepared_assumptions, prepared_conclusion


def assumptions_infeasible(assumptions: tuple[Expr, ...]) -> bool:
    facts = tuple(simplify(item) for item in assumptions)
    if Expr.boolean(False) in facts:
        return True
    fact_set = set(facts)
    for fact in facts:
        if negate(fact) in fact_set:
            return True
    constraints = [
        constraint
        for constraint in (comparison_constraint(fact) for fact in facts)
        if constraint is not None
    ]
    if any(item.kind == "false" for item in constraints):
        return True
    lowers: dict[tuple[tuple[str, int], ...], int] = {}
    equals: dict[tuple[tuple[str, int], ...], int] = {}
    not_equals: dict[tuple[tuple[str, int], ...], set[int]] = {}
    for constraint in constraints:
        if constraint.kind == "lower":
            lowers[constraint.coefficients] = max(
                lowers.get(constraint.coefficients, constraint.bound),
                constraint.bound,
            )
        elif constraint.kind == "equal":
            previous = equals.get(constraint.coefficients)
            if previous is not None and previous != constraint.bound:
                return True
            equals[constraint.coefficients] = constraint.bound
        elif constraint.kind == "not_equal":
            not_equals.setdefault(constraint.coefficients, set()).add(constraint.bound)
    for coefficients, lower in lowers.items():
        opposite = tuple((name, -value) for name, value in coefficients)
        if opposite in lowers and lower > -lowers[opposite]:
            return True
    for coefficients, value in equals.items():
        if value in not_equals.get(coefficients, set()):
            return True
        lower = lowers.get(coefficients)
        if lower is not None and value < lower:
            return True
        opposite = tuple((name, -coefficient) for name, coefficient in coefficients)
        opposite_lower = lowers.get(opposite)
        if opposite_lower is not None and -value < opposite_lower:
            return True
    return False


def prove(conclusion: Expr, assumptions: tuple[Expr, ...]) -> bool | None:
    assumptions = tuple(simplify(item) for item in assumptions)
    conclusion = simplify(conclusion)
    if assumptions_infeasible(assumptions):
        return True
    if conclusion.kind == "constant" and conclusion.type == "bool":
        return bool(conclusion.value)
    fact_set = set(assumptions)
    if conclusion in fact_set:
        return True
    if negate(conclusion) in fact_set:
        return False
    if conclusion.kind == "binary" and conclusion.op == "&&":
        outcomes = [prove(argument, assumptions) for argument in conclusion.args]
        if all(outcome is True for outcome in outcomes):
            return True
        if any(outcome is False for outcome in outcomes):
            return False
        return None
    if conclusion.kind == "binary" and conclusion.op == "||":
        outcomes = [prove(argument, assumptions) for argument in conclusion.args]
        if any(outcome is True for outcome in outcomes):
            return True
        if all(outcome is False for outcome in outcomes):
            return False
        return None
    if conclusion.kind == "unary" and conclusion.op == "!":
        outcome = prove(conclusion.args[0], assumptions)
        return None if outcome is None else not outcome
    constraints = tuple(
        item
        for item in (comparison_constraint(fact) for fact in assumptions)
        if item is not None
    )
    goal = comparison_constraint(conclusion)
    positive = _constraint_implied(goal, constraints)
    if positive:
        return True
    negative = comparison_constraint(negate(conclusion))
    if _constraint_implied(negative, constraints):
        return False
    return None


def prove_disjunctive_validity(
    conclusion: Expr,
    assumptions: tuple[Expr, ...],
) -> bool | None:
    """Prove a validity query by exact deterministic assumption case-splitting."""

    flattened: list[Expr] = []

    def flatten(expression: Expr) -> None:
        if expression.kind == "binary" and expression.op == "&&":
            for argument in expression.args:
                flatten(argument)
            return
        flattened.append(expression)

    for assumption in assumptions:
        flatten(assumption)
    normalized = tuple(flattened)
    for index, assumption in enumerate(normalized):
        if assumption.kind != "binary" or assumption.op != "||":
            continue
        remaining = normalized[:index] + normalized[index + 1 :]
        outcomes = tuple(
            prove_disjunctive_validity(
                conclusion,
                remaining + (alternative,),
            )
            for alternative in assumption.args
        )
        if all(outcome is True for outcome in outcomes):
            return True
        if any(outcome is False for outcome in outcomes):
            return False
        return None

    prepared_assumptions, prepared_conclusion = prepare_formulas(
        normalized,
        conclusion,
    )
    return prove(prepared_conclusion, prepared_assumptions)


def _constraint_implied(
    goal: Constraint | None, facts: tuple[Constraint, ...]
) -> bool:
    if goal is None:
        return False
    if goal.kind == "true":
        return True
    if goal.kind == "false":
        return False
    for fact in facts:
        if fact.kind == "true":
            continue
        if fact.coefficients != goal.coefficients:
            continue
        if goal.kind == "lower":
            if fact.kind == "lower" and fact.bound >= goal.bound:
                return True
            if fact.kind == "equal" and fact.bound >= goal.bound:
                return True
        elif goal.kind == "equal":
            if fact.kind == "equal" and fact.bound == goal.bound:
                return True
        elif goal.kind == "not_equal":
            if fact.kind == "not_equal" and fact.bound == goal.bound:
                return True
            if fact.kind == "equal" and fact.bound != goal.bound:
                return True
            if fact.kind == "lower" and fact.bound > goal.bound:
                return True
    if goal.kind == "not_equal":
        opposite = tuple((name, -value) for name, value in goal.coefficients)
        for fact in facts:
            if (
                fact.kind == "lower"
                and fact.coefficients == opposite
                and fact.bound > -goal.bound
            ):
                return True
    return False


def _integer_value(value: int, type_name: str) -> int:
    return (
        convert_integer(value, type_name)
        if is_unsigned_integer_type(type_name)
        else value
    )


EvidenceValue = int | bool | tuple[int, ...]


def evaluate(
    expr: Expr, environment: Mapping[str, EvidenceValue]
) -> EvidenceValue:
    if expr.kind == "constant":
        return expr.value  # type: ignore[return-value]
    if expr.kind == "variable":
        return environment[str(expr.value)]
    if expr.kind == "array":
        return tuple(int(evaluate(item, environment)) for item in expr.args)
    if expr.kind == "select":
        array = evaluate(expr.args[0], environment)
        index = int(evaluate(expr.args[1], environment))
        if not isinstance(array, tuple) or not 0 <= index < len(array):
            raise ValueError("array index is outside the owned array")
        return array[index]
    if expr.kind == "store":
        array = evaluate(expr.args[0], environment)
        index = int(evaluate(expr.args[1], environment))
        value = int(evaluate(expr.args[2], environment))
        if not isinstance(array, tuple) or not 0 <= index < len(array):
            raise ValueError("array index is outside the owned array")
        updated = list(array)
        updated[index] = value
        return tuple(updated)
    if expr.kind == "cast":
        value = evaluate(expr.args[0], environment)
        if expr.args[0].type == "bool" and is_fixed_integer_type(expr.type):
            return int(bool(value))
        return convert_integer(int(value), expr.type)
    if expr.kind == "predicate":
        if len(expr.args) != 1:
            raise ValueError(f"unsupported predicate {expr.op}")
        operation = expr.args[0]
        if expr.op == "signed_no_overflow":
            if (
                operation.kind != "binary"
                or operation.op not in {"+", "-", "*"}
                or not is_signed_integer_type(operation.type)
                or len(operation.args) != 2
                or any(
                    argument.type != operation.type
                    for argument in operation.args
                )
            ):
                raise ValueError("malformed signed-overflow predicate")
            return integer_type(operation.type).contains(
                int(evaluate(operation, environment))
            )
        if expr.op == "signed_left_shift_defined":
            if (
                operation.kind != "binary"
                or operation.op != "<<"
                or not is_signed_integer_type(operation.type)
                or len(operation.args) != 2
                or operation.args[0].type != operation.type
                or not is_fixed_integer_type(operation.args[1].type)
            ):
                raise ValueError("malformed signed-left-shift predicate")
            left = int(evaluate(operation.args[0], environment))
            count = int(evaluate(operation.args[1], environment))
            profile = integer_type(operation.type)
            return (
                0 <= count < profile.width
                and left >= 0
                and left * (2**count) < 2**profile.width
            )
        raise ValueError(f"unsupported predicate {expr.op}")
    if expr.kind == "unary":
        value = evaluate(expr.args[0], environment)
        if expr.op == "!":
            return not bool(value)
        if expr.op == "-":
            return _integer_value(-int(value), expr.type)
        if expr.op == "~":
            return convert_integer(~int(value), expr.type)
        raise ValueError(f"unsupported unary operator {expr.op}")
    op = expr.op
    # Preserve C++ short-circuit evaluation so an unreachable partial RHS does
    # not invalidate an otherwise concrete model.
    left = evaluate(expr.args[0], environment)
    if op == "&&":
        return bool(left) and bool(evaluate(expr.args[1], environment))
    if op == "||":
        return bool(left) or bool(evaluate(expr.args[1], environment))
    right = evaluate(expr.args[1], environment)
    if op == "+":
        return _integer_value(int(left) + int(right), expr.type)
    if op == "-":
        return _integer_value(int(left) - int(right), expr.type)
    if op == "*":
        return _integer_value(int(left) * int(right), expr.type)
    if op == "/":
        if is_unsigned_integer_type(expr.type):
            return int(left) // int(right)
        return _cxx_div(int(left), int(right))
    if op == "%":
        if is_unsigned_integer_type(expr.type):
            return int(left) % int(right)
        quotient = _cxx_div(int(left), int(right))
        return _integer_value(int(left) - int(right) * quotient, expr.type)
    if op == "&":
        return convert_integer(int(left) & int(right), expr.type)
    if op == "|":
        return convert_integer(int(left) | int(right), expr.type)
    if op == "^":
        return convert_integer(int(left) ^ int(right), expr.type)
    if op in {"<<", ">>"}:
        count = int(right)
        if count < 0 or count >= integer_type(expr.type).width:
            raise ValueError("shift count is outside the result width")
        value = int(left) << count if op == "<<" else int(left) >> count
        return convert_integer(value, expr.type)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise ValueError(f"unsupported operator {op}")


def _variable_types(expressions: Iterable[Expr]) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(expr: Expr) -> None:
        if expr.kind == "variable":
            result[str(expr.value)] = expr.type
        for argument in expr.args:
            visit(argument)

    for expression in expressions:
        visit(expression)
    return result


def _integer_constants(expressions: Iterable[Expr]) -> set[int]:
    result: set[int] = set()

    def visit(expr: Expr) -> None:
        if expr.kind == "constant" and is_signed_integer_type(expr.type):
            result.add(int(expr.value))
        for argument in expr.args:
            visit(argument)

    for expression in expressions:
        visit(expression)
    return result


def _integer_domain(type_name: str, constants: set[int]) -> tuple[int, ...]:
    profile = {"i32": I32, "i64": I64}.get(type_name)
    if profile is None:
        raise ValueError(f"unsupported search integer type {type_name!r}")
    values = {
        profile.minimum,
        profile.minimum + 1,
        -2,
        -1,
        0,
        1,
        2,
        profile.maximum - 1,
        profile.maximum,
    }
    for value in constants:
        for candidate in (value - 1, value, value + 1):
            if profile.contains(candidate):
                values.add(candidate)
    return tuple(sorted(values))


def find_satisfying_model(
    expressions: tuple[Expr, ...],
    max_evaluations: int = 100_000,
) -> tuple[bool, dict[str, int | bool]]:
    types = _variable_types(expressions)
    names = sorted(types)
    constants = _integer_constants(expressions)
    domains = [
        (False, True)
        if types[name] == "bool"
        else _integer_domain(types[name], constants)
        for name in names
    ]
    for checked, values in enumerate(product(*domains), start=1):
        if checked > max_evaluations:
            break
        environment = dict(zip(names, values))
        try:
            if all(bool(evaluate(item, environment)) for item in expressions):
                return True, environment
        except (ArithmeticError, KeyError, TypeError, ValueError):
            continue
    return False, {}


def find_counterexample(
    assumptions: tuple[Expr, ...],
    conclusion: Expr,
    max_evaluations: int = 100_000,
) -> tuple[bool, dict[str, int | bool]]:
    expressions = assumptions + (conclusion,)
    types = _variable_types(expressions)
    names = sorted(types)
    constants = _integer_constants(expressions)
    domains = [
        (False, True)
        if types[name] == "bool"
        else _integer_domain(types[name], constants)
        for name in names
    ]
    checked = 0
    for values in product(*domains):
        checked += 1
        if checked > max_evaluations:
            break
        environment = dict(zip(names, values))
        try:
            if not all(bool(evaluate(item, environment)) for item in assumptions):
                continue
            if not bool(evaluate(conclusion, environment)):
                return True, environment
        except (ArithmeticError, KeyError, TypeError, ValueError):
            continue
    return False, {}


class TraceResolutionError(ValueError):
    """Raised when compact path provenance cannot resolve against a model."""


def resolve_trace(
    templates: tuple[TraceTemplate, ...],
    model: Mapping[str, EvidenceValue],
) -> tuple[TraceStep, ...]:
    resolved: list[TraceStep] = []
    for template in templates:
        try:
            active = all(bool(evaluate(item, model)) for item in template.guard)
            if not active:
                continue
            taken = evaluate(template.condition, model)
        except (ArithmeticError, KeyError, TypeError, ValueError) as error:
            raise TraceResolutionError(
                f"cannot resolve {template.kind} trace at "
                f"{template.location.file}:{template.location.line}: "
                f"{error}"
            ) from error
        if not isinstance(taken, bool):
            raise TraceResolutionError(
                f"trace condition at {template.location.file}:"
                f"{template.location.line} did not evaluate to bool"
            )
        resolved.append(
            TraceStep(
                template.kind,
                template.condition,
                taken,
                template.location,
            )
        )
    return tuple(resolved)


def _human_counterexample(
    model: Mapping[str, EvidenceValue]
) -> dict[str, EvidenceValue]:
    result: dict[str, EvidenceValue] = {}
    for name in sorted(model):
        base, separator, version = name.partition("#")
        shown = base if separator and version == "0" else name
        if shown in result:
            shown = name
        result[shown] = model[name]
    return result


def _proves_violation_core(
    assumptions: tuple[Expr, ...],
    conclusion: Expr,
) -> bool:
    return prove_disjunctive_validity(conclusion, assumptions) is True


class AffineChecker(CheckerBackend):
    name = "affine-facts-plus-counterexample-search"

    def check_all(
        self, obligations: Iterable[Obligation]
    ) -> tuple[VerificationResult, ...]:
        return tuple(self.check(obligation) for obligation in obligations)

    def check(self, obligation: Obligation) -> VerificationResult:
        if obligation.unsupported_reason:
            return self._result(
                obligation,
                VerificationStatus.UNSUPPORTED,
                f"unsupported: {obligation.unsupported_reason}",
            )
        if obligation.mode not in {"validity", "satisfiable", "well_formed"}:
            return self._result(
                obligation,
                VerificationStatus.SOLVER_ERROR,
                f"checker error: unknown obligation mode {obligation.mode!r}",
            )
        if obligation.mode == "validity" and obligation.conclusion is None:
            return self._result(
                obligation,
                VerificationStatus.UNSUPPORTED,
                "unsupported: missing logical conclusion",
            )
        try:
            raw_expressions = obligation.assumptions
            if obligation.conclusion is not None:
                raw_expressions += (obligation.conclusion,)
            if not all(logic_supported(item) for item in raw_expressions):
                return self._result(
                    obligation,
                    VerificationStatus.UNSUPPORTED,
                    "unsupported: obligation is outside quantifier-free affine integer/boolean logic",
                )
            if obligation.mode == "well_formed":
                return self._result(
                    obligation,
                    VerificationStatus.VERIFIED,
                    "verified: contract expression is in the supported logic fragment",
                )
            if obligation.mode == "satisfiable":
                prepared, _ = prepare_formulas(
                    obligation.assumptions, Expr.boolean(True)
                )
                if assumptions_infeasible(prepared):
                    return self._result(
                        obligation,
                        VerificationStatus.VIOLATED,
                        "violated: contract requirements are infeasible",
                    )
                found, _ = find_satisfying_model(obligation.assumptions)
                if found:
                    return self._result(
                        obligation,
                        VerificationStatus.VERIFIED,
                        "verified: deterministic search found a satisfying contract input",
                    )
                return self._result(
                    obligation,
                    VerificationStatus.UNKNOWN,
                    "unknown: no contradiction proof and no satisfying model in the deterministic search set",
                )

            assert obligation.conclusion is not None
            outcome = prove_disjunctive_validity(
                obligation.conclusion,
                obligation.assumptions,
            )
            if outcome is True:
                return self._result(
                    obligation,
                    VerificationStatus.VERIFIED,
                    "verified by exact affine simplification/path facts",
                )

            # Search the original formulas so every returned binding can be
            # replayed against the serialized obligation.  Substitution is a
            # proof optimization, not a model projection step.
            found, model = find_counterexample(
                obligation.assumptions, obligation.conclusion
            )
            if found:
                trace = resolve_trace(obligation.trace_templates, model)
                minimized = minimize_counterexample(
                    obligation,
                    model,
                    _proves_violation_core,
                )
                return self._result(
                    obligation,
                    VerificationStatus.VIOLATED,
                    (
                        "violated: deterministic search found and replayed a "
                        f"concrete model; minimized from {len(model)} to "
                        f"{len(minimized)} bindings"
                    ),
                    _human_counterexample(minimized),
                    trace,
                )
            return self._result(
                obligation,
                VerificationStatus.UNKNOWN,
                "unknown: no exact proof and no counterexample in the deterministic search set",
            )
        except Exception as error:  # Result taxonomy must include internal failures.
            return self._result(
                obligation,
                VerificationStatus.SOLVER_ERROR,
                f"checker error: {type(error).__name__}: {error}",
            )

    @staticmethod
    def _result(
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


# Backward-compatible name for the original public checker.
DeterministicChecker = AffineChecker
