import unittest

from semantic_verifier import verify_source
from semantic_verifier.checker import evaluate
from semantic_verifier.model import Expr


def results_for(report, *, kind):
    return [result for result in report.results if result.kind == kind]


class CheckerSoundnessTests(unittest.TestCase):
    def test_unsupported_division_cannot_be_simplified_away(self):
        report = verify_source(
            "// cs: ensures 0 * (1 / 0) == 0\n"
            "int f() { return 0; }\n"
        )

        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "unsupported")

    def test_nonlinear_contract_cannot_be_simplified_away(self):
        report = verify_source(
            "// cs: ensures 0 * (x * x) == 0\n"
            "int f(int x) { return 0; }\n"
        )

        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "unsupported")

    def test_large_affine_normalization_uses_exact_integer_ceiling(self):
        coefficient = 10**20
        report = verify_source(
            f"// cs: requires x >= 1\n"
            f"// cs: ensures {coefficient} * x >= {coefficient + 1}\n"
            "int f(int x) { return x; }\n"
        )

        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "violated")
        self.assertEqual(result.counterexample["x"], 1)

    def test_and_rhs_safety_is_guarded_by_left_operand(self):
        report = verify_source(
            "int f(int b) { "
            "if (b != 0 && 10 / b > 0) return 1; return 0; }\n"
        )

        result = results_for(report, kind="division_by_zero")[0]
        self.assertEqual(result.status.value, "verified")

    def test_or_rhs_safety_is_guarded_by_negated_left_operand(self):
        report = verify_source(
            "int f(int b) { "
            "if (b == 0 || 10 / b > 0) return 1; return 0; }\n"
        )

        result = results_for(report, kind="division_by_zero")[0]
        self.assertEqual(result.status.value, "verified")

    def test_evaluator_uses_short_circuit_semantics(self):
        undefined_rhs = Expr.binary(
            "==",
            Expr.binary("/", Expr.integer(1), Expr.integer(0), "int"),
            Expr.integer(0),
            "bool",
        )

        self.assertFalse(
            evaluate(Expr.binary("&&", Expr.boolean(False), undefined_rhs, "bool"), {})
        )
        self.assertTrue(
            evaluate(Expr.binary("||", Expr.boolean(True), undefined_rhs, "bool"), {})
        )

    def test_later_postcondition_is_checked_only_on_defined_paths(self):
        report = verify_source(
            "// cs: ensures result <= 2147483647\n"
            "int f(int x) { int y = x + 1; return y; }\n"
        )

        overflow = results_for(report, kind="signed_overflow")[0]
        postcondition = results_for(report, kind="postcondition")[0]
        self.assertEqual(overflow.status.value, "violated")
        self.assertEqual(postcondition.status.value, "verified")

    def test_counterexample_contains_eliminated_input_bindings(self):
        report = verify_source(
            "// cs: requires x == y\n"
            "// cs: ensures result > 0\n"
            "int f(int x, int y) { return x; }\n"
        )

        result = results_for(report, kind="postcondition")[0]
        self.assertEqual(result.status.value, "violated")
        self.assertIn("x", result.counterexample)
        self.assertIn("y", result.counterexample)
        self.assertEqual(result.counterexample["x"], result.counterexample["y"])
        self.assertLessEqual(result.counterexample["x"], 0)


if __name__ == "__main__":
    unittest.main()
