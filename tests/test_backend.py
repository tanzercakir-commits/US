import contextlib
import io
from pathlib import Path
import unittest

from semantic_verifier.backend import (
    CheckerBackend,
    CrossCheckBackend,
    Z3Checker,
    create_backend,
)
from semantic_verifier.checker import AffineChecker, DeterministicChecker
from semantic_verifier.cli import build_parser, main
from semantic_verifier.model import (
    Expr,
    Obligation,
    SourceLocation,
    VerificationResult,
    VerificationStatus,
)
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


LOCATION = SourceLocation("backend.cpp", 1, 1)
OBLIGATION = Obligation(
    id="ob-backend",
    function="f",
    kind="postcondition",
    assumptions=(),
    conclusion=Expr.boolean(True),
    location=LOCATION,
    description="backend test",
)


def result(status, message=None, counterexample=None):
    return VerificationResult(
        obligation_id=OBLIGATION.id,
        function=OBLIGATION.function,
        kind=OBLIGATION.kind,
        status=status,
        location=LOCATION,
        message=message or status.value,
        counterexample=counterexample,
    )


class StubBackend(CheckerBackend):
    def __init__(self, name, returned):
        self.name = name
        self.returned = returned

    def check(self, obligation):
        return self.returned


class BackendInterfaceTests(unittest.TestCase):
    def test_affine_checker_implements_interface_and_keeps_compatibility_alias(self):
        self.assertIs(DeterministicChecker, AffineChecker)
        self.assertIsInstance(AffineChecker(), CheckerBackend)

    def test_check_all_preserves_obligation_order(self):
        backend = StubBackend("stub", result(VerificationStatus.VERIFIED))

        checked = backend.check_all((OBLIGATION, OBLIGATION))

        self.assertEqual(len(checked), 2)
        self.assertEqual(
            [item.obligation_id for item in checked],
            [OBLIGATION.id, OBLIGATION.id],
        )

    def test_factory_creates_stable_backend_selections(self):
        self.assertIsInstance(create_backend("affine"), AffineChecker)
        self.assertIsInstance(create_backend("z3"), Z3Checker)
        self.assertIsInstance(create_backend("both"), CrossCheckBackend)
        with self.assertRaises(ValueError):
            create_backend("other")


class CrossCheckBackendTests(unittest.TestCase):
    def cross_check(self, primary, secondary):
        return CrossCheckBackend(
            StubBackend("primary", primary),
            StubBackend("secondary", secondary),
        ).check(OBLIGATION)

    def test_definitive_disagreement_is_soundness_alarm(self):
        checked = self.cross_check(
            result(VerificationStatus.VERIFIED),
            result(VerificationStatus.VIOLATED, counterexample={"x": 0}),
        )

        self.assertEqual(checked.status.value, "solver_error")
        self.assertIn("soundness alarm", checked.message)
        self.assertIn("primary=verified", checked.message)
        self.assertIn("secondary=violated", checked.message)

    def test_agreement_uses_replayed_secondary_counterexample(self):
        checked = self.cross_check(
            result(VerificationStatus.VIOLATED, counterexample={"x": 1}),
            result(VerificationStatus.VIOLATED, counterexample={"x": 2}),
        )

        self.assertEqual(checked.status.value, "violated")
        self.assertEqual(checked.counterexample, {"x": 2})

    def test_definitive_result_can_strengthen_unknown(self):
        checked = self.cross_check(
            result(VerificationStatus.UNKNOWN),
            result(VerificationStatus.VERIFIED),
        )

        self.assertEqual(checked.status.value, "verified")

    def test_unsupported_and_solver_error_remain_fail_closed(self):
        unsupported = self.cross_check(
            result(VerificationStatus.VERIFIED),
            result(VerificationStatus.UNSUPPORTED),
        )
        failed = self.cross_check(
            result(VerificationStatus.VERIFIED),
            result(VerificationStatus.SOLVER_ERROR),
        )

        self.assertEqual(unsupported.status.value, "unsupported")
        self.assertEqual(failed.status.value, "solver_error")


class BackendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def test_cli_parser_defaults_to_both_and_accepts_all_backends(self):
        self.assertEqual(build_parser().parse_args(["input.cpp"]).backend, "both")
        for name in ("affine", "z3", "both"):
            with self.subTest(name=name):
                self.assertEqual(
                    build_parser().parse_args(["input.cpp", "--backend", name]).backend,
                    name,
                )

    def test_vertical_slice_has_no_z3_cross_check_disagreement(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        expected = {
            "affine": {"verified": 9, "violated": 2, "unknown": 1},
            "z3": {"verified": 10, "violated": 2},
            "both": {"verified": 10, "violated": 2},
        }
        for name in ("affine", "z3", "both"):
            with self.subTest(name=name):
                pipeline = VerificationPipeline()
                pipeline.checker = create_backend(name, z3=self.z3)
                report = pipeline.verify_file("examples/vertical_slice.cpp")
                summary = {
                    key: value
                    for key, value in report.summary().items()
                    if value
                }
                self.assertEqual(summary, expected[name])
                self.assertEqual(report.summary()["solver_error"], 0)

    def test_cli_both_mode_reports_normal_violation_exit(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        stdout = io.StringIO()
        stderr = io.StringIO()
        example = Path("examples/vertical_slice.cpp")
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [str(example), "--backend", "both", "--format", "json"]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn('"solver_error": 0', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
