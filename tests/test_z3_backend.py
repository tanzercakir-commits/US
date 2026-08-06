import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from semantic_verifier.model import (
    Expr,
    Obligation,
    SourceLocation,
    TraceStep,
    TraceTemplate,
    VerificationStatus,
)
from semantic_verifier.z3_backend import (
    Z3DiscoveryError,
    Z3ModelError,
    Z3Outcome,
    Z3ProcessRunner,
    Z3RunResult,
    check_obligation,
    discover_z3,
    parse_z3_model,
)


QUERY = "(set-logic QF_LIA)\n(assert true)\n(check-sat)\n"


class Z3DiscoveryTests(unittest.TestCase):
    def test_explicit_path_precedes_environment_and_path(self):
        with tempfile.TemporaryDirectory() as directory:
            explicit = Path(directory) / "explicit-z3"
            configured = Path(directory) / "configured-z3"
            on_path = Path(directory) / "path-z3"
            for candidate in (explicit, configured, on_path):
                candidate.write_bytes(b"")
            with patch.dict(
                os.environ,
                {"SEMANTIC_VERIFIER_Z3": str(configured)},
                clear=True,
            ), patch(
                "semantic_verifier.z3_backend.shutil.which",
                return_value=str(on_path),
            ), patch(
                "semantic_verifier.z3_backend._known_z3_candidates",
                return_value=(),
            ):
                self.assertEqual(discover_z3(str(explicit)), str(explicit))

    def test_environment_precedes_path(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = Path(directory) / "configured-z3"
            on_path = Path(directory) / "path-z3"
            configured.write_bytes(b"")
            on_path.write_bytes(b"")
            with patch.dict(
                os.environ,
                {"SEMANTIC_VERIFIER_Z3": str(configured)},
                clear=True,
            ), patch(
                "semantic_verifier.z3_backend.shutil.which",
                return_value=str(on_path),
            ), patch(
                "semantic_verifier.z3_backend._known_z3_candidates",
                return_value=(),
            ):
                self.assertEqual(discover_z3(), str(configured))

    def test_known_location_is_used_after_path(self):
        with tempfile.TemporaryDirectory() as directory:
            known = Path(directory) / "known-z3"
            known.write_bytes(b"")
            with patch.dict(os.environ, {}, clear=True), patch(
                "semantic_verifier.z3_backend.shutil.which", return_value=None
            ), patch(
                "semantic_verifier.z3_backend._known_z3_candidates",
                return_value=(str(known),),
            ):
                self.assertEqual(discover_z3(), str(known))

    def test_missing_z3_raises_stable_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "semantic_verifier.z3_backend.shutil.which", return_value=None
        ), patch(
            "semantic_verifier.z3_backend._known_z3_candidates", return_value=()
        ):
            with self.assertRaisesRegex(Z3DiscoveryError, "SEMANTIC_VERIFIER_Z3"):
                discover_z3()


