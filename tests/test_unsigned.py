import json
import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.cache import obligation_semantic_key
from semantic_verifier.integer_types import U32, U64, usual_arithmetic_type
from semantic_verifier.model import Expr, Obligation, SourceLocation
from semantic_verifier.pipeline import VerificationPipeline


def verify(source: str, backend: str = "z3"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "unsigned.cpp"
    )


def results(report, kind: str):
    return [item for item in report.results if item.kind == kind]


class UnsignedIntegerTests(unittest.TestCase):
    def test_u32_u64_lowering_and_serialization_are_exact(self):
        report = verify(
            "// cs: ensures result == x\n"
            "unsigned int id32(unsigned int x) { return x; }\n"
            "// cs: ensures result == 18446744073709551615\n"
            "unsigned long long max64() { return 18446744073709551615ULL; }\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        self.assertEqual(report.module.functions[0].return_type, "u32")
        self.assertEqual(report.module.functions[0].parameters[0].type, "u32")
        self.assertEqual(report.module.functions[1].return_type, "u64")
        payload = json.loads(report.to_json())
        constants = []

        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "constant" and value.get("type") == "u64":
                    constants.append(value["value"])
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(payload)
        self.assertIn(str(U64.maximum), constants)
        self.assertTrue(all(isinstance(value, str) for value in constants))

        for source in (
            "unsigned long f(unsigned long x) { return x; }\n",
            "unsigned short f(unsigned short x) { return x; }\n",
            "unsigned int f() { return 1UL; }\n",
        ):
            with self.subTest(source=source):
                rejected = verify(source)
                self.assertGreater(rejected.summary()["unsupported"], 0)
                self.assertEqual(rejected.summary()["verified"], 0)

    def test_unsigned_add_subtract_and_multiply_wrap_modulo_width(self):
        report = verify(
            "// cs: ensures result == 0\n"
            "unsigned int add_wrap() { return 4294967295u + 1u; }\n"
            "// cs: ensures result == -1\n"
            "unsigned int sub_wrap() { return 0u - 1u; }\n"
            "// cs: ensures result == 4294967294\n"
            "unsigned int mul_wrap() { return 4294967295u * 2u; }\n"
            "// cs: ensures result == 0\n"
            "unsigned long long add_wrap64() {\n"
            "  return 18446744073709551615ULL + 1ULL;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["verified"], 4)
        self.assertEqual(report.summary()["violated"], 0)
        self.assertFalse(results(report, "signed_overflow"))

    def test_usual_arithmetic_conversion_table_is_complete(self):
        expected = {
            "i32": ("i32", "u32", "i64", "u64"),
            "u32": ("u32", "u32", "i64", "u64"),
            "i64": ("i64", "i64", "i64", "u64"),
            "u64": ("u64", "u64", "u64", "u64"),
        }
        types = ("i32", "u32", "i64", "u64")
        for left in types:
            for right, result_type in zip(types, expected[left], strict=True):
                with self.subTest(left=left, right=right):
                    self.assertEqual(
                        usual_arithmetic_type(left, right), result_type
                    )

        source_types = {
            "i32": "int",
            "u32": "unsigned int",
            "i64": "long long",
            "u64": "unsigned long long",
        }
        functions = []
        result_types = []
        for left in types:
            for right, result_type in zip(types, expected[left], strict=True):
                functions.append(
                    f"{source_types[result_type]} f_{left}_{right}("
                    f"{source_types[left]} x, {source_types[right]} y) "
                    "{ return x + y; }"
                )
                result_types.append(result_type)
        report = verify("\n".join(functions) + "\n")
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(
            [function.body[-1].expression.type for function in report.module.functions],
            result_types,
        )

    def test_assignment_and_mixed_comparison_follow_cxx_conversions(self):
        report = verify(
            "// cs: requires x == -1\n"
            "// cs: ensures result == -1\n"
            "unsigned int from_signed(int x) {\n"
            "  unsigned int y = x;\n"
            "  return y;\n"
            "}\n"
            "// cs: requires x == -1\n"
            "// cs: requires y == 0\n"
            "// cs: ensures result == false\n"
            "bool mixed_less(int x, unsigned int y) { return x < y; }\n"
            "// cs: requires a == 2\n"
            "// cs: requires b == 3\n"
            "// cs: ensures result == 6\n"
            "long long mixed_product(unsigned int a, long long b) {\n"
            "  return a * b;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        assignment = report.module.functions[0].body[1].expression
        comparison = report.module.functions[1].body[-1].expression
        self.assertEqual((assignment.kind, assignment.type), ("cast", "u32"))
        self.assertEqual(assignment.args[0].type, "i32")
        self.assertEqual(comparison.args[0].type, "u32")
        self.assertEqual(comparison.args[0].kind, "cast")
        product = report.module.functions[2].body[-1].expression
        self.assertEqual(product.type, "i64")
        self.assertEqual(
            (product.args[0].kind, product.args[0].type), ("cast", "i64")
        )

        for operator in ("+", "-", "*"):
            with self.subTest(signed_overflow=operator):
                unsafe = verify(
                    "long long mixed(unsigned int x, long long y) { "
                    f"return x {operator} y; }}\n"
                )
                overflow = results(unsafe, "signed_overflow")[0]
                self.assertEqual(overflow.status.value, "violated")
                self.assertIn("replayed", overflow.message)

    def test_unsigned_division_remainder_and_zero_definedness(self):
        for operator in ("/", "%"):
            report = verify(
                "// cs: requires b != 0\n"
                f"// cs: ensures result == a {operator} b\n"
                "unsigned long long calc(unsigned long long a, "
                "unsigned long long b) {\n"
                f"  return a {operator} b;\n"
                "}\n"
            )
            self.assertEqual(report.summary()["verified"], 3)
            self.assertFalse(results(report, "signed_overflow"))

            unsafe = verify(
                "unsigned int calc(unsigned int a, unsigned int b) {\n"
                f"  return a {operator} b;\n"
                "}\n"
            )
            by_zero = results(unsafe, "division_by_zero")[0]
            self.assertEqual(by_zero.status.value, "violated")
            self.assertEqual(by_zero.counterexample, {"b": 0})

    def test_unsigned_contract_call_result_is_propagated(self):
        report = verify(
            "// cs: ensures result == x\n"
            "unsigned long long identity(unsigned long long x) { return x; }\n"
            "// cs: ensures result == x\n"
            "unsigned long long caller(unsigned long long x) {\n"
            "  unsigned long long y = identity(x);\n"
            "  return y;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["verified"], 2)
        call = report.module.functions[1].body[0]
        self.assertEqual(call.result_type, "u64")

    def test_unsigned_loop_invariant_flow_verifies(self):
        report = verify(
            "// cs: ensures result == n\n"
            "unsigned int count(unsigned int n) {\n"
            "  unsigned int i = 0u;\n"
            "  // cs: invariant i <= n\n"
            "  while (i < n) { i = i + 1u; }\n"
            "  return i;\n"
            "}\n"
        )

        self.assertEqual(report.summary()["verified"], 3)
        self.assertEqual(report.summary()["violated"], 0)
        loop = report.module.functions[0].body[1]
        self.assertTrue(all(item.type == "u32" for item in loop.loop_variables))

    def test_unsigned_violation_counterexample_replays_and_serializes(self):
        report = verify(
            "// cs: requires y == y\n"
            "// cs: ensures result >= x\n"
            "unsigned int increment(unsigned int x, unsigned int y) {\n"
            "  return x + 1u;\n"
            "}\n"
        )
        violation = results(report, "postcondition")[0]

        self.assertEqual(violation.status.value, "violated")
        self.assertEqual(violation.counterexample, {"x": U32.maximum})
        self.assertIn("minimized from 2 to 1 bindings", violation.message)
        serialized = json.loads(report.to_json())
        postcondition = next(
            item for item in serialized["results"] if item["kind"] == "postcondition"
        )
        self.assertEqual(postcondition["counterexample"]["x"], str(U32.maximum))

    def test_bv_obligations_require_explicit_z3_backend(self):
        source = (
            "// cs: ensures result == x + 1\n"
            "unsigned int increment(unsigned int x) { return x + 1u; }\n"
        )

        self.assertEqual(verify(source, "z3").summary()["verified"], 1)
        self.assertEqual(verify(source, "affine").summary()["unsupported"], 1)
        self.assertEqual(verify(source, "both").summary()["unsupported"], 1)

    def test_cache_keys_and_backend_identity_separate_logic_lanes(self):
        location = SourceLocation("cache.cpp", 1, 1)

        def item(type_name: str) -> Obligation:
            zero = Expr.integer(0, type_name)
            return Obligation(
                id="ob00001",
                function="f",
                kind="postcondition",
                assumptions=(),
                conclusion=Expr.binary(
                    "==", Expr.variable("x#0", type_name), zero
                ),
                location=location,
                description="cache lane",
            )

        backend = create_backend("z3")
        self.assertNotEqual(
            obligation_semantic_key(item("i32"), backend),
            obligation_semantic_key(item("u32"), backend),
        )
        self.assertEqual(
            backend.cache_identity()["query_policy"],
            "homogeneous-qf-lia-qf-bv-qf-array/v2",
        )


if __name__ == "__main__":
    unittest.main()
