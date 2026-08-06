import json
import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.integer_types import I64
from semantic_verifier.pipeline import VerificationPipeline


def verify(source: str, backend: str = "both"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "int64.cpp"
    )


def results(report, kind: str):
    return [item for item in report.results if item.kind == kind]


class SignedInt64Tests(unittest.TestCase):
    def test_i64_boundaries_and_serialization_are_exact(self):
        report = verify(
            "// cs: requires x >= -9223372036854775807 - 1\n"
            "// cs: requires x <= 9223372036854775807\n"
            "// cs: ensures result == x\n"
            "long long identity(long long x) { return x; }\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        function = report.module.functions[0]
        self.assertEqual(function.return_type, "i64")
        self.assertEqual(function.parameters[0].type, "i64")
        payload = json.loads(report.to_json())
        constants = []

        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "constant" and value.get("type") == "i64":
                    constants.append(value["value"])
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(payload)
        self.assertIn(str(I64.minimum), constants)
        self.assertIn(str(I64.maximum), constants)
        self.assertTrue(all(isinstance(value, str) for value in constants))

    def test_i32_widens_to_i64_in_return_and_arithmetic(self):
        report = verify(
            "// cs: ensures result == x + 1\n"
            "long long widen(int x) { return x + 1LL; }\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        returned = report.module.functions[0].body[-1].expression
        self.assertEqual(returned.type, "i64")
        self.assertEqual(returned.args[0].kind, "cast")
        self.assertEqual(returned.args[0].args[0].type, "i32")

    def test_i64_narrows_to_i32_with_pinned_twos_complement_result(self):
        report = verify(
            "// cs: requires x == 4294967296\n"
            "// cs: ensures result == 0\n"
            "int narrow(long long x) { return x; }\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        returned = report.module.functions[0].body[-1].expression
        self.assertEqual((returned.kind, returned.type), ("cast", "i32"))
        self.assertEqual(returned.args[0].type, "i64")

    def test_safe_add_subtract_and_literal_multiply_verify(self):
        report = verify(
            "// cs: requires x == 3\n"
            "// cs: ensures result == 7\n"
            "long long arithmetic(long long x) {\n"
            "  long long a = x + 2LL;\n"
            "  long long b = a * 2LL;\n"
            "  return b - 3LL;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unknown"], 0)
        self.assertGreaterEqual(report.summary()["verified"], 5)

    def test_i64_addition_and_unary_negation_overflow_replay(self):
        addition = verify("long long add(long long x) { return x + 1LL; }\n")
        negation = verify("long long neg(long long x) { return -x; }\n")

        add_overflow = results(addition, "signed_overflow")[0]
        neg_overflow = results(negation, "signed_overflow")[0]
        self.assertEqual(add_overflow.status.value, "violated")
        self.assertEqual(add_overflow.counterexample, {"x": I64.maximum})
        self.assertEqual(neg_overflow.status.value, "violated")
        self.assertEqual(neg_overflow.counterexample, {"x": I64.minimum})
        serialized = json.loads(addition.to_json())
        self.assertEqual(
            serialized["results"][0]["counterexample"]["x"], str(I64.maximum)
        )

    def test_division_and_remainder_by_literals_follow_cxx_sign_rules(self):
        for operator, expected in (("/", -2), ("%", -1)):
            report = verify(
                f"// cs: ensures result == {expected}\n"
                f"long long calc() {{ return -7LL {operator} 3LL; }}\n"
            )
            self.assertEqual(report.summary()["solver_error"], 0)
            self.assertEqual(report.summary()["violated"], 0)
            self.assertGreaterEqual(report.summary()["verified"], 3)

    def test_variable_divisor_zero_and_min_overflow_never_verify(self):
        for operator in ("/", "%"):
            report = verify(
                f"long long calc(long long a, long long b) {{ return a {operator} b; }}\n"
            )
            by_zero = results(report, "division_by_zero")[0]
            overflow = results(report, "signed_overflow")[0]
            self.assertEqual(by_zero.status.value, "violated")
            self.assertEqual(by_zero.counterexample, {"b": 0})
            self.assertEqual(overflow.status.value, "violated")
            self.assertEqual(
                overflow.counterexample, {"a": I64.minimum, "b": -1}
            )

        logical = verify(
            "// cs: requires b != 0\n"
            "// cs: ensures result == a / b\n"
            "long long calc(long long a, long long b) { return a / b; }\n",
            backend="affine",
        )
        postcondition = results(logical, "postcondition")[0]
        self.assertEqual(postcondition.status.value, "unsupported")
        self.assertIn("outside", postcondition.message)

    def test_i64_contract_call_result_is_propagated(self):
        report = verify(
            "// cs: ensures result == x\n"
            "long long identity(long long x) { return x; }\n"
            "// cs: ensures result == x\n"
            "long long caller(long long x) {\n"
            "  long long y = identity(x);\n"
            "  return y;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        call = report.module.functions[1].body[0]
        self.assertEqual(call.result_type, "i64")

    def test_i64_loop_invariant_flow_verifies(self):
        report = verify(
            "// cs: requires n >= 0\n"
            "// cs: ensures result == n\n"
            "long long count(long long n) {\n"
            "  long long i = 0LL;\n"
            "  // cs: invariant i >= 0\n"
            "  // cs: invariant i <= n\n"
            "  while (i < n) { i = i + 1LL; }\n"
            "  return i;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unknown"], 0)
        self.assertGreaterEqual(report.summary()["verified"], 7)
        loop = report.module.functions[0].body[1]
        self.assertTrue(all(item.type == "i64" for item in loop.loop_variables))

    def test_long_extended_unsigned_and_unsigned_literal_fail_closed(self):
        sources = (
            "long f(long x) { return x; }\n",
            "__int128 f(__int128 x) { return x; }\n",
            "unsigned long long f(unsigned long long x) { return x; }\n",
            "long long f() { return 1ULL; }\n",
        )
        for source in sources:
            with self.subTest(source=source):
                report = verify(source)
                self.assertGreater(report.summary()["unsupported"], 0)
                self.assertEqual(report.summary()["verified"], 0)


if __name__ == "__main__":
    unittest.main()
