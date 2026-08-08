import unittest

from semantic_verifier.model import Expr, Obligation, SourceLocation
from semantic_verifier.smtlib import (
    SmtLibEmissionError,
    decode_symbol,
    emit_smtlib,
    encode_symbol,
)


LOCATION = SourceLocation("smt.cpp", 1, 1)


def obligation(
    *,
    assumptions=(),
    conclusion=None,
    mode="validity",
    unsupported_reason=None,
):
    return Obligation(
        id="ob00001",
        function="f",
        kind="postcondition",
        assumptions=tuple(assumptions),
        conclusion=conclusion,
        location=LOCATION,
        description="SMT test",
        unsupported_reason=unsupported_reason,
        mode=mode,
    )


class SmtLibEmitterTests(unittest.TestCase):
    def test_emits_validity_as_assumptions_and_negated_conclusion(self):
        x = Expr.variable("x#0")
        y = Expr.variable("y#0")
        item = obligation(
            assumptions=(Expr.binary(">=", x, Expr.integer(0)),),
            conclusion=Expr.binary(">=", Expr.binary("+", x, y), y),
        )

        self.assertEqual(
            emit_smtlib(item),
            "(set-logic QF_LIA)\n"
            "(declare-fun x_v0 () Int)\n"
            "(declare-fun y_v0 () Int)\n"
            "(assert (>= x_v0 0))\n"
            "(assert (not (>= (+ x_v0 y_v0) y_v0)))\n"
            "(check-sat)\n",
        )

    def test_emits_satisfiability_assumptions_directly(self):
        flag = Expr.variable("ready#0", "bool")
        item = obligation(
            assumptions=(
                flag,
                Expr.binary("!=", Expr.variable("x#0"), Expr.integer(-2)),
            ),
            mode="satisfiable",
        )

        self.assertEqual(
            emit_smtlib(item),
            "(set-logic QF_LIA)\n"
            "(declare-fun ready_v0 () Bool)\n"
            "(declare-fun x_v0 () Int)\n"
            "(assert ready_v0)\n"
            "(assert (distinct x_v0 (- 2)))\n"
            "(check-sat)\n",
        )

    def test_empty_satisfiability_query_asserts_true(self):
        self.assertEqual(
            emit_smtlib(obligation(mode="satisfiable")),
            "(set-logic QF_LIA)\n(assert true)\n(check-sat)\n",
        )

    def test_symbol_declarations_are_sorted_and_output_is_repeatable(self):
        item = obligation(
            assumptions=(
                Expr.variable("z#1", "bool"),
                Expr.variable("a#0", "bool"),
            ),
            conclusion=Expr.variable("m#2", "bool"),
        )

        first = emit_smtlib(item)
        self.assertEqual(first, emit_smtlib(item))
        self.assertLess(first.index("a_v0"), first.index("m_v2"))
        self.assertLess(first.index("m_v2"), first.index("z_v1"))

    def test_symbol_codec_is_reversible_and_collision_free(self):
        names = ("y#0", "y_v0", "y@2#0", "and", "9lives", "ç#12")
        encoded = tuple(encode_symbol(name) for name in names)

        self.assertEqual(encoded[0], "y_v0")
        self.assertEqual(len(set(encoded)), len(encoded))
        self.assertEqual(tuple(decode_symbol(name) for name in encoded), names)

    def test_emits_all_supported_boolean_and_linear_operators(self):
        x = Expr.variable("x#0")
        flag = Expr.variable("flag#0", "bool")
        arithmetic = Expr.binary(
            "==",
            Expr.binary("*", Expr.integer(3), Expr.unary("-", x)),
            Expr.binary("-", x, Expr.integer(1)),
        )
        conclusion = Expr.binary(
            "||",
            Expr.unary("!", flag),
            Expr.binary("&&", flag, arithmetic),
        )

        text = emit_smtlib(obligation(conclusion=conclusion))

        self.assertIn(
            "(assert (not (or (not flag_v0) "
            "(and flag_v0 (= (* 3 (- x_v0)) (- x_v0 1))))))",
            text,
        )

    def test_rejects_nonlinear_arithmetic(self):
        x = Expr.variable("x#0")
        y = Expr.variable("y#0")

        with self.assertRaisesRegex(SmtLibEmissionError, "outside QF_LIA"):
            emit_smtlib(
                obligation(
                    conclusion=Expr.binary(
                        "==", Expr.binary("*", x, y), Expr.integer(0)
                    )
                )
            )

    def test_emits_cxx_division_and_rejects_unsupported_obligations(self):
        division = Expr.binary(
            "==",
            Expr.binary("/", Expr.integer(4), Expr.integer(2)),
            Expr.integer(2),
        )
        query = emit_smtlib(obligation(conclusion=division))
        self.assertIn("(div ", query)
        self.assertIn("(ite ", query)
        with self.assertRaisesRegex(SmtLibEmissionError, "literal divisor"):
            emit_smtlib(
                obligation(
                    conclusion=Expr.binary(
                        "==",
                        Expr.binary(
                            "/", Expr.variable("x#0"), Expr.variable("y#0")
                        ),
                        Expr.integer(0),
                    )
                )
            )
        with self.assertRaisesRegex(SmtLibEmissionError, "non-zero"):
            emit_smtlib(
                obligation(
                    conclusion=Expr.binary(
                        "==",
                        Expr.binary("%", Expr.variable("x#0"), Expr.integer(0)),
                        Expr.integer(0),
                    )
                )
            )
        with self.assertRaisesRegex(SmtLibEmissionError, "unsupported obligation"):
            emit_smtlib(
                obligation(
                    conclusion=Expr.boolean(True),
                    unsupported_reason="source construct",
                )
            )

    def test_rejects_malformed_types_and_non_query_modes(self):
        malformed = Expr.binary(">", Expr.boolean(True), Expr.integer(0))
        with self.assertRaisesRegex(SmtLibEmissionError, "operand"):
            emit_smtlib(obligation(conclusion=malformed))
        with self.assertRaisesRegex(SmtLibEmissionError, "not an SMT query"):
            emit_smtlib(
                obligation(conclusion=Expr.boolean(True), mode="well_formed")
            )


if __name__ == "__main__":
    unittest.main()
