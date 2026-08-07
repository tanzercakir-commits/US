from __future__ import annotations

from pathlib import Path
import unittest

from semantic_verifier.cpp26_contracts import (
    bridge_cpp26_contracts,
    normalize_result_binding,
)
from semantic_verifier.dump import dump_module, dump_results
from semantic_verifier.pipeline import VerificationPipeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "cpp26_contracts"


def without_locations(value):
    if isinstance(value, dict):
        return {
            key: without_locations(item)
            for key, item in value.items()
            if key not in {"id", "location"}
        }
    if isinstance(value, list):
        return [without_locations(item) for item in value]
    return value


class Cpp26ContractsBridgeTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = VerificationPipeline()

    def fixture_text(self, name: str) -> str:
        return (FIXTURE / name).read_text(encoding="utf-8")

    def test_bridge_preserves_utf8_bytes_and_newline_positions(self):
        source = (
            "int f(const int value)\r\n"
            "  pre(value >= 0 /* é */)\r\n"
            "  post(r: r >= value)\r\n"
            "{\r\n"
            "  contract_assert(value >= 0);\r\n"
            "  return value;\r\n"
            "}\r\n"
        )
        bridge = bridge_cpp26_contracts(source)
        self.assertEqual(
            len(bridge.compiler_source.encode("utf-8")),
            len(source.encode("utf-8")),
        )
        self.assertEqual(
            bridge.compiler_source.count("\r\n"), source.count("\r\n")
        )
        self.assertEqual(
            [item.kind for item in bridge.function_contracts],
            ["requires", "ensures"],
        )
        self.assertEqual(bridge.assertion_count, 1)
        self.assertNotIn("contract_assert", bridge.compiler_source)
        self.assertIn("assert         (value >= 0);", bridge.compiler_source)

    def test_comments_strings_raw_strings_and_directives_are_inert(self):
        source = (
            "#define CONTRACT_TEXT pre(value > 0)\n"
            "// post(r: r > 0)\n"
            'const char* a = "contract_assert(false);";\n'
            'const char* b = R"(pre(false) post(r: false))";\n'
        )
        bridge = bridge_cpp26_contracts(source)
        self.assertFalse(bridge.changed)
        self.assertEqual(bridge.compiler_source, source)

    def test_result_binding_renames_only_bound_identifier_tokens(self):
        self.assertEqual(
            normalize_result_binding(
                "r.value == box.r && r.r >= 0 && other == r", "r"
            ),
            "result.value == box.r && result.r >= 0 && other == result",
        )

    def test_verified_fixture_uses_all_three_standard_forms(self):
        report = self.pipeline.verify_file(FIXTURE / "verified.cpp")
        self.assertEqual(
            report.summary(),
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 0,
                "verified": 6,
                "violated": 0,
            },
        )
        function = report.module.functions[0]
        self.assertEqual(
            [(item.kind, item.location.line) for item in function.contracts],
            [("requires", 2), ("ensures", 3)],
        )
        assertions = [item for item in function.body if item.kind == "assert"]
        self.assertEqual(len(assertions), 1)
        self.assertEqual(assertions[0].location.line, 5)

    def test_standard_and_existing_forms_have_the_same_semantic_projection(self):
        standard = self.pipeline.verify_source(
            self.fixture_text("verified.cpp"), "equivalent.cpp"
        )
        existing = self.pipeline.verify_source(
            self.fixture_text("equivalent_cs.cpp"), "equivalent.cpp"
        )
        self.assertEqual(
            without_locations(standard.module.to_dict()),
            without_locations(existing.module.to_dict()),
        )
        self.assertEqual(
            [
                without_locations(item.to_dict())
                for item in standard.obligations
            ],
            [
                without_locations(item.to_dict())
                for item in existing.obligations
            ],
        )
        self.assertEqual(
            [(item.kind, item.status.value) for item in standard.results],
            [(item.kind, item.status.value) for item in existing.results],
        )

    def test_post_without_result_binding_is_supported(self):
        source = (
            "int nonnegative(const int value)\n"
            "  pre(value >= 0)\n"
            "  post(value >= 0)\n"
            "{ return value; }\n"
        )
        report = self.pipeline.verify_source(source, "post_without_result.cpp")
        self.assertEqual(report.summary()["verified"], 2)
        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(
            [item.text for item in report.module.functions[0].contracts],
            ["requires value >= 0", "ensures value >= 0"],
        )

    def test_violated_postcondition_is_replayed(self):
        report = self.pipeline.verify_file(FIXTURE / "violated.cpp")
        self.assertEqual(
            report.summary(),
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 0,
                "verified": 2,
                "violated": 1,
            },
        )
        violated = [item for item in report.results if item.status.value == "violated"]
        self.assertEqual([item.kind for item in violated], ["postcondition"])
        self.assertIsNotNone(violated[0].counterexample)
        self.assertIn("replay", violated[0].message.lower())

    def test_unsupported_standard_boundaries_fail_closed(self):
        cases = {
            "attribute": (
                "int f(const int x) pre [[likely]] (x >= 0) { return x; }\n"
            ),
            "assert_attribute": (
                "int f(const int x) { "
                "contract_assert [[likely]] (x >= 0); return x; }\n"
            ),
            "malformed": "int f(const int x) pre(x >= 0 { return x; }\n",
            "mixed": (
                "// cs: requires x >= 0\n"
                "int f(const int x) pre(x >= 0) { return x; }\n"
            ),
            "redeclared": (
                "int f(const int x);\n"
                "int f(const int x) post(r: r == x) { return x; }\n"
            ),
            "non_const_post_use": (
                "int f(int x) post(r: r == x) { return x; }\n"
            ),
            "result_conflict": (
                "int f(const int r) post(r: r >= 0) { return r; }\n"
            ),
            "virtual": (
                "struct S { virtual int f(const int x) "
                "post(r: r == x) { return x; } };\n"
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                report = self.pipeline.verify_source(source, f"{name}.cpp")
                self.assertGreater(report.summary()["unsupported"], 0)
                self.assertEqual(report.summary()["verified"], 0)
                self.assertEqual(report.summary()["violated"], 0)

    def test_unattached_function_contract_is_explicitly_unsupported(self):
        source = (
            "int f(const int x) {\n"
            "  pre(x >= 0);\n"
            "  return x;\n"
            "}\n"
        )
        report = self.pipeline.verify_source(source, "orphan.cpp")
        reasons = [item.reason for item in report.module.unsupported]
        self.assertTrue(any("orphan C++26" in reason for reason in reasons))
        self.assertGreater(report.summary()["unsupported"], 0)

    def test_repeated_json_text_and_ir_are_byte_identical(self):
        first = self.pipeline.verify_file(FIXTURE / "verified.cpp")
        second = self.pipeline.verify_file(FIXTURE / "verified.cpp")
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(dump_results(first), dump_results(second))
        self.assertEqual(dump_module(first.module), dump_module(second.module))

    def test_temporary_bridge_paths_never_leak(self):
        relative = Path("fixtures") / "cpp26_contracts" / "verified.cpp"
        report = self.pipeline.verify_file(relative)
        serialized = report.to_json()
        self.assertNotIn("semantic-verifier-cpp26-", serialized)
        self.assertTrue(
            all(
                item.location.file == "fixtures/cpp26_contracts/verified.cpp"
                for item in report.results
            )
        )


if __name__ == "__main__":
    unittest.main()