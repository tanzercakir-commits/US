from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from semantic_verifier.facts import (
    CALL_KINDS,
    DEFINITION_KINDS,
    FACT_SCHEMA,
    LIMITATION_CODES,
    LINKAGES,
    MUTATION_KINDS,
    PURITY_REASONS,
    PURITY_STATUSES,
    SYMBOL_KINDS,
    USE_KINDS,
    CallFact,
    DefinitionFact,
    FactIndex,
    FactIndexError,
    FactLimitation,
    FactLocation,
    FactSource,
    FactSymbol,
    MutationFact,
    PurityFact,
    UseFact,
    load_fact_index,
    load_fact_index_json,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "semantic_verifier"
    / "fact_schema"
    / "v1"
    / "index.schema.json"
)
FAKE_ID = "sha256:" + ("0" * 64)


class FactSchemaTests(unittest.TestCase):
    def make_index(self) -> FactIndex:
        source = FactSource.from_text(
            "src/world.cpp",
            "int state; int set(int x) { state = x; return state; }",
        )
        set_location = FactLocation(source.file, 1, 16)
        set_symbol = FactSymbol.create(
            kind="function",
            name="set",
            qualified_name="set",
            type="int (int)",
            linkage="external",
            owner=None,
            declaration=set_location,
            definition=set_location,
        )
        caller_location = FactLocation(source.file, 2, 1)
        caller = FactSymbol.create(
            kind="function",
            name="caller",
            qualified_name="caller",
            type="int ()",
            linkage="external",
            owner=None,
            declaration=caller_location,
            definition=caller_location,
        )
        parameter_location = FactLocation(source.file, 1, 24)
        parameter = FactSymbol.create(
            kind="parameter",
            name="x",
            qualified_name="set::x",
            type="int",
            linkage="none",
            owner=set_symbol.id,
            declaration=parameter_location,
            definition=parameter_location,
        )
        global_location = FactLocation(source.file, 1, 5)
        global_symbol = FactSymbol.create(
            kind="variable",
            name="state",
            qualified_name="state",
            type="int",
            linkage="external",
            owner=None,
            declaration=global_location,
            definition=global_location,
        )
        definitions = (
            DefinitionFact.create(
                symbol=set_symbol.id,
                context=None,
                kind="definition",
                location=set_location,
            ),
            DefinitionFact.create(
                symbol=caller.id,
                context=None,
                kind="definition",
                location=caller_location,
            ),
            DefinitionFact.create(
                symbol=parameter.id,
                context=set_symbol.id,
                kind="parameter",
                location=parameter_location,
            ),
            DefinitionFact.create(
                symbol=global_symbol.id,
                context=None,
                kind="definition",
                location=global_location,
            ),
        )
        uses = (
            UseFact.create(
                symbol=parameter.id,
                context=set_symbol.id,
                kind="read",
                location=FactLocation(source.file, 1, 37),
            ),
            UseFact.create(
                symbol=global_symbol.id,
                context=set_symbol.id,
                kind="write",
                location=FactLocation(source.file, 1, 29),
            ),
        )
        calls = (
            CallFact.create(
                caller=caller.id,
                callee=set_symbol.id,
                kind="direct",
                location=FactLocation(source.file, 2, 23),
            ),
        )
        mutations = (
            MutationFact.create(
                context=set_symbol.id,
                target=global_symbol.id,
                kind="assignment",
                location=FactLocation(source.file, 1, 35),
            ),
        )
        purity = (
            PurityFact(
                set_symbol.id,
                "impure",
                ("global_mutation",),
            ),
            PurityFact(
                caller.id,
                "impure",
                ("direct_impure_call",),
            ),
        )
        limitations = (
            FactLimitation(
                "unsupported_ast",
                "example boundary remains explicit",
                caller.id,
                FactLocation(source.file, 2, 30),
            ),
        )
        return FactIndex.create(
            source=source,
            symbols=(parameter, global_symbol, caller, set_symbol),
            definitions=definitions,
            uses=uses,
            calls=calls,
            mutations=mutations,
            purity=purity,
            limitations=limitations,
        )

    def test_machine_schema_is_versioned_and_strict(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], FACT_SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        required = {
            "calls",
            "definitions",
            "id",
            "limitations",
            "mutations",
            "purity",
            "schema",
            "source",
            "symbols",
            "uses",
        }
        self.assertEqual(set(schema["required"]), required)
        for definition in (
            "call",
            "definition",
            "limitation",
            "location",
            "mutation",
            "purity",
            "source",
            "symbol",
            "use",
        ):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])
        self.assertEqual(
            set(schema["$defs"]["symbol"]["properties"]["kind"]["enum"]),
            SYMBOL_KINDS,
        )
        self.assertEqual(
            set(schema["$defs"]["symbol"]["properties"]["linkage"]["enum"]),
            LINKAGES,
        )
        self.assertEqual(
            set(schema["$defs"]["definition"]["properties"]["kind"]["enum"]),
            DEFINITION_KINDS,
        )
        self.assertEqual(
            set(schema["$defs"]["use"]["properties"]["kind"]["enum"]),
            USE_KINDS,
        )
        self.assertEqual(
            {schema["$defs"]["call"]["properties"]["kind"]["const"]},
            CALL_KINDS,
        )
        self.assertEqual(
            set(schema["$defs"]["mutation"]["properties"]["kind"]["enum"]),
            MUTATION_KINDS,
        )
        self.assertEqual(
            set(schema["$defs"]["purity"]["properties"]["status"]["enum"]),
            PURITY_STATUSES,
        )
        self.assertEqual(
            set(
                schema["$defs"]["purity"]["properties"]["reasons"]["items"]["enum"]
            ),
            PURITY_REASONS,
        )
        self.assertEqual(
            set(schema["$defs"]["limitation"]["properties"]["code"]["enum"]),
            LIMITATION_CODES,
        )

    def test_immutable_model_round_trips_canonical_json(self):
        index = self.make_index()
        loaded = load_fact_index_json(index.to_json())
        self.assertEqual(index, loaded)
        self.assertEqual(index.to_json(), loaded.to_json())
        self.assertTrue(index.to_json().endswith("\n"))
        with self.assertRaises(FrozenInstanceError):
            index.source.file = "changed.cpp"  # type: ignore[misc]

    def test_input_array_and_reason_order_do_not_change_bytes(self):
        index = self.make_index()
        payload = deepcopy(index.to_dict())
        for field in (
            "calls",
            "definitions",
            "limitations",
            "mutations",
            "purity",
            "symbols",
            "uses",
        ):
            payload[field].reverse()
        for purity in payload["purity"]:
            purity["reasons"].reverse()
        loaded = load_fact_index(payload)
        self.assertEqual(loaded.to_json(), index.to_json())
        self.assertEqual(loaded.id, index.id)
    def test_semantic_changes_update_content_identities(self):
        index = self.make_index()
        changed_source = FactSource.from_text(
            index.source.file,
            "int state; int set(int x) { state = x + 1; return state; }",
        )
        changed = FactIndex.create(
            source=changed_source,
            symbols=index.symbols,
            definitions=index.definitions,
            uses=index.uses,
            calls=index.calls,
            mutations=index.mutations,
            purity=index.purity,
            limitations=index.limitations,
        )
        self.assertNotEqual(index.id, changed.id)

        function = next(
            symbol for symbol in index.symbols
            if symbol.kind == "function" and symbol.name == "set"
        )
        changed_symbol = FactSymbol.create(
            kind=function.kind,
            name=function.name,
            qualified_name=function.qualified_name,
            type="long (long)",
            linkage=function.linkage,
            owner=function.owner,
            declaration=function.declaration,
            definition=function.definition,
        )
        self.assertNotEqual(function.id, changed_symbol.id)

    def test_unknown_schema_fields_and_enum_values_fail_closed(self):
        index = self.make_index()
        cases = []

        unknown_root = deepcopy(index.to_dict())
        unknown_root["clock"] = 10
        cases.append(unknown_root)

        unknown_nested = deepcopy(index.to_dict())
        unknown_nested["symbols"][0]["frontend_id"] = "unstable"
        cases.append(unknown_nested)

        unknown_schema = deepcopy(index.to_dict())
        unknown_schema["schema"] = "codeskeptic.fact-index/v2"
        cases.append(unknown_schema)

        unknown_enum = deepcopy(index.to_dict())
        unknown_enum["symbols"][0]["kind"] = "namespace"
        cases.append(unknown_enum)

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(FactIndexError):
                    load_fact_index(payload)

    def test_duplicate_and_dangling_relations_fail_closed(self):
        index = self.make_index()
        duplicate = deepcopy(index.to_dict())
        duplicate["symbols"].append(deepcopy(duplicate["symbols"][0]))
        with self.assertRaisesRegex(FactIndexError, "duplicates"):
            load_fact_index(duplicate)

        use = index.uses[0]
        dangling_use = UseFact.create(
            symbol=FAKE_ID,
            context=use.context,
            kind=use.kind,
            location=use.location,
        )
        with self.assertRaisesRegex(FactIndexError, "dangling"):
            FactIndex.create(
                source=index.source,
                symbols=index.symbols,
                definitions=index.definitions,
                uses=(dangling_use,),
                calls=index.calls,
                mutations=index.mutations,
                purity=index.purity,
                limitations=index.limitations,
            )

    def test_content_identity_tampering_is_rejected(self):
        payload = deepcopy(self.make_index().to_dict())
        payload["id"] = FAKE_ID
        with self.assertRaisesRegex(FactIndexError, "index.id"):
            load_fact_index(payload)

        payload = deepcopy(self.make_index().to_dict())
        payload["uses"][0]["id"] = FAKE_ID
        with self.assertRaisesRegex(FactIndexError, "use.id"):
            load_fact_index(payload)

    def test_hash_location_and_path_validation_is_strict(self):
        with self.assertRaisesRegex(FactIndexError, "sha256"):
            FactSource("world.cpp", "c++17", "ABC")
        with self.assertRaisesRegex(FactIndexError, "positive"):
            FactLocation("world.cpp", 0, 1)
        with self.assertRaisesRegex(FactIndexError, "normalized"):
            FactLocation("src//world.cpp", 1, 1)

        source = FactSource.from_text(
            ".\\src\\world.cpp",
            "int value;",
        )
        self.assertEqual(source.file, "src/world.cpp")

    def test_symbol_owner_and_context_invariants_are_checked(self):
        index = self.make_index()
        function = next(
            symbol for symbol in index.symbols if symbol.kind == "function"
        )
        bad_parameter = FactSymbol.create(
            kind="parameter",
            name="bad",
            qualified_name="bad",
            type="int",
            linkage="none",
            owner=FAKE_ID,
            declaration=function.declaration,
            definition=function.definition,
        )
        with self.assertRaisesRegex(FactIndexError, "dangling"):
            FactIndex.create(
                source=index.source,
                symbols=(*index.symbols, bad_parameter),
                definitions=index.definitions,
                uses=index.uses,
                calls=index.calls,
                mutations=index.mutations,
                purity=index.purity,
                limitations=index.limitations,
            )

        local = next(
            symbol for symbol in index.symbols if symbol.kind == "parameter"
        )
        wrong_context = next(
            symbol
            for symbol in index.symbols
            if symbol.kind == "function" and symbol.id != local.owner
        )
        bad_definition = DefinitionFact.create(
            symbol=local.id,
            context=wrong_context.id,
            kind="parameter",
            location=local.declaration,
        )
        with self.assertRaisesRegex(FactIndexError, "context"):
            FactIndex.create(
                source=index.source,
                symbols=index.symbols,
                definitions=(bad_definition,),
                uses=index.uses,
                calls=index.calls,
                mutations=index.mutations,
                purity=index.purity,
                limitations=index.limitations,
            )

    def test_purity_is_complete_derived_tri_state_not_proof(self):
        index = self.make_index()
        self.assertEqual(
            {fact.status for fact in index.purity},
            {"impure"},
        )
        serialized = index.to_json()
        self.assertNotIn('"verified"', serialized)
        self.assertNotIn('"proved"', serialized)

        function = index.purity[0].function
        with self.assertRaisesRegex(FactIndexError, "cannot carry"):
            PurityFact(function, "pure", ("global_mutation",))
        with self.assertRaisesRegex(FactIndexError, "require a reason"):
            PurityFact(function, "unknown", ())
        with self.assertRaisesRegex(FactIndexError, "exactly one"):
            FactIndex.create(
                source=index.source,
                symbols=index.symbols,
                definitions=index.definitions,
                uses=index.uses,
                calls=index.calls,
                mutations=index.mutations,
                purity=index.purity[:1],
                limitations=index.limitations,
            )

    def test_fact_locations_cannot_escape_source_unit(self):
        index = self.make_index()
        use = index.uses[0]
        escaped = UseFact.create(
            symbol=use.symbol,
            context=use.context,
            kind=use.kind,
            location=FactLocation("other.cpp", 1, 1),
        )
        with self.assertRaisesRegex(FactIndexError, "source.file"):
            FactIndex.create(
                source=index.source,
                symbols=index.symbols,
                definitions=index.definitions,
                uses=(escaped,),
                calls=index.calls,
                mutations=index.mutations,
                purity=index.purity,
                limitations=index.limitations,
            )

    def test_non_object_or_invalid_json_is_rejected(self):
        with self.assertRaisesRegex(FactIndexError, "JSON object"):
            load_fact_index_json("[]")
        with self.assertRaisesRegex(FactIndexError, "invalid fact-index JSON"):
            load_fact_index_json("{")


if __name__ == "__main__":
    unittest.main()
