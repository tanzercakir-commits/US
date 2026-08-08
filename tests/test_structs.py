import json
from pathlib import Path
import tempfile
import unittest

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
from semantic_verifier.record_types import (
    MAX_RECORD_DEPTH,
    RecordField,
    RecordType,
    RecordValue,
    make_record_type,
    record_constructor_symbol,
    record_sort_symbol,
    record_type,
)
from semantic_verifier.smtlib import emit_smtlib
from semantic_verifier.z3_backend import parse_z3_model


def verify(source: str, backend: str = "z3"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "structs.cpp"
    )


def obligation(conclusion: Expr) -> Obligation:
    return Obligation(
        "ob1",
        "f",
        "assertion",
        (),
        conclusion,
        SourceLocation("structs.cpp", 1, 1),
        "record test",
    )


class RecordCounterexampleBackend(CheckerBackend):
    name = "record-counterexample"

    def __init__(self, type_name: str):
        self.type_name = type_name
        self.calls = 0

    def check(self, item):
        self.calls += 1
        return VerificationResult(
            item.id,
            item.function,
            item.kind,
            VerificationStatus.VIOLATED,
            item.location,
            "violated: replayed record",
            {"p#0": RecordValue(self.type_name, (1, 2))},
        )


class RecordTypeTests(unittest.TestCase):
    def test_type_identity_is_canonical_bounded_and_recursive(self):
        pair = make_record_type("Pair", (("x", "i32"), ("ready", "bool")))
        box = make_record_type("Box", (("pair", pair), ("values", "array<i32,2>")))
        self.assertEqual(record_type(pair).source_name, "Pair")
        self.assertEqual(record_type(box).field("pair").type, pair)
        self.assertEqual(record_type(box).depth, 2)
        with self.assertRaises(ValueError):
            RecordType("Empty", ())
        with self.assertRaises(ValueError):
            RecordType("Duplicate", (RecordField("x", "i32"), RecordField("x", "i32")))
        with self.assertRaises(ValueError):
            RecordValue(pair, (2**31, False))
        with self.assertRaises(ValueError):
            RecordValue(pair, (1, 0))

    def test_nesting_depth_is_fail_closed(self):
        type_name = make_record_type("Level1", (("value", "i32"),))
        for depth in range(2, MAX_RECORD_DEPTH + 1):
            type_name = make_record_type(f"Level{depth}", (("next", type_name),))
        self.assertEqual(record_type(type_name).depth, MAX_RECORD_DEPTH)
        with self.assertRaises(ValueError):
            make_record_type("TooDeep", (("next", type_name),))


class RecordPipelineTests(unittest.TestCase):
    def test_construction_copy_and_field_isolation_are_exact(self):
        report = verify(
            """
struct Pair { int x; int y; };
// cs: requires input.x < 2147483647
// cs: ensures return == input.y
int f(Pair input) {
  Pair copy = input;
  copy.x = copy.x + 1;
  return input.y;
}
"""
        )
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        assignment = next(
            node
            for node in report.module.functions[0].body
            if node.kind == "assign" and node.expression.kind == "update"
        )
        self.assertEqual(assignment.expression.value, "x")
        self.assertEqual(report.module.records[0].source_name, "Pair")

    def test_nested_record_array_update_and_bounds_verify(self):
        report = verify(
            """
struct Pair { int x; int y; };
struct Box { Pair pair; int values[2]; };
// cs: requires i >= 0 && i < 2
// cs: ensures return == replacement
int f(Box box, int i, int replacement) {
  box.pair.x = replacement;
  box.values[i] = box.pair.x;
  return box.values[i];
}
"""
        )
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(
            [item.status for item in report.results if item.kind == "array_bounds"],
            [VerificationStatus.VERIFIED, VerificationStatus.VERIFIED],
        )

    def test_branch_merge_preserves_unmodified_fields(self):
        report = verify(
            """
struct Pair { int x; int y; };
// cs: ensures return.y == input.y
Pair choose(Pair input, bool flag) {
  Pair output = input;
  if (flag) output.x = 1; else output.x = 2;
  return output;
}
"""
        )
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        branch = next(
            node for node in report.module.functions[0].body if node.kind == "branch"
        )
        self.assertEqual(branch.merges[0].incoming_true.type, report.module.records[0].name)

    def test_calls_pass_and_return_records_by_value(self):
        report = verify(
            """
struct Pair { int x; int y; };
// cs: ensures return.x == input.x && return.y == input.y
Pair identity(Pair input) { return input; }
// cs: ensures return.x == input.x && return.y == input.y
Pair caller(Pair input) { Pair result = identity(input); return result; }
"""
        )
        self.assertEqual(report.summary()["verified"], 2)
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)

    def test_loop_havoc_preserves_record_invariant_fields(self):
        report = verify(
            """
struct Pair { int x; int y; };
// cs: requires n >= 0
// cs: ensures return.y == input.y
Pair loop(Pair input, int n) {
  Pair output = input;
  // cs: invariant n >= 0 && output.y == input.y
  while (n > 0) { output.x = 0; n = n - 1; }
  return output;
}
"""
        )
        self.assertEqual(report.summary()["verified"], 5)
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)

    def test_unsigned_record_countermodel_uses_bitvector_replay(self):
        report = verify(
            """
struct Word { unsigned int value; };
// cs: ensures return.value == 0
Word bad(Word input) { return input; }
"""
        )
        result = report.results[0]
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        value = (result.counterexample or {})["input"]
        self.assertEqual(value.fields, (2**32 - 1,))
        self.assertIn("replayed successfully", result.message)
    def test_contract_projection_and_replayed_counterexample_are_exact(self):
        pair = make_record_type("Pair", (("x", "i32"), ("y", "i32")))
        parsed = ContractExpressionParser("p.x == p.y", {"p": pair}).parse()
        self.assertEqual(parsed.args[0].kind, "project")

        report = verify(
            """
struct Pair { int x; int y; };
// cs: ensures return.x == input.x
Pair bad(Pair input) { input.x = 0; return input; }
"""
        )
        result = report.results[0]
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        self.assertIsInstance((result.counterexample or {})["input"], RecordValue)
        public = result.to_dict()["counterexample"]["input"]
        self.assertEqual(set(public), {"x", "y"})
        self.assertTrue(all(isinstance(value, str) for value in public.values()))

    def test_unreviewed_record_constructs_fail_closed(self):
        too_many = " ".join(f"int f{i};" for i in range(17))
        rejected = (
            "union U { int x; int y; }; int f() { return 0; }",
            "class C { public: int x; }; int f() { return 0; }",
            "struct S { int x : 3; }; int f() { return 0; }",
            "struct S { int *p; }; int f() { return 0; }",
            "struct S { int &r; }; int f() { return 0; }",
            "struct S { int x = 1; }; int f() { return 0; }",
            "struct S { int x; int get() { return x; } }; int f() { return 0; }",
            "struct B { int x; }; struct D : B { int y; }; int f() { return 0; }",
            "struct S { int x; int y; }; int f() { S s = {1}; return 0; }",
            "struct S { int x; }; int f() { S s; return 0; }",
            f"struct Wide {{ {too_many} }}; int f() {{ return 0; }}",
        )
        for source in rejected:
            with self.subTest(source=source):
                report = verify(source)
                self.assertGreater(report.summary()["unsupported"], 0)
                self.assertEqual(report.summary()["verified"], 0)

    def test_backend_policy_and_serialization_are_deterministic(self):
        source = (
            "struct Pair { int x; int y; };\n"
            "// cs: ensures return.x == input.x\n"
            "Pair f(Pair input) { return input; }\n"
        )
        first = verify(source)
        self.assertEqual(first.to_json(), verify(source).to_json())
        self.assertEqual(first.summary()["unsupported"], 0)
        self.assertGreater(verify(source, "affine").summary()["unsupported"], 0)
        self.assertGreater(verify(source, "both").summary()["unsupported"], 0)


