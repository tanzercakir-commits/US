import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.z3_backend import (
    Z3DiscoveryError,
    Z3Outcome,
    Z3ProcessRunner,
    discover_z3,
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


if __name__ == "__main__":
    unittest.main()
