from pathlib import Path
import tempfile
import unittest

from semantic_verifier.array_types import (
    MAX_ARRAY_ELEMENTS,
    ArrayType,
    array_type,
    is_array_type,
    parse_source_array_type,
)
from semantic_verifier.backend import CheckerBackend, create_backend
from semantic_verifier.cache import CachedCheckerBackend
from semantic_verifier.contracts import ContractExpressionParser
from semantic_verifier.model import (
    Expr,
    Obligation,
    SourceLocation,
    VerificationResult,
    VerificationStatus,
)
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.query_fragment import QueryFragment, classify_obligation
from semantic_verifier.smtlib import emit_smtlib
from semantic_verifier.z3_backend import parse_z3_model


def verify(source: str, backend: str = "z3"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "arrays.cpp"
    )


def obligation(assumptions: tuple[Expr, ...], conclusion: Expr) -> Obligation:
    return Obligation(
        "ob1",
        "f",
        "assertion",
        assumptions,
        conclusion,
        SourceLocation("arrays.cpp", 1, 1),
        "array test",
    )


class ArrayCounterexampleBackend(CheckerBackend):
    name = "array-counterexample"

    def __init__(self):
        self.calls = 0

    def check(self, item):
        self.calls += 1
        return VerificationResult(
            item.id,
            item.function,
            item.kind,
            VerificationStatus.VIOLATED,
            item.location,
            "violated: replayed array",
            {"a#0": (1, 2)},
        )


class ArrayTypeTests(unittest.TestCase):
    def test_owned_type_identity_is_canonical_and_bounded(self):
        profile = ArrayType("i32", 3)
        self.assertEqual(profile.name, "array<i32,3>")
        self.assertEqual(array_type(profile.name), profile)
        self.assertTrue(is_array_type(profile.name))
        self.assertFalse(is_array_type("int[3]"))
        with self.assertRaises(ValueError):
            ArrayType("bool", 3)
        with self.assertRaises(ValueError):
            ArrayType("i32", MAX_ARRAY_ELEMENTS + 1)

    def test_source_type_parser_rejects_unreviewed_shapes(self):
        source_types = {"int": "i32", "unsigned int": "u32"}
        self.assertIsNone(parse_source_array_type("int", source_types))
        self.assertEqual(
            parse_source_array_type("unsigned int[2]", source_types),
            ArrayType("u32", 2),
        )
        for rejected in ("int[2][3]", "bool[2]", "int[]"):
            with self.subTest(rejected=rejected), self.assertRaises(ValueError):
                parse_source_array_type(rejected, source_types)


class ArrayPipelineTests(unittest.TestCase):
    def test_constant_and_symbolic_reads_verify_with_bounds(self):
        report = verify(
            """
// cs: ensures return == 7
int constant_read() { int a[3] = {4, 7, 9}; return a[1]; }
// cs: requires i >= 0 && i < 3
// cs: ensures return > 0
int symbolic_read(int i) { int a[3] = {4, 7, 9}; return a[i]; }
"""
        )
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(
            [item.status for item in report.results if item.kind == "array_bounds"],
            [VerificationStatus.VERIFIED, VerificationStatus.VERIFIED],
        )

    def test_writes_are_whole_array_ssa_and_preserve_other_elements(self):
        report = verify(
            """
// cs: ensures return == 2
int f(bool choose) {
  int a[3] = {1, 2, 3};
  if (choose) a[0] = 9;
  a[2] = 8;
  return a[1];
}
"""
        )
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(report.summary()["violated"], 0)
        text = report.module.functions[0].body
        self.assertTrue(any(node.expression and node.expression.kind == "store" for node in text))

    def test_feasible_out_of_bounds_access_is_violated_and_replayed(self):
        report = verify("int f(int i) { int a[2] = {1, 2}; return a[i]; }\n")
        bounds = [item for item in report.results if item.kind == "array_bounds"]
        self.assertEqual(len(bounds), 1)
        self.assertEqual(bounds[0].status, VerificationStatus.VIOLATED)
        self.assertIn("replayed successfully", bounds[0].message)
        self.assertIn("i", bounds[0].counterexample or {})

    def test_constant_out_of_bounds_access_is_violated(self):
        report = verify("int f() { int a[2] = {1, 2}; return a[2]; }\n")
        bounds = [item for item in report.results if item.kind == "array_bounds"]
        self.assertEqual([item.status for item in bounds], [VerificationStatus.VIOLATED])

    def test_contract_parser_supports_owned_array_indexing(self):
        parsed = ContractExpressionParser(
            "a[i] == 7", {"a": "array<i32,3>", "i": "i32"}
        ).parse()
        self.assertEqual(parsed.args[0].kind, "select")
        self.assertEqual(parsed.args[0].type, "i32")

        report = verify(
            """
// cs: requires i >= 0 && i < 2
// cs: ensures return > 0
int f(int i) {
  int a[2] = {1, 2};
  // cs: invariant i >= 0 && i < 2 && a[i] > 0
  while (false) { }
  return a[i];
}
"""
        )
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(
            len([item for item in report.results if item.kind == "array_bounds"]),
            5,
        )

    def test_unreviewed_array_constructs_fail_closed(self):
        rejected = (
            "int f(int a[2]) { return a[0]; }",
            "int f() { int a[2] = {1,2}; int *p = a; return p[0]; }",
            "int f() { int *a = new int[2]; return 0; }",
            "int f() { int a[2][2] = {{1,2},{3,4}}; return 0; }",
            "int f() { int a[2] = {1}; return a[0]; }",
            "int f() { int a[2]; return 0; }",
            "int f() { int a[65] = {}; return 0; }",
        )
        for source in rejected:
            with self.subTest(source=source):
                report = verify(source)
                self.assertGreater(report.summary()["unsupported"], 0)
                self.assertEqual(report.summary()["verified"], 0)

    def test_backend_policy_keeps_arrays_on_explicit_z3(self):
        source = "// cs: ensures return == 2\nint f(){int a[2]={1,2};return a[1];}\n"
        self.assertEqual(verify(source, "z3").summary()["unsupported"], 0)
        self.assertGreater(verify(source, "affine").summary()["unsupported"], 0)
        self.assertGreater(verify(source, "both").summary()["unsupported"], 0)

    def test_report_serialization_is_deterministic(self):
        source = "int f(int i){int a[2]={1,2};return a[i];}\n"
        self.assertEqual(verify(source).to_json(), verify(source).to_json())


