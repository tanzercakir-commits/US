import json
import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.dump import dump_module
from semantic_verifier.model import SCHEMA, VerificationStatus
from semantic_verifier.pipeline import VerificationPipeline


def verify(source: str, backend: str = "z3"):
    return VerificationPipeline(checker=create_backend(backend)).verify_source(
        source, "references.cpp"
    )


class RestrictedReferenceTests(unittest.TestCase):
    def test_mutable_scalar_reference_updates_the_live_target(self):
        report = verify(
            "// cs: ensures return == 7\n"
            "int f(int value) { int& alias = value; alias = 7; return value; }\n"
        )
        self.assertEqual(report.summary()["verified"], 1)
        self.assertEqual(report.summary()["unsupported"], 0)
        function = report.module.functions[0]
        self.assertEqual(len(function.locals), 0)
        self.assertEqual(len(function.references), 1)
        binding = function.references[0]
        self.assertEqual((binding.name, binding.type, binding.target), ("alias", "i32", "value"))
        self.assertTrue(binding.mutable)
        self.assertEqual(binding.lifetime, "enclosing_lexical_scope")

    def test_const_reference_reads_current_value_not_a_snapshot(self):
        report = verify(
            "// cs: ensures return == 3\n"
            "int f(int value) { const int& view = value; value = 3; return view; }\n"
        )
        self.assertEqual(report.summary()["verified"], 1)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertFalse(report.module.functions[0].references[0].mutable)

    def test_record_and_disjoint_field_references_preserve_other_fields(self):
        report = verify(
            """
struct Pair { int x; int y; };
// cs: ensures return.x == 4 && return.y == input.y
Pair whole(Pair input) { Pair& alias = input; alias.x = 4; return input; }
// cs: requires input.x <= 2147483642
// cs: ensures return == input.x + 5
int fields(Pair input) {
  const int& left = input.x;
  int& right = input.y;
  right = 5;
  return left + right;
}
"""
        )
        self.assertEqual(report.summary()["verified"], 4)
        self.assertEqual(report.summary()["violated"], 0)
        self.assertEqual(report.summary()["unsupported"], 0)
        fields = report.module.functions[1].references
        self.assertEqual([step.value for step in fields[0].path], ["x"])
        self.assertEqual([step.value for step in fields[1].path], ["y"])

    def test_branch_and_sequential_lifetimes_allow_nonoverlapping_live_bindings(self):
        report = verify(
            """
// cs: ensures (choose && return == 1) || (!choose && return == 2)
int branch(int value, bool choose) {
  if (choose) { int& alias = value; alias = 1; }
  else { int& alias = value; alias = 2; }
  return value;
}
// cs: ensures return == 2
int sequential(int value) {
  { int& alias = value; alias = 1; }
  { int& alias = value; alias = 2; }
  return value;
}
"""
        )
        self.assertEqual(report.summary()["verified"], 2)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(len(report.module.functions[0].references), 2)
        self.assertEqual(len(report.module.functions[1].references), 2)

    def test_reference_declared_before_loop_tracks_target_havoc(self):
        report = verify(
            """
// cs: requires n >= 0
int loop(int value, int n) {
  int& alias = value;
  // cs: invariant n >= 0
  while (n > 0) { alias = 0; n = n - 1; }
  return alias;
}
"""
        )
        self.assertEqual(report.summary()["verified"], 4)
        self.assertEqual(report.summary()["unsupported"], 0)
        loop = next(node for node in report.module.functions[0].body if node.kind == "loop")
        self.assertEqual({item.name for item in loop.loop_variables}, {"n", "value"})

    def test_reference_value_can_flow_to_a_by_value_call(self):
        report = verify(
            """
// cs: ensures return == input
int identity(int input) { return input; }
// cs: ensures return == input
int caller(int input) {
  const int& view = input;
  int result = identity(view);
  return result;
}
"""
        )
        self.assertEqual(report.summary()["verified"], 2)
        self.assertEqual(report.summary()["unsupported"], 0)

    def test_multiple_possible_temporary_and_unreviewed_targets_fail_closed(self):
        rejected = (
            "int f(bool b, int x, int y) { int& r = b ? x : y; return r; }",
            "int f() { const int& r = 1; return r; }",
            "int f() { int&& r = 1; return r; }",
            "int f() { int a[2] = {1,2}; int& r = a[0]; return r; }",
            "int f(int value) { int* p = &value; int& r = *p; return r; }",
            "int f(int value, int n) { while (n > 0) { int& r=value; r=0; n=n-1; } return value; }",
        )
        for source in rejected:
            with self.subTest(source=source):
                report = verify(source + "\n")
                self.assertEqual(report.summary()["verified"], 0)
                self.assertGreater(
                    report.summary()["unsupported"] + report.summary()["solver_error"],
                    0,
                )

    def test_overlapping_live_reference_paths_fail_closed(self):
        report = verify(
            """
struct Pair { int x; int y; };
int f(Pair input) { Pair& whole=input; int& field=input.x; return field; }
"""
        )
        self.assertEqual(report.summary()["verified"], 0)
        unsupported = next(
            item for item in report.results if item.status == VerificationStatus.UNSUPPORTED
        )
        self.assertIn("overlaps an existing live reference", unsupported.message)

    def test_reference_parameters_and_returns_fail_closed(self):
        for source in (
            "int f(int& input) { return input; }",
            "int& f(int input) { return input; }",
        ):
            with self.subTest(source=source):
                report = verify(source + "\n")
                self.assertEqual(report.summary()["verified"], 0)
                self.assertGreater(report.summary()["unsupported"], 0)

    def test_reference_ir_and_serialization_are_deterministic(self):
        source = (
            "// cs: ensures return == 4\n"
            "int f(int value) { int& alias=value; alias=4; return value; }\n"
        )
        first = verify(source)
        second = verify(source)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(dump_module(first.module), dump_module(second.module))
        payload = json.loads(first.to_json())
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v6")
        self.assertEqual(payload["schema"], SCHEMA)
        reference = payload["semantic_ir"]["functions"][0]["references"][0]
        self.assertEqual(reference["target"], "value")
        self.assertEqual(reference["lifetime"], "enclosing_lexical_scope")


if __name__ == "__main__":
    unittest.main()