class Z3ProcessRunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.executable = Path(self.directory.name) / "z3"
        self.executable.write_bytes(b"")

    def run_with_completed(self, stdout, *, mode="validity", returncode=0, stderr=""):
        completed = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )
        with patch(
            "semantic_verifier.z3_backend.subprocess.run", return_value=completed
        ):
            return Z3ProcessRunner(str(self.executable), 1.25).run(QUERY, mode)

    def test_validity_status_mapping(self):
        self.assertEqual(
            self.run_with_completed("unsat\n").status.value, "verified"
        )
        self.assertEqual(
            self.run_with_completed("sat\n").status.value, "violated"
        )
        self.assertEqual(
            self.run_with_completed("unknown\n").status.value, "unknown"
        )

    def test_satisfiability_status_mapping(self):
        self.assertEqual(
            self.run_with_completed("sat\n", mode="satisfiable").status.value,
            "verified",
        )
        self.assertEqual(
            self.run_with_completed("unsat\n", mode="satisfiable").status.value,
            "violated",
        )

    def test_command_has_fixed_determinism_and_timeout_options(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="unsat\n", stderr=""
        )
        with patch(
            "semantic_verifier.z3_backend.subprocess.run", return_value=completed
        ) as run:
            result = Z3ProcessRunner(str(self.executable), 1.25).run(QUERY)

        self.assertEqual(result.outcome, Z3Outcome.UNSAT)
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.executable))
        self.assertEqual(
            command[1:],
            [
                "-in",
                "-smt2",
                "timeout=1250",
                "smt.random_seed=0",
                "sat.random_seed=0",
                "parallel.enable=false",
            ],
        )
        self.assertEqual(run.call_args.kwargs["timeout"], 1.25)
        self.assertEqual(run.call_args.kwargs["input"], QUERY)

    def test_timeout_is_unknown(self):
        timeout = subprocess.TimeoutExpired(
            cmd=[str(self.executable)], timeout=0.01, output=b"partial"
        )
        with patch(
            "semantic_verifier.z3_backend.subprocess.run", side_effect=timeout
        ):
            result = Z3ProcessRunner(str(self.executable), 0.01).run(QUERY)

        self.assertEqual(result.outcome, Z3Outcome.TIMEOUT)
        self.assertEqual(result.status.value, "unknown")
        self.assertEqual(result.stdout, "partial")

    def test_nonzero_exit_and_unexpected_output_are_solver_errors(self):
        crashed = self.run_with_completed("", returncode=7, stderr="boom")
        malformed = self.run_with_completed("not-a-result\n")

        self.assertEqual(crashed.outcome, Z3Outcome.CRASH)
        self.assertEqual(crashed.status.value, "solver_error")
        self.assertIn("code 7", crashed.message)
        self.assertEqual(malformed.outcome, Z3Outcome.CRASH)
        self.assertEqual(malformed.status.value, "solver_error")

    def test_execution_failure_is_solver_error(self):
        with patch(
            "semantic_verifier.z3_backend.subprocess.run",
            side_effect=PermissionError("denied"),
        ):
            result = Z3ProcessRunner(str(self.executable)).run(QUERY)

        self.assertEqual(result.outcome, Z3Outcome.CRASH)
        self.assertEqual(result.status.value, "solver_error")
        self.assertIn("PermissionError", result.message)

    def test_missing_z3_and_invalid_request_keep_runner_alive(self):
        missing = Path(self.directory.name) / "missing-z3"
        with patch.dict(os.environ, {}, clear=True), patch(
            "semantic_verifier.z3_backend.shutil.which", return_value=None
        ), patch(
            "semantic_verifier.z3_backend._known_z3_candidates", return_value=()
        ):
            result = Z3ProcessRunner(str(missing)).run(QUERY)

        self.assertEqual(result.outcome, Z3Outcome.CONFIGURATION_ERROR)
        self.assertEqual(result.status.value, "solver_error")
        self.assertEqual(
            Z3ProcessRunner(str(self.executable)).run("", "validity").status.value,
            "solver_error",
        )
        self.assertEqual(
            Z3ProcessRunner(str(self.executable)).run(QUERY, "other").status.value,
            "solver_error",
        )

    def test_invalid_timeout_is_rejected(self):
        for timeout in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    Z3ProcessRunner(str(self.executable), timeout)

    def test_real_z3_process_when_installed(self):
        try:
            executable = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")

        result = Z3ProcessRunner(executable, 5).run(QUERY, "satisfiable")

        self.assertEqual(result.outcome, Z3Outcome.SAT)
        self.assertEqual(result.status.value, "verified")
        self.assertEqual(result.returncode, 0)


MODEL_OUTPUT = """sat
(
  (define-fun x_v0 () Int
    (- 4))
  (define-fun ready_v0 () Bool
    true)
  (define-fun y_u000040x2_v0 () Int
    7)
)
"""
LOCATION = SourceLocation("model.cpp", 1, 1)


