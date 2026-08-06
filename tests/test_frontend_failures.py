import contextlib
import io
import json
import unittest
from unittest.mock import patch

from semantic_verifier.cli import main
from semantic_verifier.frontend import FrontendError
from semantic_verifier.pipeline import VerificationPipeline


DISCOVERY_ERROR = "Clang was not found for this test"


class FrontendFailureTests(unittest.TestCase):
    def test_discovery_failure_is_a_deterministic_solver_error_report(self):
        with patch(
            "semantic_verifier.frontend.discover_clang",
            side_effect=FrontendError(DISCOVERY_ERROR),
        ):
            first = VerificationPipeline().verify_source(
                "int f() { return 0; }\n", "missing-clang.cpp"
            )
            second = VerificationPipeline().verify_source(
                "int f() { return 0; }\n", "missing-clang.cpp"
            )

        self.assertEqual(first.to_json(), second.to_json())
        payload = json.loads(first.to_json())
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v5")
        self.assertEqual(payload["source"], "missing-clang.cpp")
        self.assertEqual(payload["summary"]["solver_error"], 1)
        self.assertEqual(len(payload["obligations"]), 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["status"], "solver_error")
        self.assertEqual(
            payload["results"][0]["kind"], "frontend_initialization"
        )
        self.assertIn(DISCOVERY_ERROR, payload["results"][0]["message"])

    def test_json_cli_emits_report_and_exit_three_on_discovery_failure(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "semantic_verifier.frontend.discover_clang",
            side_effect=FrontendError(DISCOVERY_ERROR),
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "input.cpp",
                    "--format",
                    "json",
                    "--clang",
                    "missing-clang",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v5")
        self.assertEqual(payload["summary"]["solver_error"], 1)
        self.assertEqual(payload["results"][0]["status"], "solver_error")


if __name__ == "__main__":
    unittest.main()
