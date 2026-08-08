from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "research" / "cpp26_contracts_bridge.json"


class Cpp26ContractsResearchTests(unittest.TestCase):
    def load_matrix(self):
        return json.loads(MATRIX.read_text(encoding="utf-8-sig"))

    def test_matrix_has_versioned_dated_shape(self):
        matrix = self.load_matrix()
        self.assertEqual(
            set(matrix),
            {
                "as_of",
                "bridge_decision",
                "feature_test",
                "mappings",
                "non_mappings",
                "schema",
                "sources",
                "standard_surface",
                "toolchains",
            },
        )
        self.assertEqual(matrix["schema"], "codeskeptic.cpp26-contracts-research/v1")
        self.assertEqual(matrix["as_of"], "2026-08-07")
        self.assertEqual(
            matrix["feature_test"],
            {"macro": "__cpp_contracts", "minimum": 202502},
        )

    def test_all_standard_forms_have_distinct_owned_mappings(self):
        matrix = self.load_matrix()
        mappings = {item["cpp26"]: item for item in matrix["mappings"]}
        self.assertEqual(set(mappings), {"pre", "post", "contract_assert"})
        self.assertEqual(mappings["pre"]["owned_semantic"], "requires")
        self.assertEqual(mappings["post"]["owned_semantic"], "ensures")
        self.assertEqual(
            mappings["contract_assert"]["owned_semantic"], "assertion_ir"
        )
        self.assertTrue(
            all(item["support"] == "planned_c3_1" for item in mappings.values())
        )
        surface = {item["form"] for item in matrix["standard_surface"]}
        self.assertEqual(surface, set(mappings))

    def test_only_primary_official_sources_support_status_claims(self):
        urls = {item["url"] for item in self.load_matrix()["sources"]}
        self.assertEqual(
            urls,
            {
                "https://wg21.link/P2900R14",
                "https://eel.is/c++draft/dcl.contract.func",
                "https://eel.is/c++draft/stmt.contract.assert",
                "https://eel.is/c++draft/basic.contract.eval",
                "https://clang.llvm.org/cxx_status.html",
                "https://gcc.gnu.org/projects/cxx-status.html",
            },
        )

    def test_decision_is_fail_closed_and_records_non_mappings(self):
        matrix = self.load_matrix()
        decision = matrix["bridge_decision"]
        self.assertEqual(decision["mode"], "fail_closed_source_bridge")
        self.assertEqual(
            decision["compiler_source_policy"],
            "same UTF-8 byte length and newline positions",
        )
        self.assertTrue(decision["clang_native_ast_required_later"])
        self.assertEqual(
            matrix["toolchains"]["local_probe"],
            {
                "compiler": "Clang 20.1.8",
                "feature_macro": "missing",
                "mode": "-std=c++2c",
                "result": "rejected",
                "syntax_diagnostic": "expected function body after function declarator",
            },
        )
        self.assertEqual(
            {item["owned_semantic"] for item in matrix["non_mappings"]},
            {"invariant", "modifies"},
        )


if __name__ == "__main__":
    unittest.main()