def make_obligation(
    *, assumptions=(), conclusion=None, mode="validity", trace_templates=()
):
    return Obligation(
        id="ob-model",
        function="f",
        kind="postcondition",
        assumptions=tuple(assumptions),
        conclusion=conclusion,
        location=LOCATION,
        description="model replay test",
        mode=mode,
        trace_templates=trace_templates,
    )


def process_result(outcome, status, stdout=""):
    return Z3RunResult(
        outcome=outcome,
        status=status,
        message=f"{status.value}: injected result",
        stdout=stdout,
        returncode=0,
    )


class Z3ModelParserTests(unittest.TestCase):
    def test_parses_int_bool_negative_and_reversible_names(self):
        self.assertEqual(
            parse_z3_model(
                MODEL_OUTPUT,
                {"x#0": "int", "ready#0": "bool", "y@2#0": "int"},
            ),
            {"x#0": -4, "ready#0": True, "y@2#0": 7},
        )

    def test_accepts_model_wrapper_and_comments(self):
        output = "sat\n(model ; comment\n (define-fun x_v0 () Int 0))\n"

        self.assertEqual(parse_z3_model(output, {"x#0": "int"}), {"x#0": 0})

    def test_rejects_malformed_or_unsupported_model_forms(self):
        invalid_outputs = (
            "unsat\n()\n",
            "sat\n((define-fun x_v0 (Int) Int 0))\n",
            "sat\n((define-fun x_v0 () Real 0))\n",
            "sat\n((define-fun x_v0 () Int (+ 1 2)))\n",
            "sat\n((define-fun |x| () Int 0))\n",
            "sat\n((define-fun x_v0 () Int 0)\n",
        )
        for output in invalid_outputs:
            with self.subTest(output=output):
                with self.assertRaises(Z3ModelError):
                    parse_z3_model(output)

    def test_rejects_missing_unexpected_duplicate_and_wrong_sort_bindings(self):
        with self.assertRaisesRegex(Z3ModelError, "missing"):
            parse_z3_model(
                "sat\n((define-fun x_v0 () Int 0))\n",
                {"x#0": "int", "y#0": "int"},
            )
        with self.assertRaisesRegex(Z3ModelError, "unexpected"):
            parse_z3_model(
                "sat\n((define-fun x_v0 () Int 0))\n",
                {},
            )
        with self.assertRaisesRegex(Z3ModelError, "duplicate"):
            parse_z3_model(
                "sat\n((define-fun x_v0 () Int 0) "
                "(define-fun x_v0 () Int 1))\n"
            )
        with self.assertRaisesRegex(Z3ModelError, "sort mismatch"):
            parse_z3_model(
                "sat\n((define-fun x_v0 () Bool true))\n",
                {"x#0": "int"},
            )


