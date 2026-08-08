"""Deterministic counterexample relevance and core minimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .array_types import array_type
from .record_types import RecordValue, record_type
from .model import Expr, Obligation


ValidityProver = Callable[[tuple[Expr, ...], Expr], bool]


def obligation_variable_cone(obligation: Obligation) -> frozenset[str]:
    """Return the transitive syntactic dependency cone of the conclusion."""

    if obligation.mode != "validity" or obligation.conclusion is None:
        return frozenset()

    relevant = set(obligation.conclusion.variables())
    changed = True
    while changed:
        changed = False
        for assumption in obligation.assumptions:
            variables = assumption.variables()
            if relevant.intersection(variables) and not variables <= relevant:
                relevant.update(variables)
                changed = True
    return frozenset(relevant)


def project_counterexample(
    obligation: Obligation,
    model: Mapping[str, int | bool | tuple[int, ...] | RecordValue],
) -> dict[str, int | bool | tuple[int, ...] | RecordValue]:
    """Project a replayed model to variables in the obligation cone."""

    if obligation.mode != "validity" or obligation.conclusion is None:
        return {name: model[name] for name in sorted(model)}
    relevant = obligation_variable_cone(obligation)
    return {name: model[name] for name in sorted(model) if name in relevant}


def minimize_counterexample(
    obligation: Obligation,
    model: Mapping[str, int | bool | tuple[int, ...] | RecordValue],
    proves: ValidityProver,
) -> dict[str, int | bool | tuple[int, ...] | RecordValue]:
    """Greedily remove bindings that are unnecessary to force a violation.

    The caller must first replay the complete model against the original
    validity obligation. Variables outside the conclusion's transitive
    assumption cone are projected out before greedy elimination. A retained
    core is sufficient when the obligation's assumptions plus the retained
    equalities imply the negated conclusion.
    """

    if obligation.mode != "validity" or obligation.conclusion is None:
        return {name: model[name] for name in sorted(model)}

    retained = project_counterexample(obligation, model)
    variable_types = _obligation_variable_types(obligation)
    negated_conclusion = Expr.unary("!", obligation.conclusion, "bool")
    for name in tuple(retained):
        candidate = dict(retained)
        candidate.pop(name)
        binding_facts = tuple(
            _binding_equality(key, candidate[key], variable_types[key])
            for key in sorted(candidate)
        )
        if proves(obligation.assumptions + binding_facts, negated_conclusion):
            retained = candidate
    return retained


def _obligation_variable_types(obligation: Obligation) -> dict[str, str]:
    result: dict[str, str] = {}
    expressions = obligation.assumptions
    if obligation.conclusion is not None:
        expressions += (obligation.conclusion,)
    for expression in expressions:
        pending = [expression]
        while pending:
            current = pending.pop()
            if current.kind == "variable":
                result[str(current.value)] = current.type
            pending.extend(current.args)
    return result


def _value_expression(
    value: int | bool | tuple[int, ...] | RecordValue,
    type_name: str,
) -> Expr:
    if type(value) is bool:
        if type_name != "bool":
            raise TypeError("boolean has the wrong type")
        return Expr.boolean(value)
    if type(value) is int:
        return Expr.integer(value, type_name)
    if isinstance(value, tuple):
        profile = array_type(type_name)
        if len(value) != profile.length or any(type(item) is not int for item in value):
            raise TypeError("array has the wrong shape")
        return Expr.array(
            (Expr.integer(item, profile.element_type) for item in value),
            profile.element_type,
        )
    if isinstance(value, RecordValue):
        if value.type != type_name:
            raise TypeError("record has the wrong type")
        profile = record_type(type_name)
        return Expr.record(
            (
                _value_expression(field_value, field.type)
                for field, field_value in zip(profile.fields, value.fields)
            ),
            type_name,
        )
    raise TypeError("unsupported concrete value")


def _binding_equality(
    name: str, value: int | bool | tuple[int, ...] | RecordValue, type_name: str
) -> Expr:
    try:
        constant = _value_expression(value, type_name)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"counterexample binding {name!r} has mismatched value: {error}"
        ) from error
    return Expr.binary(
        "==",
        Expr.variable(name, type_name),
        constant,
        "bool",
    )
