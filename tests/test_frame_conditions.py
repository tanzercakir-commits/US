from pathlib import Path
import unittest

from semantic_verifier import verify_source
from semantic_verifier.backend import create_backend
from semantic_verifier.dump import dump_module
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


def results_for(report, *, function, kind):
    return [
        result
        for result in report.results
        if result.function == function and result.kind == kind
    ]


class FrameConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def verify_z3(self, source):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        return VerificationPipeline(
            checker=create_backend("z3", z3=self.z3)
        ).verify_source(source)

    def test_scalar_modifies_havocs_then_constrains_the_actual(self):
        report = verify_source(
            "// cs: modifies value\n"
            "// cs: ensures value == 7\n"
            "void assign_seven(int &value);\n"
            "// cs: ensures result == 7\n"
            "int caller() { int value = 0; assign_seven(value); return value; }\n"
        )
        self.assertEqual(results_for(report, function="caller", kind="postcondition")[0].status.value, "verified")
        call = report.module.functions[1].body[1]
        self.assertEqual((call.frame_effects[0].before, call.frame_effects[0].after), ("value#0", "value#1"))
        self.assertEqual(call.post_arguments[0].value, "value#1")

    def test_result_assignment_after_frame_effect_uses_distinct_ssa_versions(self):
        report = verify_source(
            "// cs: modifies value\n"
            "// cs: ensures value == 7 && result == value\n"
            "int assign_and_return(int &value);\n"
            "// cs: ensures result == 7\n"
            "int caller() { int value = 0; value = assign_and_return(value); return value; }\n"
        )
        self.assertEqual(results_for(report, function="caller", kind="postcondition")[0].status.value, "verified")
        call = report.module.functions[1].body[1]
        self.assertEqual(call.frame_effects[0].after, "value#1")
        self.assertEqual(call.target, "value#2")
        self.assertEqual(call.post_arguments[0].value, "value#1")
    def test_explicit_empty_frame_and_const_reference_preserve_state(self):
        report = verify_source(
            "// cs: modifies\n"
            "// cs: ensures value >= 0\n"
            "void inspect(const int &value);\n"
            "// cs: requires input >= 0\n"
            "// cs: ensures result == input\n"
            "int caller(int input) { inspect(input); return input; }\n"
        )
        self.assertFalse(any(result.status.value != "verified" for result in report.results))
        call = report.module.functions[1].body[1]
        self.assertEqual(call.frame_effects, ())
        self.assertEqual(call.arguments, call.post_arguments)

    def test_record_field_frame_preserves_every_unlisted_field(self):
        report = self.verify_z3(
            "struct Pair { int x; int y; };\n"
            "// cs: modifies pair.x\n"
            "// cs: ensures pair.x == 7\n"
            "void set_x(Pair &pair);\n"
            "// cs: ensures result.x == 7 && result.y == input.y\n"
            "Pair caller(Pair input) { set_x(input); return input; }\n"
        )
        post = results_for(report, function="caller", kind="postcondition")[0]
        self.assertEqual(post.status.value, "verified")
        obligation = next(item for item in report.obligations if item.id == post.obligation_id)
        self.assertIn(
            "(input#1 == update(input#0, x, input#1.x))",
            [assumption.text() for assumption in obligation.assumptions],
        )

    def test_multiple_disjoint_reference_actuals_share_one_exact_root_effect(self):
        report = self.verify_z3(
            "struct Pair { int x; int y; };\n"
            "// cs: modifies left, right\n"
            "// cs: ensures left == 3 && right == 4\n"
            "void set_both(int &left, int &right);\n"
            "// cs: ensures result.x == 3 && result.y == 4\n"
            "Pair caller() { Pair pair = {0, 0}; set_both(pair.x, pair.y); return pair; }\n"
        )
        self.assertEqual(results_for(report, function="caller", kind="postcondition")[0].status.value, "verified")
        effect = report.module.functions[1].body[1].frame_effects[0]
        self.assertEqual(
            [[step.value for step in location.path] for location in effect.modified],
            [["x"], ["y"]],
        )

    def test_nested_modifies_path_is_normalized_and_preserves_siblings(self):
        report = self.verify_z3(
            "struct Inner { int value; int spare; };\n"
            "struct Outer { Inner inner; int tag; };\n"
            "// cs: modifies outer.inner.value\n"
            "// cs: ensures outer.inner.value == 9\n"
            "void update(Outer &outer);\n"
            "// cs: ensures result.inner.value == 9 && result.inner.spare == input.inner.spare && result.tag == input.tag\n"
            "Outer caller(Outer input) { update(input); return input; }\n"
        )
        self.assertEqual(results_for(report, function="caller", kind="postcondition")[0].status.value, "verified")
        target = report.module.functions[0].frame.targets[0]
        self.assertEqual([step.value for step in target.path], ["inner", "value"])

    def test_local_proved_reference_can_be_the_actual(self):
        report = verify_source(
            "// cs: modifies value\n"
            "// cs: ensures value == 5\n"
            "void assign_five(int &value);\n"
            "// cs: ensures result == 5\n"
            "int caller() { int value = 0; int &alias = value; assign_five(alias); return value; }\n"
        )
        self.assertEqual(results_for(report, function="caller", kind="postcondition")[0].status.value, "verified")

    def test_invalid_duplicate_inaccessible_const_and_value_targets_fail_closed(self):
        sources = [
            ("duplicate or overlapping", "// cs: modifies value, value\nvoid mutate(int &value);\n"),
            ("inaccessible", "// cs: modifies missing\nvoid mutate(int &value);\n"),
            ("mutable reference parameter", "// cs: modifies value\nvoid inspect(const int &value);\n"),
            ("mutable reference parameter", "// cs: modifies value\nvoid by_value(int value);\n"),
        ]
        for reason, source in sources:
            with self.subTest(reason=reason, source=source):
                report = verify_source(source)
                self.assertTrue(any(result.status.value == "unsupported" and reason in result.message for result in report.results))
    def test_redeclaration_parameter_renaming_is_positional_and_conflicts_fail_closed(self):
        renamed = verify_source(
            "// cs: modifies original\n"
            "// cs: ensures original == 8\n"
            "void mutate(int &original);\n"
            "void mutate(int &renamed);\n"
            "// cs: ensures result == 8\n"
            "int caller() { int value = 0; mutate(value); return value; }\n"
        )
        self.assertEqual(results_for(renamed, function="caller", kind="postcondition")[0].status.value, "verified")
        self.assertEqual(renamed.module.functions[1].frame.targets[0].root, "f0002.s0001")
        conflicting = verify_source(
            "struct Pair { int x; int y; };\n"
            "// cs: modifies first.x\n"
            "void update(Pair &first);\n"
            "// cs: modifies second.y\n"
            "void update(Pair &second);\n"
        )
        self.assertTrue(any("conflicting modifies" in result.message for result in conflicting.results))
    def test_missing_frame_contract_fails_at_declaration_and_call(self):
        report = verify_source(
            "void mutate(int &value);\n"
            "int caller() { int value = 0; mutate(value); return value; }\n"
        )
        messages = [result.message for result in report.results]
        self.assertTrue(any("require an explicit cs: modifies" in message for message in messages))
        self.assertTrue(any("reference call requires" in message for message in messages))

    def test_overlapping_reference_actuals_fail_closed(self):
        report = verify_source(
            "// cs: modifies left, right\n"
            "void mutate(int &left, int &right);\n"
            "int caller() { int value = 0; mutate(value, value); return value; }\n"
        )
        self.assertTrue(any("overlapping reference arguments" in result.message for result in report.results))

    def test_conditional_reference_actual_and_reference_definition_fail_closed(self):
        conditional = verify_source(
            "// cs: modifies value\n"
            "void mutate(int &value);\n"
            "int caller(bool choose) { int a = 0; int b = 0; mutate(choose ? a : b); return a; }\n"
        )
        self.assertTrue(any(result.status.value == "unsupported" for result in conditional.results))
        definition = verify_source(
            "// cs: modifies value\n"
            "void mutate(int &value) { value = 1; }\n"
        )
        self.assertTrue(any("reference-parameter definitions" in result.message for result in definition.results))

    def test_frame_ir_and_json_are_deterministic_and_schema_v7(self):
        source = (
            "// cs: modifies value\n"
            "// cs: ensures value == 1\n"
            "void mutate(int &value);\n"
            "int caller() { int value = 0; mutate(value); return value; }\n"
        )
        first = verify_source(source)
        second = verify_source(source)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(dump_module(first.module), dump_module(second.module))
        payload = first.to_dict()["semantic_ir"]
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v7")
        self.assertEqual(payload["functions"][0]["parameters"][0]["passing"], "mutable_reference")
        self.assertEqual(payload["functions"][0]["frame"]["targets"][0]["root"], "f0001.s0001")
        self.assertEqual(payload["functions"][1]["body"][1]["frame_effects"][0]["after"], "value#1")

    def test_frame_example_is_fully_verified_and_deterministic(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        pipeline = VerificationPipeline(checker=create_backend("z3", z3=self.z3))
        first = pipeline.verify_file(Path("examples/frame_conditions.cpp"))
        second = pipeline.verify_file(Path("examples/frame_conditions.cpp"))
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.summary(), {"solver_error": 0, "unknown": 0, "unsupported": 0, "verified": 10, "violated": 0})


if __name__ == "__main__":
    unittest.main()
