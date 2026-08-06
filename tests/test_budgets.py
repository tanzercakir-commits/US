import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from semantic_verifier.backend import CheckerBackend, CrossCheckBackend, Z3Checker
from semantic_verifier.budget import (
    BudgetedCheckerBackend,
    FileCheckBudget,
    SolverTimeout,
)
from semantic_verifier.cache import CachedCheckerBackend
from semantic_verifier.cli import build_parser
from semantic_verifier.model import (
    Expr,
    Obligation,
    SourceLocation,
    VerificationResult,
    VerificationStatus,
)
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3Outcome, Z3RunResult


LOCATION = SourceLocation("budget.cpp", 3, 1)


def obligation(identifier, *, unsupported_reason=None):
    return Obligation(
        id=identifier,
        function="budgeted",
        kind="assertion",
        assumptions=(),
        conclusion=Expr.boolean(True),
        location=LOCATION,
        description="budget test",
        unsupported_reason=unsupported_reason,
    )


class CountingBackend(CheckerBackend):
    name = "budget-counting"

    def __init__(self):
        self.calls = []

    def check(self, item):
        self.calls.append(item.id)
        status = (
            VerificationStatus.UNSUPPORTED
            if item.unsupported_reason is not None
            else VerificationStatus.VERIFIED
        )
        return VerificationResult(
            obligation_id=item.id,
            function=item.function,
            kind=item.kind,
            status=status,
            location=item.location,
            message=f"{status.value}: counted",
        )


class TimeoutRunner:
    def cache_identity(self):
        return {"runner": "injected-timeout"}

    def run(self, smtlib, mode="validity"):
        return Z3RunResult(
            outcome=Z3Outcome.TIMEOUT,
            status=VerificationStatus.UNKNOWN,
            message="unknown: Z3 timed out after 0.01 seconds",
        )


class ModelTimeoutRunner:
    def __init__(self):
        self.calls = 0

    def run(self, smtlib, mode="validity"):
        self.calls += 1
        if self.calls == 1:
            return Z3RunResult(
                outcome=Z3Outcome.SAT,
                status=VerificationStatus.VIOLATED,
                message="violated candidate",
            )
        return TimeoutRunner().run(smtlib, mode)


