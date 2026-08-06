"""Deterministic homogeneous SMT query-fragment classification."""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from .array_types import is_array_type
from .integer_types import is_unsigned_integer_type
from .model import Expr, Obligation


class QueryFragment(str, Enum):
    QF_LIA = "QF_LIA"
    QF_BV = "QF_BV"
    QF_ARRAY = "QF_ARRAY"


def classify_expressions(expressions: Iterable[Expr]) -> QueryFragment:
    """Classify scalar LIA/BV or owned-array formulas deterministically."""

    pending = list(expressions)
    if any(
        expression.kind in {"array", "select", "store"}
        or is_array_type(expression.type)
        for root in pending
        for expression in _walk(root)
    ):
        return QueryFragment.QF_ARRAY
    while pending:
        expression = pending.pop()
        if is_unsigned_integer_type(expression.type) or expression.op in {
            "~",
            "&",
            "|",
            "^",
            "<<",
            ">>",
            "signed_left_shift_defined",
        }:
            return QueryFragment.QF_BV
        pending.extend(expression.args)
    return QueryFragment.QF_LIA


def _walk(expression: Expr) -> Iterable[Expr]:
    yield expression
    for argument in expression.args:
        yield from _walk(argument)


def classify_obligation(obligation: Obligation) -> QueryFragment:
    expressions = list(obligation.assumptions)
    if obligation.conclusion is not None:
        expressions.append(obligation.conclusion)
    return classify_expressions(expressions)
