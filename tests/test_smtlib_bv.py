import unittest

from semantic_verifier.model import Expr, Obligation, SourceLocation
from semantic_verifier.query_fragment import QueryFragment, classify_obligation
from semantic_verifier.smtlib import SmtLibEmissionError, emit_smtlib
from semantic_verifier.z3_backend import Z3ModelError, parse_z3_model


LOCATION = SourceLocation("bv.cpp", 1, 1)


def obligation(conclusion: Expr, assumptions: tuple[Expr, ...] = ()) -> Obligation:
    return Obligation(
        id="ob00001",
        function="f",
        kind="postcondition",
        assumptions=assumptions,
        conclusion=conclusion,
        location=LOCATION,
        description="BV test",
    )


class BitVectorSmtLibTests(unittest.TestCase):
    def test_classifier_selects_bv_for_any_unsigned_taint(self):
        signed = obligation(
            Expr.binary("==", Expr.variable("x#0", "i32"), Expr.integer(0))
        )
        unsigned = obligation(
            Expr.binary(
                "==", Expr.variable("x#0", "u32"), Expr.integer(0, "u32")
            )
        )

        self.assertEqual(classify_obligation(signed), QueryFragment.QF_LIA)
        self.assertEqual(classify_obligation(unsigned), QueryFragment.QF_BV)

    def test_bv_query_is_homogeneous_and_deterministic(self):
        x = Expr.variable("x#0", "u32")
        conclusion = Expr.binary(
            "==",
            Expr.binary("+", x, Expr.integer(1, "u32"), "u32"),
            Expr.integer(0, "u32"),
        )
        item = obligation(conclusion)
        first = emit_smtlib(item)

        self.assertEqual(first, emit_smtlib(item))
        self.assertIn("(set-logic QF_BV)", first)
        self.assertIn("(declare-fun x_v0 () (_ BitVec 32))", first)
        self.assertIn("(bvadd x_v0 (_ bv1 32))", first)
        self.assertNotIn(" Int", first)
        self.assertNotIn("QF_LIA", first)

    def test_bv_casts_use_extension_and_truncation(self):
        signed32 = Expr.variable("s#0", "i32")
        unsigned32 = Expr.variable("u#0", "u32")
        unsigned64 = Expr.variable("wide#0", "u64")
        checks = (
            Expr.binary(
                "==", Expr.cast(signed32, "u64"), Expr.cast(signed32, "u64")
            ),
            Expr.binary(
                "==", Expr.cast(unsigned32, "u64"), Expr.cast(unsigned32, "u64")
            ),
            Expr.binary(
                "==", Expr.cast(unsigned64, "i32"), Expr.cast(unsigned64, "i32")
            ),
        )
        conclusion = Expr.binary(
            "&&", checks[0], Expr.binary("&&", checks[1], checks[2], "bool"), "bool"
        )
        query = emit_smtlib(obligation(conclusion))

        self.assertIn("((_ sign_extend 32) s_v0)", query)
        self.assertIn("((_ zero_extend 32) u_v0)", query)
        self.assertIn("((_ extract 31 0) wide_v0)", query)

    def test_bv_comparisons_and_arithmetic_respect_signedness(self):
        signed_left = Expr.variable("s#0", "i32")
        signed_right = Expr.variable("t#0", "i32")
        unsigned_left = Expr.variable("u#0", "u32")
        unsigned_right = Expr.variable("v#0", "u32")
        signed_check = Expr.binary("<", signed_left, signed_right)
        unsigned_product = Expr.binary(
            "*", unsigned_left, unsigned_right, "u32"
        )
        unsigned_check = Expr.binary(
            "<",
            Expr.binary("/", unsigned_product, unsigned_right, "u32"),
            Expr.binary("%", unsigned_left, unsigned_right, "u32"),
        )
        query = emit_smtlib(
            obligation(Expr.binary("&&", signed_check, unsigned_check, "bool"))
        )

        self.assertIn("bvslt", query)
        self.assertIn("bvult", query)
        self.assertIn("bvmul", query)
        self.assertIn("bvudiv", query)
        self.assertIn("bvurem", query)
        self.assertNotIn(" Int", query)

        mixed_product = Expr.binary(
            "*",
            Expr.cast(unsigned_left, "i64"),
            Expr.variable("w#0", "i64"),
            "i64",
        )
        overflow_query = emit_smtlib(
            obligation(Expr.predicate("signed_no_overflow", mixed_product))
        )
        self.assertIn("((_ sign_extend 64)", overflow_query)
        self.assertIn("(bvmul", overflow_query)
        self.assertNotIn(" Int", overflow_query)

    def test_bv_literal_zero_divisor_fails_closed(self):
        expression = Expr.binary(
            "/", Expr.variable("x#0", "u32"), Expr.integer(0, "u32"), "u32"
        )
        with self.assertRaisesRegex(SmtLibEmissionError, "non-zero"):
            emit_smtlib(
                obligation(Expr.binary("==", expression, Expr.integer(0, "u32")))
            )

    def test_bitvector_models_decode_to_source_signedness(self):
        output = (
            "sat\n(\n"
            "  (define-fun signed_v0 () (_ BitVec 32) #xffffffff)\n"
            "  (define-fun unsigned_v0 () (_ BitVec 64) #xffffffffffffffff)\n"
            ")\n"
        )

        self.assertEqual(
            parse_z3_model(output, {"signed#0": "i32", "unsigned#0": "u64"}),
            {"signed#0": -1, "unsigned#0": 18446744073709551615},
        )

    def test_bitvector_model_sort_mismatch_fails_closed(self):
        output = "sat\n((define-fun x_v0 () Int 0))\n"
        with self.assertRaisesRegex(Z3ModelError, "sort mismatch"):
            parse_z3_model(output, {"x#0": "u32"})

        mixed = (
            "sat\n(\n"
            "  (define-fun x_v0 () Int 0)\n"
            "  (define-fun y_v0 () (_ BitVec 32) #x00000000)\n"
            ")\n"
        )
        with self.assertRaisesRegex(Z3ModelError, "mixes Int and BitVec"):
            parse_z3_model(mixed, {"x#0": "i32", "y#0": "u32"})


if __name__ == "__main__":
    unittest.main()
