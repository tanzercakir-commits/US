"""Swappable checker backends and deterministic cross-check selection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from .model import (
    Obligation,
    TraceStep,
    VerificationResult,
    VerificationStatus,
)
from .record_types import RecordValue

if TYPE_CHECKING:
    from .budget import SolverTimeout
    from .z3_backend import Z3ProcessRunner


_DEFINITIVE = frozenset(
    {VerificationStatus.VERIFIED, VerificationStatus.VIOLATED}
)


class CheckerBackend(ABC):
    """Interface implemented by every obligation referee backend."""

    name: str

    @abstractmethod
    def check(self, obligation: Obligation) -> VerificationResult:
        """Check exactly one obligation."""

    def check_all(
        self, obligations: Iterable[Obligation]
    ) -> tuple[VerificationResult, ...]:
        return tuple(self.check(obligation) for obligation in obligations)

    def cache_identity(self) -> Mapping[str, object]:
        """Return stable referee identity and result-relevant configuration."""

        return {"implementation": "v0", "name": self.name}


class Z3Checker(CheckerBackend):
    name = "z3-homogeneous-qf-lia-qf-bv-qf-array-qf-record"

    def __init__(
        self,
        z3: str | None = None,
        timeout_seconds: float | SolverTimeout = 5.0,
        *,
        runner: Z3ProcessRunner | None = None,
    ) -> None:
        if runner is None:
            from .z3_backend import Z3ProcessRunner

            runner = Z3ProcessRunner(z3, timeout_seconds)
        self.runner = runner

    def check(self, obligation: Obligation) -> VerificationResult:
        from .z3_backend import check_obligation

        return check_obligation(obligation, self.runner)

    def cache_identity(self) -> Mapping[str, object]:
        identity = getattr(self.runner, "cache_identity", None)
        configuration = (
            identity()
            if callable(identity)
            else {"runner": type(self.runner).__qualname__}
        )
        return {
            "configuration": configuration,
            "implementation": "smtlib-replay/v5",
            "query_policy": "homogeneous-qf-lia-qf-bv-qf-array-qf-record/v3",
            "name": self.name,
        }


class CrossCheckBackend(CheckerBackend):
    """Run two sound backends and alarm on definitive disagreement."""

    name = "affine-z3-cross-check"

    def __init__(
        self,
        primary: CheckerBackend,
        secondary: CheckerBackend,
    ) -> None:
        self.primary = primary
        self.secondary = secondary

    def check(self, obligation: Obligation) -> VerificationResult:
        primary = self.primary.check(obligation)
        secondary = self.secondary.check(obligation)
        if (
            primary.status in _DEFINITIVE
            and secondary.status in _DEFINITIVE
            and primary.status != secondary.status
        ):
            return _result(
                obligation,
                VerificationStatus.SOLVER_ERROR,
                "solver error: backend soundness alarm: "
                f"{self.primary.name}={primary.status.value}, "
                f"{self.secondary.name}={secondary.status.value}",
            )

        if VerificationStatus.SOLVER_ERROR in {
            primary.status,
            secondary.status,
        }:
            failed = (
                primary
                if primary.status == VerificationStatus.SOLVER_ERROR
                else secondary
            )
            return _result(
                obligation,
                VerificationStatus.SOLVER_ERROR,
                "solver error: backend cross-check failed: " + failed.message,
            )

        if VerificationStatus.UNSUPPORTED in {
            primary.status,
            secondary.status,
        }:
            unsupported = (
                primary
                if primary.status == VerificationStatus.UNSUPPORTED
                else secondary
            )
            return _result(
                obligation,
                VerificationStatus.UNSUPPORTED,
                "unsupported in backend cross-check: " + unsupported.message,
            )

        resource_unknown = _resource_unknown(primary, secondary)
        if resource_unknown is not None:
            return _result(
                obligation,
                VerificationStatus.UNKNOWN,
                "unknown: backend cross-check resource exhaustion: "
                + resource_unknown.message.removeprefix("unknown: "),
            )

        selected = _select_strong_result(primary, secondary)
        return _result(
            obligation,
            selected.status,
            "backend cross-check completed: " + selected.message,
            selected.counterexample,
            selected.trace,
        )

    def cache_identity(self) -> Mapping[str, object]:
        return {
            "implementation": "definitive-agreement/v0",
            "name": self.name,
            "primary": self.primary.cache_identity(),
            "secondary": self.secondary.cache_identity(),
        }


def create_backend(
    name: str,
    *,
    z3: str | None = None,
    timeout_seconds: float | SolverTimeout = 5.0,
) -> CheckerBackend:
    """Create a backend from the stable CLI selection names."""

    from .checker import AffineChecker

    if name == "affine":
        return AffineChecker()
    if name == "z3":
        return Z3Checker(z3, timeout_seconds)
    if name == "both":
        return CrossCheckBackend(
            AffineChecker(),
            Z3Checker(z3, timeout_seconds),
        )
    raise ValueError(f"unknown checker backend {name!r}")


def _resource_unknown(
    primary: VerificationResult,
    secondary: VerificationResult,
) -> VerificationResult | None:
    for result in (primary, secondary):
        if result.status == VerificationStatus.UNKNOWN and result.message.startswith(
            ("unknown: Z3 timed out", "unknown: file check budget exhausted")
        ):
            return result
    return None


def _select_strong_result(
    primary: VerificationResult,
    secondary: VerificationResult,
) -> VerificationResult:
    if secondary.status in _DEFINITIVE:
        return secondary
    if primary.status in _DEFINITIVE:
        return primary
    if primary.status == VerificationStatus.UNKNOWN:
        return primary
    return secondary


def _result(
    obligation: Obligation,
    status: VerificationStatus,
    message: str,
    counterexample: Mapping[str, int | bool | tuple[int, ...] | RecordValue] | None = None,
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
