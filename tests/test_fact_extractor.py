from __future__ import annotations

import json
import unittest

from semantic_verifier.fact_extractor import (
    ClangFactExtractor,
    extract_facts,
)
from semantic_verifier.facts import load_fact_index_json


class FactExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = ClangFactExtractor()

    @staticmethod
    def symbols_by_id(index):
        return {symbol.id: symbol for symbol in index.symbols}

    @staticmethod
    def functions(index):
        return {
            symbol.id: symbol
            for symbol in index.symbols
            if symbol.kind == "function"
        }

    @staticmethod
    def purity_by_name(index):
        symbols = {
            symbol.id: symbol.qualified_name
            for symbol in index.symbols
        }
        return {
            symbols[fact.function]: fact
            for fact in index.purity
        }

    def test_extracts_symbols_def_use_calls_and_mutations(self):
        source = (
            "int global_total = 0;\n"
            "int identity(int value) {\n"
            "    int local = value;\n"
            "    return local;\n"
            "}\n"
            "int update(int value) {\n"
            "    global_total = value;\n"
            "    return identity(global_total);\n"
            "}\n"
        )
        index = self.extractor.extract_source(source, "facts/basic.cpp")
        symbols = self.symbols_by_id(index)
        named = {
            (symbol.qualified_name, symbol.kind)
            for symbol in index.symbols
        }
        self.assertIn(("global_total", "variable"), named)
        self.assertIn(("identity", "function"), named)
        self.assertIn(("update", "function"), named)
        self.assertIn(("identity::value@parameter:0", "parameter"), named)
        self.assertTrue(
            any(
                name.startswith("identity::local@")
                and kind == "variable"
                for name, kind in named
            )
        )

        self.assertEqual(len(index.calls), 1)
        call = index.calls[0]
        self.assertEqual(symbols[call.caller].qualified_name, "update")
        self.assertEqual(symbols[call.callee].qualified_name, "identity")

        mutation_names = {
            symbols[fact.target].qualified_name
            for fact in index.mutations
        }
        self.assertIn("global_total", mutation_names)
        self.assertTrue(
            any(name.startswith("identity::local@") for name in mutation_names)
        )
        global_uses = [
            fact.kind
            for fact in index.uses
            if symbols[fact.symbol].qualified_name == "global_total"
        ]
        self.assertEqual(set(global_uses), {"read", "write"})
        self.assertTrue(
            any(
                fact.kind == "assignment"
                and symbols[fact.symbol].qualified_name == "global_total"
                for fact in index.definitions
            )
        )

        purity = self.purity_by_name(index)
        self.assertEqual(purity["identity"].status, "pure")
        self.assertEqual(purity["update"].status, "impure")
        self.assertEqual(
            purity["update"].reasons,
            ("global_mutation",),
        )
        self.assertEqual(index.limitations, ())

    def test_record_field_and_parameter_mutation_are_explicit(self):
        source = (
            "struct Point { int x; int y; };\n"
            "int set_x(Point& point, int value) {\n"
            "    point.x = value;\n"
            "    return point.x;\n"
            "}\n"
        )
        index = extract_facts(source, "facts/records.cpp")
        symbols = self.symbols_by_id(index)
        named = {
            (symbol.qualified_name, symbol.kind)
            for symbol in index.symbols
        }
        self.assertIn(("Point", "record"), named)
        self.assertIn(("Point::x", "field"), named)
        self.assertIn(("Point::y", "field"), named)

        mutations = {
            symbols[fact.target].qualified_name
            for fact in index.mutations
        }
        self.assertIn("Point::x", mutations)
        self.assertIn("set_x::point@parameter:0", mutations)
        purity = self.purity_by_name(index)["set_x"]
        self.assertEqual(purity.status, "impure")
        self.assertEqual(purity.reasons, ("parameter_mutation",))
        self.assertTrue(
            any(
                symbols[fact.symbol].qualified_name == "Point::x"
                and fact.kind == "read"
                for fact in index.uses
            )
        )

    def test_namespaces_and_overloads_have_distinct_stable_symbols(self):
        source = (
            "namespace alpha {\n"
            "int pick(int value) { return value; }\n"
            "int pick(bool value) { return value ? 1 : 0; }\n"
            "int call() { return pick(1); }\n"
            "}\n"
            "namespace beta {\n"
            "int pick(int value) { return value + 1; }\n"
            "}\n"
        )
        index = extract_facts(source, "facts/scopes.cpp")
        functions = [
            symbol
            for symbol in index.symbols
            if symbol.kind == "function"
        ]
        alpha = [
            symbol
            for symbol in functions
            if symbol.qualified_name == "alpha::pick"
        ]
        self.assertEqual(len(alpha), 2)
        self.assertEqual(
            {symbol.type for symbol in alpha},
            {"int (bool)", "int (int)"},
        )
        self.assertEqual(len({symbol.id for symbol in alpha}), 2)
        beta = [
            symbol
            for symbol in functions
            if symbol.qualified_name == "beta::pick"
        ]
        self.assertEqual(len(beta), 1)
        symbols = self.symbols_by_id(index)
        self.assertEqual(len(index.calls), 1)
        call = index.calls[0]
        self.assertEqual(symbols[call.caller].qualified_name, "alpha::call")
        self.assertEqual(symbols[call.callee].qualified_name, "alpha::pick")
        self.assertEqual(symbols[call.callee].type, "int (int)")
    def test_indirect_and_virtual_calls_are_visible_and_unknown(self):
        source = (
            "int apply(int (*fn)(int), int value) { return fn(value); }\n"
            "struct Base { virtual int run(); };\n"
            "int invoke(Base* base) { return base->run(); }\n"
        )
        index = extract_facts(source, "facts/dispatch.cpp")
        codes = {limitation.code for limitation in index.limitations}
        self.assertIn("indirect_call", codes)
        self.assertIn("virtual_dispatch", codes)
        purity = self.purity_by_name(index)
        self.assertEqual(purity["apply"].status, "unknown")
        self.assertEqual(purity["apply"].reasons, ("indirect_call",))
        self.assertEqual(purity["invoke"].status, "unknown")
        self.assertEqual(
            purity["invoke"].reasons,
            ("virtual_dispatch",),
        )
        self.assertEqual(index.calls, ())

    def test_declaration_only_callee_propagates_unknown(self):
        source = (
            "int external(int value);\n"
            "int caller(int value) { return external(value); }\n"
        )
        index = extract_facts(source, "facts/declaration.cpp")
        symbols = self.symbols_by_id(index)
        self.assertEqual(len(index.calls), 1)
        self.assertEqual(
            symbols[index.calls[0].callee].qualified_name,
            "external",
        )
        purity = self.purity_by_name(index)
        self.assertEqual(purity["external"].status, "unknown")
        self.assertEqual(
            purity["external"].reasons,
            ("unsupported_construct",),
        )
        self.assertEqual(purity["caller"].status, "unknown")
        self.assertEqual(
            purity["caller"].reasons,
            ("unsupported_construct",),
        )

    def test_macro_expansion_is_explicit_and_not_approximated(self):
        source = (
            "#define WRITE(target) ((target) = 1)\n"
            "int update(int value) { WRITE(value); return value; }\n"
        )
        index = extract_facts(source, "facts/macro.cpp")
        self.assertTrue(
            any(
                limitation.code == "macro_location"
                for limitation in index.limitations
            )
        )
        purity = self.purity_by_name(index)["update"]
        self.assertEqual(purity.status, "unknown")
        self.assertIn("unsupported_construct", purity.reasons)

    def test_repeated_and_relocated_frontend_runs_are_byte_identical(self):
        source = (
            "int twice(int value) {\n"
            "    int result = value + value;\n"
            "    return result;\n"
            "}\n"
        )
        first = self.extractor.extract_source(
            source,
            "stable/facts.cpp",
        )
        second = self.extractor.extract_source(
            source,
            "stable/facts.cpp",
        )
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.id, second.id)
        loaded = load_fact_index_json(first.to_json())
        self.assertEqual(loaded, first)

        serialized = first.to_json()
        self.assertNotIn("semantic-verifier-", serialized)
        self.assertNotIn("AppData", serialized)
        self.assertNotIn('"0x', serialized)
        self.assertNotIn("clang", serialized.lower())

    def test_system_header_declarations_are_excluded(self):
        source = (
            "#include <stddef.h>\n"
            "int keep(int value) { return value; }\n"
        )
        index = extract_facts(source, "facts/header.cpp")
        names = {
            symbol.qualified_name
            for symbol in index.symbols
        }
        self.assertIn("keep", names)
        self.assertIn("keep::value@parameter:0", names)
        self.assertEqual(len(names), 2)
        self.assertTrue(
            all(
                location.file == "facts/header.cpp"
                for symbol in index.symbols
                for location in (
                    symbol.declaration,
                    *(
                        (symbol.definition,)
                        if symbol.definition is not None
                        else ()
                    ),
                )
            )
        )

    def test_unsupported_top_level_construct_is_not_silent(self):
        source = (
            "using Value = int;\n"
            "int identity(int value) { return value; }\n"
        )
        index = extract_facts(source, "facts/alias.cpp")
        self.assertTrue(
            any(
                limitation.code == "unsupported_ast"
                and "TypeAliasDecl" in limitation.message
                for limitation in index.limitations
            )
        )
        self.assertEqual(
            self.purity_by_name(index)["identity"].status,
            "pure",
        )

    def test_shadowed_locals_do_not_collide_and_global_calls_are_limited(self):
        source = (
            "int source();\n"
            "int global_value = source();\n"
            "int shadow(int parameter) {\n"
            "    { int value = parameter; }\n"
            "    { int value = parameter; }\n"
            "    return parameter;\n"
            "}\n"
        )
        index = extract_facts(source, "facts/shadow.cpp")
        locals_named_value = [
            symbol
            for symbol in index.symbols
            if symbol.kind == "variable"
            and symbol.name == "value"
            and symbol.owner is not None
        ]
        self.assertEqual(len(locals_named_value), 2)
        self.assertEqual(
            len({symbol.id for symbol in locals_named_value}),
            2,
        )
        self.assertEqual(
            len({symbol.qualified_name for symbol in locals_named_value}),
            2,
        )
        self.assertTrue(
            any(
                limitation.code == "unsupported_ast"
                and "global initializer" in limitation.message
                for limitation in index.limitations
            )
        )
    def test_output_contains_derived_facts_not_proof_claims(self):
        index = extract_facts(
            "int identity(int value) { return value; }\n",
            "facts/trust.cpp",
        )
        payload = json.loads(index.to_json())
        self.assertEqual(
            {row["status"] for row in payload["purity"]},
            {"pure"},
        )
        serialized = index.to_json()
        self.assertNotIn('"verified"', serialized)
        self.assertNotIn('"proved"', serialized)
        self.assertNotIn('"unknown": false', serialized)


if __name__ == "__main__":
    unittest.main()
