from pathlib import Path
import unittest

from semantic_verifier import verify_source
from semantic_verifier.backend import create_backend
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


class RecursionPolicyTests(unittest.TestCase):
    def test_direct_recursion_is_explicitly_unsupported(self):
        report = verify_source(
            "// cs: ensures result >= 0\n"
            "int recursive(int x) { "
            "if (x > 0) { int y = recursive(x); return y; } return 0; }\n"
        )

        self.assertEqual(len(report.results), 1)
        result = report.results[0]
        self.assertEqual(result.function, "recursive")
        self.assertEqual(result.status.value, "unsupported")
        self.assertIn("direct recursion", result.message)
        self.assertIn("decreasing-measure policy", result.message)
        self.assertIn("recursive/1", result.message)

    def test_mutual_recursion_marks_every_function_in_the_cycle(self):
        report = verify_source(
            "int odd(int x);\n"
            "int even(int x) { int y = odd(x); return y; }\n"
            "int odd(int x) { int y = even(x); return y; }\n"
        )

        self.assertEqual(
            [(result.function, result.status.value) for result in report.results],
            [("even", "unsupported"), ("odd", "unsupported")],
        )
        for result in report.results:
            self.assertIn("mutual recursion", result.message)
            self.assertIn("even/1, odd/1", result.message)

    def test_overloaded_acyclic_call_is_not_mistaken_for_recursion(self):
        report = verify_source(
            "int choose(bool flag) { return 0; }\n"
            "int choose(int x) { choose(true); return x; }\n"
        )

        self.assertFalse(
            any("recursion" in result.message for result in report.results)
        )
        self.assertFalse(
            any(result.status.value == "unsupported" for result in report.results)
        )

    def test_existing_modular_chain_remains_acyclic_and_verified(self):
        try:
            z3 = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")
        pipeline = VerificationPipeline()
        pipeline.checker = create_backend("both", z3=z3)

        report = pipeline.verify_file(Path("examples/modular_calls.cpp"))

        self.assertEqual(report.summary()["verified"], 6)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(report.summary()["solver_error"], 0)


if __name__ == "__main__":
    unittest.main()
