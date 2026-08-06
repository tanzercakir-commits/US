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

    def test_int_call_initializer_lowers_to_call_with_result(self):
        report = verify_source(
            "int callee(int x) { return x; } "
            "int caller(int x) { int q = callee(x); return q; }\n"
        )
        caller = next(
            function
            for function in report.module.functions
            if function.name == "caller"
        )
        call, returned = caller.body

        self.assertEqual(call.kind, "call")
        self.assertEqual(call.target, "q#0")
        self.assertEqual(call.result_type, "i32")
        self.assertEqual(call.callee, "callee")
        self.assertEqual([argument.value for argument in call.arguments], ["x#0"])
        self.assertEqual(returned.expression.value, "q#0")
        self.assertEqual(
            {key: call.to_dict()[key] for key in ("kind", "target", "result_type")},
            {"kind": "call", "target": "q#0", "result_type": "i32"},
        )

    def test_int_call_assignment_creates_next_target_version(self):
        report = verify_source(
            "int callee(int x) { return x; } "
            "int caller(int x) { int q = 0; q = callee(x); return q; }\n"
        )
        caller = next(
            function
            for function in report.module.functions
            if function.name == "caller"
        )

        self.assertEqual(
            [(node.kind, node.target) for node in caller.body[:-1]],
            [("assign", "q#0"), ("call", "q#1")],
        )
        self.assertEqual(caller.body[1].result_type, "i32")
        self.assertEqual(caller.body[-1].expression.value, "q#1")

    def test_other_nested_call_positions_remain_fail_closed(self):
        cases = {
            "initializer expression": (
                "int f(int x) { return x; } "
                "int g(int x) { int q = f(x) + 1; return q; }",
                "calls nested inside expressions",
            ),
            "assignment expression": (
                "int f(int x) { return x; } "
                "int g(int x) { int q = 0; q = f(x) + 1; return q; }",
                "calls nested inside expressions",
            ),
            "return expression": (
                "int f(int x) { return x; } int g(int x) { return f(x); }",
                "calls nested inside expressions",
            ),
            "nested argument": (
                "int f(int x) { return x; } "
                "int g(int x) { int q = f(f(x)); return q; }",
                "calls nested inside expressions",
            ),
            "bool result initializer": (
                "bool f(bool x) { return x; } "
                "bool g(bool x) { bool q = f(x); return q; }",
                "only int call results",
            ),
        }
        for label, (source, reason) in cases.items():
            with self.subTest(label=label):
                report = verify_source(source + "\n")
                unsupported = next(
                    result
                    for result in report.results
                    if result.status.value == "unsupported"
                )
                self.assertIn(reason, unsupported.message)
    def test_while_lowers_invariant_and_loop_state_havoc(self):
        source = (
            "int sum(int n) {\n"
            "  int i = 0;\n"
            "  int total = 0;\n"
            "  // cs: invariant i >= 0 && total >= 0\n"
            "  while (i < n) {\n"
            "    total = total + i;\n"
            "    i = i + 1;\n"
            "  }\n"
            "  return total;\n"
            "}\n"
        )
        report = verify_source(source)
        function = report.module.functions[0]
        loop = next(node for node in function.body if node.kind == "loop")

        self.assertEqual(loop.expression.text(), "(i#1 < n#0)")
        self.assertEqual(
            [item.expression.text() for item in loop.invariants],
            ["((i#1 >= 0) && (total#1 >= 0))"],
        )
        self.assertEqual(
            [
                (
                    item.name,
                    item.entry,
                    item.head,
                    item.back_edge,
                    item.exit,
                )
                for item in loop.loop_variables
            ],
            [
                ("i", "i#0", "i#1", "i#2", "i#3"),
                ("total", "total#0", "total#1", "total#2", "total#3"),
            ],
        )
        self.assertEqual(
            [(node.kind, node.target) for node in loop.body],
            [("assign", "total#2"), ("assign", "i#2")],
        )
        self.assertEqual(function.body[-1].expression.value, "total#3")
        self.assertEqual(
            [item["name"] for item in loop.to_dict()["loop_variables"]],
            ["i", "total"],
        )

    def test_loop_modified_variables_include_nested_branch_assignments(self):
        source = (
            "int f(int x, int y, bool flag) {\n"
            "  // cs: invariant x >= 0 && y >= 0\n"
            "  while (x < 10) {\n"
            "    if (flag) x = x + 1; else y = y + 1;\n"
            "  }\n"
            "  return x + y;\n"
            "}\n"
        )
        report = verify_source(source)
        loop = report.module.functions[0].body[0]

        self.assertEqual(loop.kind, "loop")
        self.assertEqual(
            [item.name for item in loop.loop_variables], ["x", "y"]
        )
        self.assertEqual(loop.body[0].kind, "branch")
        self.assertEqual(
            [item.back_edge for item in loop.loop_variables], ["x#3", "y#3"]
        )