class ArraySmtTests(unittest.TestCase):
    def test_signed_and_unsigned_arrays_use_homogeneous_array_logics(self):
        index = Expr.variable("i#0", "i32")
        signed = Expr.variable("a#0", "array<i32,3>")
        signed_obligation = obligation(
            (), Expr.binary("==", Expr.select(signed, index), Expr.integer(1), "bool")
        )
        self.assertEqual(classify_obligation(signed_obligation), QueryFragment.QF_ARRAY)
        signed_query = emit_smtlib(signed_obligation)
        self.assertIn("(set-logic QF_ALIA)", signed_query)
        self.assertIn("(Array Int Int)", signed_query)

        unsigned = Expr.array(
            (Expr.integer(1, "u32"), Expr.integer(2, "u32")), "u32"
        )
        unsigned_obligation = obligation(
            (),
            Expr.binary(
                "==",
                Expr.select(unsigned, Expr.variable("u#0", "u32")),
                Expr.integer(2, "u32"),
                "bool",
            ),
        )
        unsigned_query = emit_smtlib(unsigned_obligation)
        self.assertIn("(set-logic QF_ABV)", unsigned_query)
        self.assertNotIn(" Int", unsigned_query)
        self.assertEqual(unsigned_query, emit_smtlib(unsigned_obligation))

    def test_array_counterexample_evidence_round_trips_through_cache(self):
        array = Expr.variable("a#0", "array<i32,2>")
        item = obligation(
            (),
            Expr.binary(
                "==", Expr.select(array, Expr.integer(0)), Expr.integer(0), "bool"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = ArrayCounterexampleBackend()
            cached = CachedCheckerBackend(backend, Path(directory) / "cache.json")
            first = cached.check(item)
            second = cached.check(item)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(first.counterexample, {"a#0": (1, 2)})
        self.assertEqual(second.counterexample, first.counterexample)
        self.assertEqual(first.to_dict()["counterexample"], {"a#0": ["1", "2"]})

    def test_z3_const_store_models_materialize_owned_arrays(self):
        signed = parse_z3_model(
            "sat\n(model (define-fun a_v0 () (Array Int Int) "
            "(store ((as const (Array Int Int)) 0) 1 7)))\n",
            {"a#0": "array<i32,3>"},
        )
        self.assertEqual(signed, {"a#0": (0, 7, 0)})
        unsigned = parse_z3_model(
            "sat\n(model (define-fun a_v0 () "
            "(Array (_ BitVec 64) (_ BitVec 32)) "
            "(store ((as const (Array (_ BitVec 64) (_ BitVec 32))) "
            "(_ bv0 32)) (_ bv1 64) (_ bv4294967295 32))))\n",
            {"a#0": "array<u32,2>"},
        )
        self.assertEqual(unsigned, {"a#0": (0, 2**32 - 1)})


if __name__ == "__main__":
    unittest.main()
