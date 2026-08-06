import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.contracts import ContractExpressionParser
from semantic_verifier.model import Expr, Obligation, SourceLocation
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.query_fragment import QueryFragment, classify_obligation
from semantic_verifier.smtlib import emit_smtlib


LOCATION = SourceLocation("bitwise.cpp", 1, 1)


def verify(source: str, backend: str = "z3"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "bitwise.cpp"
    )


def results(report, kind: str):
    return [item for item in report.results if item.kind == kind]


def obligation(conclusion: Expr) -> Obligation:
    return Obligation(
        id="ob00001",
        function="f",
        kind="postcondition",
        assumptions=(),
        conclusion=conclusion,
        location=LOCATION,
        description="bitwise test",
    )


class BitwiseAndShiftTests(unittest.TestCase):
    def test_contract_precedence_and_bool_promotion_are_exact(self):
        expression = ContractExpressionParser(
            "result == ((a & b) | (c ^ ~d))",
            {name: "i32" for name in ("result", "a", "b", "c", "d")},
        ).parse()
        value = expression.args[1]

        self.assertEqual(value.op, "|")
        self.assertEqual(value.args[0].op, "&")
        self.assertEqual(value.args[1].op, "^")
        self.assertEqual(value.args[1].args[1].op, "~")

        shifted = ContractExpressionParser(
            "flag << 1 + 2 < limit",
            {"flag": "bool", "limit": "i32"},
        ).parse()
        self.assertEqual(shifted.op, "<")
        self.assertEqual(shifted.args[0].op, "<<")
        self.assertEqual(shifted.args[0].args[0].kind, "cast")
        self.assertEqual(shifted.args[0].args[1].op, "+")

    def test_masks_negative_patterns_and_de_morgan_verify(self):
        report = verify(
            "// cs: ensures result == (~x & 255)\n"
            "int low_byte(int x) { return ~x & 255; }\n"
            "// cs: ensures result == true\n"
            "bool de_morgan(unsigned int x, unsigned int y) {\n"
            "  return ~(x & y) == (~x | ~y);\n"
            "}\n"
            "// cs: ensures result == 18446744073709551615\n"
            "unsigned long long all_bits() { return ~0ULL; }\n"
            "// cs: ensures result == ~flag\n"
            "int promoted_bool(bool flag) { return ~flag; }\n"
        )

        self.assertEqual(report.summary()["verified"], 4)
        self.assertEqual(sum(report.summary().values()), 4)

    def test_mixed_signedness_uses_usual_conversions(self):
        report = verify(
            "// cs: ensures result == (x ^ y)\n"
            "unsigned long long mix(int x, unsigned long long y) {\n"
            "  return x ^ y;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["verified"], 1)
        expression = report.module.functions[0].body[-1].expression
        self.assertEqual(expression.type, "u64")
        self.assertEqual((expression.args[0].kind, expression.args[0].type), ("cast", "u64"))

    def test_32_and_64_bit_shifts_and_pinned_right_shift_verify(self):
        report = verify(
            "// cs: ensures result == -2\n"
            "int arithmetic_right() { return -8 >> 2; }\n"
            "// cs: ensures result == 1\n"
            "unsigned int logical_right() { return 2147483648u >> 31; }\n"
            "// cs: ensures result == 9223372036854775808\n"
            "unsigned long long high_bit() { return 1ULL << 63; }\n"
            "// cs: ensures result == -2147483648\n"
            "int signed_boundary() { return 1 << 31; }\n"
        )

        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(report.summary()["unknown"], 0)
        self.assertGreaterEqual(report.summary()["verified"], 8)

    def test_negative_and_width_exceeding_shift_counts_are_violations(self):
        cases = (
            "int f(int x) { return x >> -1; }\n",
            "unsigned int f(unsigned int x) { return x << 32; }\n",
            "unsigned long long f(unsigned long long x) { return x >> 64; }\n",
        )
        for source in cases:
            with self.subTest(source=source):
                report = verify(source)
                count = results(report, "shift_count")[0]
                self.assertEqual(count.status.value, "violated")
                self.assertIn("replayed", count.message)

    def test_invalid_signed_left_shift_values_are_violations(self):
        for expression in ("-1 << 1", "2 << 31"):
            with self.subTest(expression=expression):
                report = verify(f"int f() {{ return {expression}; }}\n")
                safety = results(report, "signed_left_shift")[0]
                self.assertEqual(safety.status.value, "violated")
                self.assertIn("replayed", safety.message)

    def test_shift_violation_counterexample_replays_and_minimizes(self):
        report = verify(
            "// cs: requires n == 1\n"
            "// cs: ensures result == x\n"
            "unsigned int shifted(unsigned int x, unsigned int n) {\n"
            "  return x << n;\n"
            "}\n"
        )
        violation = results(report, "postcondition")[0]

        self.assertEqual(violation.status.value, "violated")
        self.assertIn("replayed", violation.message)
        self.assertIn("x", violation.counterexample)

    def test_signed_only_bitwise_formula_selects_bv_and_requires_z3(self):
        source = (
            "// cs: ensures result == (x & 255)\n"
            "int mask(int x) { return x & 255; }\n"
        )
        expression = Expr.binary(
            "==",
            Expr.unary("~", Expr.variable("x#0", "i32"), "i32"),
            Expr.integer(-1, "i32"),
        )

        self.assertEqual(classify_obligation(obligation(expression)), QueryFragment.QF_BV)
        self.assertGreater(verify(source, "z3").summary()["verified"], 0)
        self.assertGreater(verify(source, "affine").summary()["unsupported"], 0)
        self.assertGreater(verify(source, "both").summary()["unsupported"], 0)

    def test_smtlib_uses_exact_bitwise_and_shift_operators(self):
        signed = Expr.variable("s#0", "i64")
        unsigned = Expr.variable("u#0", "u64")
        count = Expr.variable("n#0", "u32")
        bitwise = Expr.binary(
            "^",
            Expr.binary("&", signed, Expr.unary("~", signed, "i64"), "i64"),
            Expr.binary("|", signed, signed, "i64"),
            "i64",
        )
        shifts = Expr.binary(
            "==",
            Expr.binary(">>", bitwise, count, "i64"),
            Expr.cast(Expr.binary("<<", unsigned, count, "u64"), "i64"),
        )
        query = emit_smtlib(obligation(shifts))

        self.assertEqual(query, emit_smtlib(obligation(shifts)))
        for operator in ("bvnot", "bvand", "bvor", "bvxor", "bvashr", "bvshl"):
            self.assertIn(operator, query)
        self.assertNotIn(" Int", query)

    def test_compound_rotate_and_builtin_operations_fail_closed(self):
        sources = (
            "unsigned int f(unsigned int x, unsigned int y) { x &= y; return x; }\n",
            "unsigned int f(unsigned int x) { return __builtin_rotateleft32(x, 1); }\n",
            "int f(unsigned int x) { return __builtin_popcount(x); }\n",
        )
        for source in sources:
            with self.subTest(source=source):
                report = verify(source)
                self.assertGreater(report.summary()["unsupported"], 0)
                self.assertEqual(report.summary()["verified"], 0)


if __name__ == "__main__":
    unittest.main()
