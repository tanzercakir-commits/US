"""End-to-end frontend, lowering, VC generation, and checking pipeline."""

from __future__ import annotations

from pathlib import Path

from .backend import CheckerBackend
from .budget import BudgetedCheckerBackend, FileCheckBudget
from .cache import CachedCheckerBackend
from .checker import DeterministicChecker
from .frontend import ClangJsonFrontend, FrontendError
from .lowering import SemanticLowerer
from .model import (
    Expr,
    IRNode,
    ModuleIR,
    Obligation,
    SourceLocation,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
)
from .vc import VerificationConditionGenerator


class VerificationPipeline:
    def __init__(
        self,
        clang: str | None = None,
        *,
        checker: CheckerBackend | None = None,
        cache_path: str | Path | None = None,
        check_budget: FileCheckBudget | None = None,
    ) -> None:
        self.frontend: ClangJsonFrontend | None = None
        self._frontend_initialization_error: str | None = None
        try:
            self.frontend = ClangJsonFrontend(clang)
        except FrontendError as error:
            # Keep operational frontend failures inside the same deterministic
            # result envelope as checker failures. In particular, JSON mode
            # must never degrade to an unstructured stderr-only response.
            self._frontend_initialization_error = str(error)
        selected = checker or DeterministicChecker()
        if cache_path is not None:
            selected = CachedCheckerBackend(selected, cache_path)
        if check_budget is not None:
            selected = BudgetedCheckerBackend(selected, check_budget)
        self.checker = selected

    def verify_file(self, path: str | Path) -> VerificationReport:
        shown = Path(path).as_posix()
        if self._frontend_initialization_error is not None:
            return self._frontend_initialization_failure(
                shown, self._frontend_initialization_error
            )
        assert self.frontend is not None
        try:
            unit = self.frontend.parse_file(path, display_path=shown)
        except FrontendError as error:
            return self._frontend_failure(shown, str(error))
        return self._verify_unit(unit)

    def verify_source(
        self, source: str, display_path: str = "test.cpp"
    ) -> VerificationReport:
        if self._frontend_initialization_error is not None:
            return self._frontend_initialization_failure(
                display_path, self._frontend_initialization_error
            )
        assert self.frontend is not None
        try:
            unit = self.frontend.parse_source(source, display_path=display_path)
        except FrontendError as error:
            return self._frontend_failure(display_path, str(error))
        return self._verify_unit(unit)

    def _verify_unit(self, unit) -> VerificationReport:
        module = SemanticLowerer(unit).lower()
        obligations = VerificationConditionGenerator(module).generate()
        results = self.checker.check_all(obligations)
        return VerificationReport(module, obligations, results)

    def _frontend_failure(self, source: str, reason: str) -> VerificationReport:
        location = SourceLocation(source.replace("\\", "/"), 1, 1)
        module = ModuleIR(
            source=location.file,
            functions=(),
            unsupported=(
                IRNode(
                    id="u00001",
                    kind="unsupported",
                    location=location,
                    reason=f"frontend failure: {reason}",
                ),
            ),
        )
        obligations = VerificationConditionGenerator(module).generate()
        return VerificationReport(module, obligations, self.checker.check_all(obligations))

    @staticmethod
    def _frontend_initialization_failure(
        source: str, reason: str
    ) -> VerificationReport:
        location = SourceLocation(source.replace("\\", "/"), 1, 1)
        message = f"frontend initialization failed: {reason}"
        module = ModuleIR(source=location.file, functions=())
        obligation = Obligation(
            id="ob00001",
            function="<frontend>",
            kind="frontend_initialization",
            assumptions=(),
            conclusion=Expr.variable("clang_frontend_initialized", "bool"),
            location=location,
            description="Clang frontend must initialize before semantic lowering",
        )
        result = VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=VerificationStatus.SOLVER_ERROR,
            location=location,
            message=message,
        )
        return VerificationReport(module, (obligation,), (result,))


def verify_file(path: str | Path, clang: str | None = None) -> VerificationReport:
    return VerificationPipeline(clang).verify_file(path)


def verify_source(
    source: str,
    display_path: str = "test.cpp",
    clang: str | None = None,
) -> VerificationReport:
    return VerificationPipeline(clang).verify_source(source, display_path)