class ResourceBudgetTests(unittest.TestCase):
    def test_value_objects_accept_zero_and_unlimited_boundaries(self):
        self.assertEqual(SolverTimeout(1.25).seconds, 1.25)
        self.assertEqual(FileCheckBudget(0).max_checks, 0)
        self.assertTrue(FileCheckBudget().unlimited)
        for invalid in (-1, True, 1.5):
            with self.subTest(file_budget=invalid):
                with self.assertRaises(ValueError):
                    FileCheckBudget(invalid)
        for invalid in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(solver_timeout=invalid):
                with self.assertRaises(ValueError):
                    SolverTimeout(invalid)

    def test_exhaustion_is_unknown_and_preserves_started_results(self):
        backend = CountingBackend()
        checker = BudgetedCheckerBackend(backend, FileCheckBudget(1))

        results = checker.check_all(
            (obligation("ob1"), obligation("ob2"), obligation("ob3"))
        )

        self.assertEqual(backend.calls, ["ob1"])
        self.assertEqual(
            [item.status for item in results],
            [
                VerificationStatus.VERIFIED,
                VerificationStatus.UNKNOWN,
                VerificationStatus.UNKNOWN,
            ],
        )
        self.assertIn("obligation was not started", results[1].message)

    def test_unsupported_does_not_consume_a_supported_check_unit(self):
        backend = CountingBackend()
        checker = BudgetedCheckerBackend(backend, FileCheckBudget(1))

        results = checker.check_all(
            (
                obligation("unsupported", unsupported_reason="outside subset"),
                obligation("started"),
                obligation("unstarted"),
            )
        )

        self.assertEqual(backend.calls, ["unsupported", "started"])
        self.assertEqual(
            [item.status for item in results],
            [
                VerificationStatus.UNSUPPORTED,
                VerificationStatus.VERIFIED,
                VerificationStatus.UNKNOWN,
            ],
        )

    def test_zero_starts_none_and_unlimited_delegates_all(self):
        zero_backend = CountingBackend()
        zero = BudgetedCheckerBackend(zero_backend, FileCheckBudget(0))
        unlimited_backend = CountingBackend()
        unlimited = BudgetedCheckerBackend(unlimited_backend, FileCheckBudget())
        items = (obligation("ob1"), obligation("ob2"))

        zero_results = zero.check_all(items)
        unlimited_results = unlimited.check_all(items)

        self.assertEqual(zero_backend.calls, [])
        self.assertTrue(
            all(item.status == VerificationStatus.UNKNOWN for item in zero_results)
        )
        self.assertEqual(unlimited_backend.calls, ["ob1", "ob2"])
        self.assertTrue(
            all(
                item.status == VerificationStatus.VERIFIED
                for item in unlimited_results
            )
        )

    def test_budget_resets_for_each_check_all_file_boundary(self):
        backend = CountingBackend()
        checker = BudgetedCheckerBackend(backend, FileCheckBudget(1))
        items = (obligation("first"), obligation("second"))

        first = checker.check_all(items)
        second = checker.check_all(items)

        self.assertEqual(backend.calls, ["first", "first"])
        self.assertEqual(first, second)

    def test_file_budget_cannot_be_bypassed_by_a_warm_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.json"
            item = obligation("cached")
            CachedCheckerBackend(CountingBackend(), path).check(item)
            warm_backend = CountingBackend()
            checker = BudgetedCheckerBackend(
                CachedCheckerBackend(warm_backend, path),
                FileCheckBudget(0),
            )

            checked = checker.check_all((item,))

        self.assertEqual(warm_backend.calls, [])
        self.assertEqual(checked[0].status, VerificationStatus.UNKNOWN)
        self.assertIn("not started", checked[0].message)

    def test_repeated_budgeted_pipeline_json_is_byte_identical(self):
        source = """\
void assert(bool);
int budgeted(int x) {
    assert(x >= 0);
    assert(x <= 0);
    return x;
}
"""

        first = VerificationPipeline(
            checker=CountingBackend(),
            check_budget=FileCheckBudget(1),
        ).verify_source(source, "stable/budget.cpp")
        second = VerificationPipeline(
            checker=CountingBackend(),
            check_budget=FileCheckBudget(1),
        ).verify_source(source, "stable/budget.cpp")

        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.summary()["verified"], 1)
        self.assertEqual(first.summary()["unknown"], 1)

    def test_injected_solver_timeout_is_unknown(self):
        checked = Z3Checker(runner=TimeoutRunner()).check(obligation("timeout"))

        self.assertEqual(checked.status, VerificationStatus.UNKNOWN)
        self.assertIn("timed out", checked.message)

    def test_countermodel_request_timeout_is_unknown(self):
        checked = Z3Checker(runner=ModelTimeoutRunner()).check(
            Obligation(
                id="model-timeout",
                function="budgeted",
                kind="assertion",
                assumptions=(),
                conclusion=Expr.boolean(False),
                location=LOCATION,
                description="model timeout",
            )
        )

        self.assertEqual(checked.status, VerificationStatus.UNKNOWN)
        self.assertIn("replayable countermodel", checked.message)

    def test_cross_check_never_hides_timeout_as_verified(self):
        verified = CountingBackend()
        timeout = Z3Checker(runner=TimeoutRunner())

        checked = CrossCheckBackend(verified, timeout).check(obligation("cross"))

        self.assertEqual(checked.status, VerificationStatus.UNKNOWN)
        self.assertIn("resource exhaustion", checked.message)

    def test_cli_accepts_non_negative_budget_and_rejects_negative(self):
        self.assertIsNone(build_parser().parse_args(["input.cpp"]).max_checks)
        self.assertEqual(
            build_parser().parse_args(["input.cpp", "--max-checks", "0"]).max_checks,
            0,
        )
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["input.cpp", "--max-checks", "-1"])


if __name__ == "__main__":
    unittest.main()
