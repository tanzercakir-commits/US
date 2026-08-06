import unittest

from semantic_verifier import verify_source


def results_for(report, *, function=None, kind=None):
    return [
        result
        for result in report.results
        if (function is None or result.function == function)
        and (kind is None or result.kind == kind)
    ]


SAFE_DIVIDE = """
// cs: requires b != 0
// cs: requires !(a == -2147483648 && b == -1)
int safe_divide(int a, int b) { return a / b; }
"""


class VerificationTests(unittest.TestCase):
    def test_valid_precondition(self):
        report = verify_source(
            SAFE_DIVIDE
            + "int caller(int x) { safe_divide(x, 2); return 0; }\n"
        )
        results = results_for(report, function="caller", kind="precondition")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.status.value == "verified" for item in results))

    def test_violated_precondition_has_counterexample(self):
        report = verify_source(
            SAFE_DIVIDE
            + "int caller(int x, int input) { "
            "safe_divide(x, input); return 0; }\n"
        )
        results = results_for(report, function="caller", kind="precondition")
        zero = next(item for item in results if item.counterexample.get("input") == 0)
        self.assertEqual(zero.status.value, "violated")

    def test_valid_postcondition(self):
        report = verify_source(
            "// cs: requires x < 2147483647\n"
            "// cs: ensures result > x\n"
            "int increment(int x) { return x + 1; }\n"
        )
        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "verified")

    def test_violated_postcondition_can_have_empty_sufficient_core(self):
        report = verify_source(
            "// cs: requires x > -2147483648\n"
            "// cs: ensures result >= x\n"
            "int decrement(int x) { return x - 1; }\n"
        )
        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "violated")
        self.assertEqual(result.counterexample, {})

    def test_unknown_is_never_promoted_to_verified(self):
        report = verify_source(
            "// cs: requires x >= y\n"
            "// cs: requires y >= z\n"
            "// cs: ensures result >= z\n"
            "int chain(int x, int y, int z) { return x; }\n"
        )
        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "unknown")

    def test_unsupported_loop_is_explicit(self):
        report = verify_source(
            "int f(int x) { while (x > 0) x = x - 1; return x; }\n"
        )
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("WhileStmt", report.results[0].message)

    def test_nonlinear_multiplication_is_explicit(self):
        report = verify_source("int square(int x) { return x * x; }\n")
        result = results_for(report, kind="unsupported_logic")[0]
        self.assertEqual(result.status.value, "unsupported")
        self.assertIn("nonlinear", result.message)

    def test_violated_assertion(self):
        report = verify_source(
            "void assert(bool);\n"
            "int f(int x) { assert(x >= 0); return x; }\n"
        )
        result = results_for(report, kind="assertion")[0]
        self.assertEqual(result.status.value, "violated")
        self.assertLess(result.counterexample["x"], 0)

    def test_valid_assertion_under_requirement(self):
        report = verify_source(
            "void assert(bool);\n"
            "// cs: requires x >= 0\n"
            "int f(int x) { assert(x >= 0); return x; }\n"
        )
        result = results_for(report, kind="assertion")[0]
        self.assertEqual(result.status.value, "verified")

    def test_division_safety_obligations_are_verified(self):
        report = verify_source(SAFE_DIVIDE)
        results = results_for(report, function="safe_divide")
        self.assertEqual(
            {item.kind for item in results},
            {"contract_consistency", "division_by_zero", "signed_overflow"},
        )
        self.assertTrue(all(item.status.value == "verified" for item in results))

    def test_nonzero_alone_misses_real_cpp_overflow_case(self):
        report = verify_source(
            "// cs: requires b != 0\n"
            "int divide(int a, int b) { return a / b; }\n"
        )
        overflow = results_for(report, kind="signed_overflow")[0]
        self.assertEqual(overflow.status.value, "violated")
        self.assertEqual(overflow.counterexample["a"], -2147483648)
        self.assertEqual(overflow.counterexample["b"], -1)

    def test_uncontracted_external_call_is_unsupported(self):
        report = verify_source(
            "int external(int x);\n"
            "int f(int x) { external(x); return 0; }\n"
        )
        result = results_for(report, function="f")[0]
        self.assertEqual(result.status.value, "unsupported")
        self.assertIn("external call", result.message)