class Z3CountermodelReplayTests(unittest.TestCase):
    def test_valid_countermodel_is_replayed_and_projected(self):
        x = Expr.variable("x#0")
        trace_templates = (
            TraceTemplate("branch", Expr.boolean(True), (), LOCATION),
        )
        expected_trace = (
            TraceStep("branch", Expr.boolean(True), True, LOCATION),
        )
        item = make_obligation(
            conclusion=Expr.binary(">=", x, Expr.integer(0)),
            trace_templates=trace_templates,
        )
        runner = Mock()
        runner.run.side_effect = (
            process_result(Z3Outcome.SAT, VerificationStatus.VIOLATED, "sat\n"),
            process_result(
                Z3Outcome.SAT,
                VerificationStatus.VIOLATED,
                "sat\n((define-fun x_v0 () Int (- 1)))\n",
            ),
            process_result(
                Z3Outcome.SAT,
                VerificationStatus.VIOLATED,
                "sat\n",
            ),
        )

        result = check_obligation(item, runner)

        self.assertEqual(result.status.value, "violated")
        self.assertEqual(result.counterexample, {"x": -1})
        self.assertEqual(result.trace, expected_trace)
        self.assertEqual(runner.run.call_count, 3)
        self.assertTrue(runner.run.call_args_list[1].args[0].endswith("(get-model)\n"))

    def test_corrupt_model_that_fails_replay_is_solver_error(self):
        x = Expr.variable("x#0")
        trace_templates = (
            TraceTemplate("branch", Expr.boolean(True), (), LOCATION),
        )
        expected_trace = (
            TraceStep("branch", Expr.boolean(True), True, LOCATION),
        )
        item = make_obligation(
            conclusion=Expr.binary(">=", x, Expr.integer(0)),
            trace_templates=trace_templates,
        )
        runner = Mock()
        runner.run.side_effect = (
            process_result(Z3Outcome.SAT, VerificationStatus.VIOLATED, "sat\n"),
            process_result(
                Z3Outcome.SAT,
                VerificationStatus.VIOLATED,
                "sat\n((define-fun x_v0 () Int 1))\n",
            ),
        )

        result = check_obligation(item, runner)

        self.assertEqual(result.status.value, "solver_error")
        self.assertIn("does not falsify", result.message)
        self.assertIsNone(result.counterexample)
        self.assertEqual(result.trace, ())

    def test_unresolvable_compact_trace_fails_closed(self):
        x = Expr.variable("x#0")
        missing = Expr.variable("missing#0", "bool")
        item = make_obligation(
            conclusion=Expr.binary(">=", x, Expr.integer(0)),
            trace_templates=(
                TraceTemplate("branch", missing, (), LOCATION),
            ),
        )
        runner = Mock()
        runner.run.side_effect = (
            process_result(Z3Outcome.SAT, VerificationStatus.VIOLATED, "sat\n"),
            process_result(
                Z3Outcome.SAT,
                VerificationStatus.VIOLATED,
                "sat\n((define-fun x_v0 () Int (- 1)))\n",
            ),
        )

        result = check_obligation(item, runner)

        self.assertEqual(result.status.value, "solver_error")
        self.assertIn("cannot resolve branch trace", result.message)
        self.assertIsNone(result.counterexample)
        self.assertEqual(result.trace, ())

    def test_malformed_or_disagreeing_model_query_is_solver_error(self):
        x = Expr.variable("x#0")
        item = make_obligation(conclusion=Expr.binary(">=", x, Expr.integer(0)))
        for second in (
            process_result(Z3Outcome.SAT, VerificationStatus.VIOLATED, "sat\n()\n"),
            process_result(Z3Outcome.UNKNOWN, VerificationStatus.UNKNOWN, "unknown\n"),
        ):
            with self.subTest(outcome=second.outcome):
                runner = Mock()
                runner.run.side_effect = (
                    process_result(
                        Z3Outcome.SAT, VerificationStatus.VIOLATED, "sat\n"
                    ),
                    second,
                )
                result = check_obligation(item, runner)
                self.assertEqual(result.status.value, "solver_error")

    def test_non_sat_result_does_not_request_model(self):
        item = make_obligation(conclusion=Expr.boolean(True))
        runner = Mock()
        runner.run.return_value = process_result(
            Z3Outcome.UNSAT, VerificationStatus.VERIFIED, "unsat\n"
        )

        result = check_obligation(item, runner)

        self.assertEqual(result.status.value, "verified")
        runner.run.assert_called_once()

    def test_well_formed_mode_is_checked_without_solver_process(self):
        item = make_obligation(
            conclusion=Expr.binary("==", Expr.variable("x#0"), Expr.integer(0)),
            mode="well_formed",
        )
        runner = Mock()

        result = check_obligation(item, runner)

        self.assertEqual(result.status.value, "verified")
        runner.run.assert_not_called()

    def test_real_violation_returns_replayed_bindings(self):
        try:
            executable = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")
        x = Expr.variable("x#0")
        item = make_obligation(conclusion=Expr.binary(">=", x, Expr.integer(0)))

        result = check_obligation(item, Z3ProcessRunner(executable, 5))

        self.assertEqual(result.status.value, "violated")
        self.assertIn("x", result.counterexample)
        self.assertLess(result.counterexample["x"], 0)


if __name__ == "__main__":
    unittest.main()