class RecordSmtAndEvidenceTests(unittest.TestCase):
    def test_record_queries_select_int_or_bv_sublanes(self):
        signed_type = make_record_type("Signed", (("value", "i32"),))
        signed = Expr.variable("s#0", signed_type)
        signed_item = obligation(
            Expr.binary("==", Expr.project(signed, "value"), Expr.integer(1))
        )
        self.assertEqual(classify_obligation(signed_item), QueryFragment.QF_RECORD)
        signed_query = emit_smtlib(signed_item)
        self.assertIn("(set-logic ALL)", signed_query)
        self.assertIn("_value Int)", signed_query)

        unsigned_type = make_record_type("Unsigned", (("value", "u32"),))
        unsigned = Expr.variable("u#0", unsigned_type)
        unsigned_item = obligation(
            Expr.binary(
                "==", Expr.project(unsigned, "value"), Expr.integer(1, "u32")
            )
        )
        unsigned_query = emit_smtlib(unsigned_item)
        self.assertIn("(_ BitVec 32)", unsigned_query)
        self.assertEqual(unsigned_query, emit_smtlib(unsigned_item))

    def test_nested_datatypes_are_declared_dependency_first(self):
        inner = make_record_type("Inner", (("x", "i32"),))
        outer = make_record_type("Outer", (("inner", inner), ("y", "i32")))
        value = Expr.variable("outer#0", outer)
        query = emit_smtlib(
            obligation(
                Expr.binary("==", Expr.project(value, "inner"), Expr.project(value, "inner"))
            )
        )
        self.assertLess(query.index(record_sort_symbol(inner)), query.index(record_sort_symbol(outer)))

    def test_z3_record_models_decode_nested_arrays(self):
        type_name = make_record_type("Buffer", (("values", "array<i32,2>"),))
        sort = record_sort_symbol(type_name)
        constructor = record_constructor_symbol(type_name)
        parsed = parse_z3_model(
            "sat\n(model (define-fun b_v0 () "
            f"{sort} ({constructor} "
            "(store ((as const (Array Int Int)) 0) 1 7))))\n",
            {"b#0": type_name},
        )
        self.assertEqual(parsed, {"b#0": RecordValue(type_name, ((0, 7),))})

    def test_record_counterexample_round_trips_through_cache(self):
        type_name = make_record_type("Pair", (("x", "i32"), ("y", "i32")))
        value = Expr.variable("p#0", type_name)
        item = obligation(Expr.binary("==", value, value))
        with tempfile.TemporaryDirectory() as directory:
            backend = RecordCounterexampleBackend(type_name)
            cached = CachedCheckerBackend(backend, Path(directory) / "cache.json")
            first = cached.check(item)
            second = cached.check(item)
            cache_payload = json.loads((Path(directory) / "cache.json").read_text())
        self.assertEqual(backend.calls, 1)
        self.assertEqual(second.counterexample, first.counterexample)
        encoded = next(iter(cache_payload["entries"].values()))["result"]["counterexample"]
        self.assertEqual(encoded["p#0"]["$record"], type_name)


if __name__ == "__main__":
    unittest.main()
