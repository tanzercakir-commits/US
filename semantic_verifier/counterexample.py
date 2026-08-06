"""Deterministic counterexample relevance and core minimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .array_types import array_type
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
    model: Mapping[str, int | bool | tuple[int, ...]],
) -> dict[str, int | bool | tuple[int, ...]]:
    """Project a replayed model to variables in the obligation cone."""

    if obligation.mode != "validity" or obligation.conclusion is None:
        return {name: model[name] for name in sorted(model)}
    relevant = obligation_variable_cone(obligation)
    return {name: model[name] for name in sorted(model) if name in relevant}


def minimize_counterexample(
    obligation: Obligation,
    model: Mapping[str, int | bool | tuple[int, ...]],
    proves: ValidityProver,
) -> dict[str, int | bool | tuple[int, ...]]:
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


def _binding_equality(
    name: str, value: int | bool | tuple[int, ...], type_name: str
) -> Expr:
    if isinstance(value, bool):
        if type_name != "bool":
            raise TypeError(f"counterexample binding {name!r} has mismatched type")
        constant = Expr.boolean(value)
    elif isinstance(value, int):
        constant = Expr.integer(value, type_name)
    elif isinstance(value, tuple):
        profile = array_type(type_name)
        if len(value) != profile.length or any(type(item) is not int for item in value):
            raise TypeError(f"counterexample binding {name!r} has mismatched array value")
        constant = Expr.array(
            (Expr.integer(item, profile.element_type) for item in value),
            profile.element_type,
        )
    else:
        raise TypeError(f"counterexample binding {name!r} has unsupported value")
    return Expr.binary(
        "==",
        Expr.variable(name, type_name),
        constant,
        "bool",
    )
