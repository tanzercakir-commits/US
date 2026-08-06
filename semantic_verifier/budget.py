"""Deterministic solver and per-file verification work budgets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math

from .backend import CheckerBackend
from .model import Obligation, VerificationResult, VerificationStatus


@dataclass(frozen=True, slots=True)
class SolverTimeout:
    """Positive finite wall-clock limit for each external solver process."""

    seconds: float = 5.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.seconds, bool)
            or not isinstance(self.seconds, (int, float))
            or not math.isfinite(self.seconds)
            or self.seconds <= 0
        ):
            raise ValueError("solver timeout must be a finite positive number")
        object.__setattr__(self, "seconds", float(self.seconds))


@dataclass(frozen=True, slots=True)
class FileCheckBudget:
    """Maximum supported obligation checks started for each source file."""

    max_checks: int | None = None

    def __post_init__(self) -> None:
        if self.max_checks is None:
            return
        if type(self.max_checks) is not int or self.max_checks < 0:
            raise ValueError("file check budget must be a non-negative integer or None")

    @property
    def unlimited(self) -> bool:
        return self.max_checks is None


class BudgetedCheckerBackend(CheckerBackend):
    """Apply one deterministic top-level check unit per supported obligation."""

    def __init__(self, backend: CheckerBackend, budget: FileCheckBudget) -> None:
        self.backend = backend
        self.budget = budget
        self.name = backend.name

    def cache_identity(self) -> Mapping[str, object]:
        return {
            "backend": self.backend.cache_identity(),
            "file_check_budget": self.budget.max_checks,
            "implementation": "source-order-check-units/v0",
        }

    def check(self, obligation: Obligation) -> VerificationResult:
        if obligation.unsupported_reason is not None or self.budget.unlimited:
            return self.backend.check(obligation)
        if self.budget.max_checks == 0:
            return _exhausted_result(obligation, 0)
        return self.backend.check(obligation)

    def check_all(
        self, obligations: Iterable[Obligation]
    ) -> tuple[VerificationResult, ...]:
        if self.budget.unlimited:
            return self.backend.check_all(obligations)

        assert self.budget.max_checks is not None
        used = 0
        results: list[VerificationResult] = []
        for obligation in obligations:
            if obligation.unsupported_reason is not None:
                results.append(self.backend.check(obligation))
                continue
            if used >= self.budget.max_checks:
                results.append(_exhausted_result(obligation, self.budget.max_checks))
                continue
            used += 1
            results.append(self.backend.check(obligation))
        return tuple(results)


def _exhausted_result(
    obligation: Obligation,
    max_checks: int,
) -> VerificationResult:
    return VerificationResult(
        obligation_id=obligation.id,
        function=obligation.function,
        kind=obligation.kind,
        status=VerificationStatus.UNKNOWN,
        location=obligation.location,
        message=(
            "unknown: file check budget exhausted after "
            f"{max_checks} supported obligation checks; obligation was not started"
        ),
    )
