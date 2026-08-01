import unittest

from semantic_verifier import verify_source


class FrontendSoundnessTests(unittest.TestCase):
    def test_disjoint_scope_names_have_distinct_ssa_identities(self):
        report = verify_source(
            "// cs: ensures result == 1\n"
            "int f() { { int y = 1; } { int y = 2; } return 0; }\n"
        )

        function = report.module.functions[0]
        self.assertEqual(
            [symbol.versioned_name for symbol in function.locals],
            ["y#0", "y@2#0"],
        )
        self.assertEqual(
            [symbol.source_name for symbol in function.locals], ["y", "y"]
        )
        postcondition = next(
            result for result in report.results if result.kind == "postcondition"
        )
        self.assertEqual(postcondition.status.value, "violated")

    def test_same_arity_overload_uses_resolved_parameter_types(self):
        report = verify_source(
            "// cs: requires x > 0\n"
            "int target(int x) { return x; }\n"
            "int target(bool flag);\n"
            "int caller(bool b) { target(b); return 0; }\n"
        )

        targets = [
            function
            for function in report.module.functions
            if function.name == "target"
        ]
        self.assertEqual(
            [function.link_name for function in targets],
            ["target(int)", "target(bool)"],
        )
        caller_results = [
            result for result in report.results if result.function == "caller"
        ]
        self.assertEqual(len(caller_results), 1)
        self.assertEqual(caller_results[0].status.value, "unsupported")
        self.assertIn("uncontracted external call", caller_results[0].message)

    def test_multiline_signature_uses_declaration_begin_for_contract(self):
        report = verify_source(
            "// cs: ensures result == 1\n"
            "int\n"
            "f() { return 0; }\n"
        )

        function = report.module.functions[0]
        self.assertEqual(len(function.contracts), 1)
        postcondition = next(
            result for result in report.results if result.kind == "postcondition"
        )
        self.assertEqual(postcondition.status.value, "violated")

    def test_orphan_contract_is_explicit_module_unsupported(self):
        report = verify_source(
            "// cs: ensures result == 1\n"
            "\n"
            "int f() { return 0; }\n"
        )

        self.assertEqual(len(report.module.functions[0].contracts), 0)
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("orphan cs: contract", report.results[0].message)

    def test_parse_error_redacts_random_temporary_path(self):
        first = verify_source("int broken( {\n", display_path="visible.cpp")
        second = verify_source("int broken( {\n", display_path="visible.cpp")

        self.assertEqual(first.to_json(), second.to_json())
        serialized = first.to_json()
        self.assertIn("visible.cpp", serialized)
        self.assertNotIn("semantic-verifier-", serialized)
        self.assertNotIn("AppData", serialized)


if __name__ == "__main__":
    unittest.main()
