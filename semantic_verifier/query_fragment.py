"""Deterministic homogeneous SMT query-fragment classification."""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from .integer_types import is_unsigned_integer_type
from .model import Expr, Obligation


class QueryFragment(str, Enum):
    QF_LIA = "QF_LIA"
    QF_BV = "QF_BV"


def classify_expressions(expressions: Iterable[Expr]) -> QueryFragment:
    """Classify unsigned-tainted or bitwise formulas as homogeneous BV."""

    pending = list(expressions)
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


def classify_obligation(obligation: Obligation) -> QueryFragment:
    expressions = list(obligation.assumptions)
    if obligation.conclusion is not None:
        expressions.append(obligation.conclusion)
    return classify_expressions(expressions)
