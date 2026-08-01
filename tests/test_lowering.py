import unittest

from semantic_verifier import verify_source
from semantic_verifier.dump import dump_module


class LoweringTests(unittest.TestCase):
    def test_assignment_versions_state(self):
        report = verify_source(
            "int f(int x) { int y = x; y = y + 1; return y; }\n"
        )
        function = report.module.functions[0]
        assignments = [node for node in function.body if node.kind == "assign"]
        self.assertEqual([node.target for node in assignments], ["y#0", "y#1"])

    def test_if_else_has_branch_and_merge(self):
        report = verify_source(
            "int f(int x) { int y = 0; "
            "if (x > 0) y = 1; else y = 2; return y; }\n"
        )
        branch = next(
            node for node in report.module.functions[0].body if node.kind == "branch"
        )
        self.assertEqual(len(branch.then_body), 1)
        self.assertEqual(len(branch.else_body), 1)
        self.assertEqual(len(branch.merges), 1)
        self.assertEqual(branch.merges[0].target, "y#3")

    def test_ir_dump_is_stable_and_human_readable(self):
        source = "int f(int x) { int y = x; return y; }\n"
        first = dump_module(verify_source(source).module)
        second = dump_module(verify_source(source).module)
        self.assertEqual(first, second)
        self.assertIn("y#0 := x#0", first)

    def test_source_location_is_preserved(self):
        report = verify_source(
            "\n\nint f(int x) {\n    return x;\n}\n", display_path="sample.cpp"
        )
        return_node = report.module.functions[0].body[0]
        self.assertEqual(return_node.location.file, "sample.cpp")
        self.assertEqual(return_node.location.line, 4)

    def test_bool_local_and_branch(self):
        report = verify_source(
            "bool f(bool flag) { bool out = false; "
            "if (flag) out = true; return out; }\n"
        )
        self.assertFalse(any(r.status.value == "unsupported" for r in report.results))
