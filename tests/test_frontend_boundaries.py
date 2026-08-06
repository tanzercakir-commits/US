from pathlib import Path
import tempfile
import unittest

from semantic_verifier import verify_file, verify_source


class FrontendBoundaryTests(unittest.TestCase):
    def test_utf8_byte_offsets_preserve_main_file_nodes_and_locations(self):
        report = verify_source(
            "// " + (chr(0xE9) * 100) + "\nint f(int x){ return x; }\n",
            display_path="unicode.cpp",
        )

        function = report.module.functions[0]
        self.assertEqual((function.location.line, function.location.column), (2, 5))
        self.assertEqual(
            (function.parameters[0].location.line, function.parameters[0].location.column),
            (2, 11),
        )
        self.assertEqual(
            (function.body[0].location.line, function.body[0].location.column),
            (2, 15),
        )

    def test_crlf_is_preserved_for_contract_attachment_and_locations(self):
        source = (
            b"// cs: ensures result == 1\r\n"
            b"int\r\n"
            b"f() { return 0; }\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crlf.cpp"
            path.write_bytes(source)
            report = verify_file(path)

        function = report.module.functions[0]
        self.assertEqual(len(function.contracts), 1)
        self.assertEqual((function.location.line, function.location.column), (3, 1))
        postcondition = next(
            result for result in report.results if result.kind == "postcondition"
        )
        self.assertEqual(postcondition.status.value, "violated")

    def test_utf8_bom_first_line_contract_attaches_with_physical_locations(self):
        source = (
            b"\xef\xbb\xbf// cs: ensures result == 1\r\n"
            b"int f() { return 0; }\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.cpp"
            path.write_bytes(source)
            report = verify_file(path)

        function = report.module.functions[0]
        self.assertEqual(len(function.contracts), 1)
        self.assertEqual(
            (function.contracts[0].location.line, function.contracts[0].location.column),
            (1, 5),
        )
        self.assertEqual((function.location.line, function.location.column), (2, 5))
        postcondition = next(
            result for result in report.results if result.kind == "postcondition"
        )
        self.assertEqual(postcondition.status.value, "violated")

    def test_include_is_explicit_and_header_function_is_not_in_main_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "helper.hpp").write_text(
                "int from_header() { return 99; }\n", encoding="utf-8"
            )
            source = root / "main.cpp"
            source.write_text(
                '#include "helper.hpp"\nint local() { return 0; }\n',
                encoding="utf-8",
            )
            report = verify_file(source)

        self.assertEqual(
            [function.name for function in report.module.functions], ["local"]
        )
        self.assertTrue(
            any("#include" in (issue.reason or "") for issue in report.module.unsupported)
        )
        self.assertEqual(report.results[0].status.value, "unsupported")

    def test_conditional_preprocessor_directive_is_explicit(self):
        report = verify_source("#if 1\nint f() { return 0; }\n#endif\n")

        self.assertEqual([function.name for function in report.module.functions], ["f"])
        self.assertTrue(
            any("#if" in (issue.reason or "") for issue in report.module.unsupported)
        )
        self.assertEqual(report.results[0].status.value, "unsupported")

    def test_preprocessor_directive_after_block_comment_is_explicit(self):
        report = verify_source(
            "/* legal preprocessing whitespace */ #define VALUE 1\n"
            "int f() { return VALUE; }\n"
        )

        self.assertTrue(
            any("#define" in (issue.reason or "") for issue in report.module.unsupported)
        )
        self.assertEqual(report.results[0].status.value, "unsupported")

    def test_preprocessor_directive_after_bom_is_explicit(self):
        report = verify_source(
            "\ufeff#define VALUE 1\n"
            "int f() { return VALUE; }\n"
        )

        issue = next(
            issue
            for issue in report.module.unsupported
            if "#define" in (issue.reason or "")
        )
        self.assertEqual(issue.location.line, 1)
        self.assertEqual(report.results[0].status.value, "unsupported")

    def test_preprocessor_digraph_is_normalized_and_explicit(self):
        report = verify_source(
            "%:define VALUE 1\n"
            "int f() { return VALUE; }\n"
        )

        self.assertTrue(
            any("#define" in (issue.reason or "") for issue in report.module.unsupported)
        )
        self.assertEqual(report.results[0].status.value, "unsupported")

    def test_directive_text_inside_block_comment_is_not_a_preprocessor_issue(self):
        report = verify_source(
            "/*\n#define NOT_A_DIRECTIVE 1\n*/\n"
            "int f() { return 0; }\n"
        )

        self.assertFalse(
            any(
                "preprocessor directive" in (issue.reason or "")
                for issue in report.module.unsupported
            )
        )
        self.assertFalse(report.results)

    def test_directive_text_inside_strings_is_not_a_preprocessor_issue(self):
        cases = {
            "ordinary": 'int f() { "#define NOT_A_DIRECTIVE 1"; return 0; }\n',
            "raw": 'int f() { R"(\n#define NOT_A_DIRECTIVE 1\n)"; return 0; }\n',
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                report = verify_source(source)
                self.assertFalse(
                    any(
                        "preprocessor directive" in (issue.reason or "")
                        for issue in report.module.unsupported
                    )
                )

    def test_function_try_block_is_explicitly_unsupported_definition(self):
        report = verify_source(
            "// cs: ensures result == 1\n"
            "int f() try { return 1; } catch (...) { return 0; }\n"
        )

        function = report.module.functions[0]
        self.assertTrue(function.has_body)
        self.assertEqual(len(function.contracts), 1)
        self.assertEqual(
            [result.kind for result in report.results], ["unsupported_construct"]
        )
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("function try blocks", report.results[0].message)

    def test_builtin_shaped_assert_function_try_block_is_not_hidden(self):
        report = verify_source(
            "void assert(bool flag) try {} catch (...) {}\n"
        )

        self.assertEqual([function.name for function in report.module.functions], ["assert"])
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("function try blocks", report.results[0].message)

    def test_volatile_parameter_and_local_are_explicitly_unsupported(self):
        cases = {
            "return": "volatile int f() { return 0; }\n",
            "parameter": "int f(volatile int x) { return x; }\n",
            "local": "int f() { volatile int x = 0; return x; }\n",
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                report = verify_source(source)
                self.assertEqual(report.results[0].status.value, "unsupported")
                self.assertIn("volatile", report.results[0].message)

    def test_static_and_thread_local_are_explicitly_unsupported(self):
        cases = {
            "static": "int f() { static int x = 0; return x; }\n",
            "thread_local": "int f() { thread_local int x = 0; return x; }\n",
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                report = verify_source(source)
                self.assertEqual(report.results[0].status.value, "unsupported")
                self.assertIn("static and thread_local", report.results[0].message)

    def test_result_parameter_name_is_reserved(self):
        report = verify_source("int f(int result) { return result; }\n")

        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("reserved for postconditions", report.results[0].message)

    def test_only_declaration_only_void_bool_assert_is_builtin(self):
        report = verify_source(
            "void assert(bool);\n"
            "int f(int x) { assert(x >= 0); return x; }\n"
        )

        self.assertEqual([function.name for function in report.module.functions], ["f"])
        assertion = next(result for result in report.results if result.kind == "assertion")
        self.assertEqual(assertion.status.value, "violated")

    def test_user_defined_int_assert_is_a_normal_contracted_call(self):
        report = verify_source(
            "// cs: requires flag\n"
            "int assert(bool flag) { return 0; }\n"
            "int caller() { assert(false); return 0; }\n"
        )

        self.assertFalse(any(result.kind == "assertion" for result in report.results))
        precondition = next(
            result for result in report.results if result.kind == "precondition"
        )
        self.assertEqual(precondition.status.value, "violated")

    def test_unreachable_unsupported_statement_is_still_explicit(self):
        report = verify_source(
            "int f(int x) { return x; do x = x - 1; while (x); }\n"
        )

        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("DoStmt", report.results[0].message)

    def test_main_fallthrough_lowers_to_explicit_return_zero(self):
        report = verify_source("int main() {}\n")

        function = report.module.functions[0]
        self.assertEqual(len(function.body), 1)
        implicit_return = function.body[0]
        self.assertEqual(implicit_return.kind, "return")
        self.assertEqual(implicit_return.origin, "implicit_main_fallthrough")
        self.assertEqual(implicit_return.expression.value, 0)
        self.assertFalse(report.results)


if __name__ == "__main__":
    unittest.main()
