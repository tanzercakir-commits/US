"""Deterministic counterexample-core minimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .model import Expr, Obligation


ValidityProver = Callable[[tuple[Expr, ...], Expr], bool]


def minimize_counterexample(
    obligation: Obligation,
    model: Mapping[str, int | bool],
    proves: ValidityProver,
) -> dict[str, int | bool]:
    """Greedily remove bindings that are unnecessary to force a violation.

    The caller must first replay the complete model against the original
    validity obligation. A retained core is sufficient when the obligation's
    assumptions plus the retained equalities imply the negated conclusion.
    """

    if obligation.mode != "validity" or obligation.conclusion is None:
        return {name: model[name] for name in sorted(model)}

    retained = {name: model[name] for name in sorted(model)}
    negated_conclusion = Expr.unary("!", obligation.conclusion, "bool")
    for name in sorted(model):
        candidate = dict(retained)
        candidate.pop(name)
        binding_facts = tuple(
            _binding_equality(key, candidate[key]) for key in sorted(candidate)
        )
        if proves(obligation.assumptions + binding_facts, negated_conclusion):
            retained = candidate
    return retained


def _binding_equality(name: str, value: int | bool) -> Expr:
    if isinstance(value, bool):
        constant = Expr.boolean(value)
        type_name = "bool"
    elif isinstance(value, int):
        constant = Expr.integer(value)
        type_name = "int"
    else:
        raise TypeError(f"counterexample binding {name!r} has unsupported value")
    return Expr.binary(
        "==",
        Expr.variable(name, type_name),
        constant,
        "bool",
    )
