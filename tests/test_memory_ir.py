from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import unittest

from semantic_verifier.dump import dump_module
from semantic_verifier.memory_ir import (
    MEMORY_SCHEMA,
    MemoryIRError,
    MemoryLocation,
    MemoryModel,
    MemoryObject,
    MemoryOperation,
    MemoryPathStep,
    MemoryPointer,
    MemoryRegion,
    MemoryState,
    load_memory_model_json,
    load_memory_operation_json,
)
from semantic_verifier.memory_migration import (
    MemoryMigrationError,
    V6_SCHEMA,
    migrate_v6_report_to_v7,
)
from semantic_verifier.model import (
    Expr,
    FunctionIR,
    IRNode,
    ModuleIR,
    SCHEMA,
    SourceLocation,
)
from semantic_verifier.schema import SchemaCompatibilityError, require_current_schema


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "memory_ir"
ARCHIVE = ROOT / "fixtures" / "versions" / "v6"
ZERO_HASH = "sha256:" + "0" * 64


def _memory_fixture():
    stack = MemoryRegion.create(
        kind="stack",
        owner="f",
        source_key="memory.cpp:1:1:pair",
        extent_bytes=8,
        alignment_bytes=4,
    )
    heap = MemoryRegion.create(
        kind="heap",
        owner="f",
        source_key="memory.cpp:2:1:allocation-site",
        extent_bytes=16,
        alignment_bytes=8,
    )
    root = MemoryObject.create(
        region=stack.id,
        type="record<Pair>{left:i32,right:i32}",
        extent_bytes=8,
        alignment_bytes=4,
    )
    right_step = MemoryPathStep("field", "right", "i32", 4, 4)
    right = MemoryLocation.create(
        object=root.id,
        type="i32",
        path=(right_step,),
        extent_bytes=4,
    )
    address = MemoryPointer.address_of(
        pointee="i32",
        region=stack.id,
        location=right.id,
        offset_bytes=4,
    )
    null = MemoryPointer.typed_null("i32")
    states = tuple(MemoryState.create("f", ordinal) for ordinal in range(6))
    model = MemoryModel.create(
        regions=(stack, heap),
        objects=(root,),
        locations=(right,),
        pointers=(address, null),
        states=states,
    )
    operations = (
        MemoryOperation.create(
            kind="lifetime",
            state_before=states[0].id,
            state_after=states[1].id,
            region=stack.id,
            lifetime_before="declared",
            lifetime_after="alive",
        ),
        MemoryOperation.create(
            kind="load",
            state_before=states[1].id,
            state_after=states[1].id,
            pointer=address.id,
            location=right.id,
        ),
        MemoryOperation.create(
            kind="store",
            state_before=states[1].id,
            state_after=states[2].id,
            pointer=address.id,
            location=right.id,
        ),
        MemoryOperation.create(
            kind="lifetime",
            state_before=states[2].id,
            state_after=states[3].id,
            region=stack.id,
            lifetime_before="alive",
            lifetime_after="ended",
        ),
        MemoryOperation.create(
            kind="allocation",
            state_before=states[3].id,
            state_after=states[4].id,
            region=heap.id,
            allocation_before="unallocated",
            allocation_after="allocated",
        ),
        MemoryOperation.create(
            kind="allocation",
            state_before=states[4].id,
            state_after=states[5].id,
            region=heap.id,
            allocation_before="allocated",
            allocation_after="freed",
        ),
    )
    location = SourceLocation("memory.cpp", 10, 5)
    body = (
        IRNode("n1", "memory_lifetime", location, memory=operations[0]),
        IRNode(
            "n2",
            "memory_load",
            location,
            target="right#1",
            result_type="i32",
            memory=operations[1],
        ),
        IRNode(
            "n3",
            "memory_store",
            location,
            expression=Expr.integer(7),
            memory=operations[2],
        ),
        IRNode("n4", "memory_lifetime", location, memory=operations[3]),
        IRNode("n5", "memory_allocation", location, memory=operations[4]),
        IRNode("n6", "memory_allocation", location, memory=operations[5]),
    )
    function = FunctionIR(
        id="f",
        name="memory_fixture",
        return_type="i32",
        location=SourceLocation("memory.cpp", 1, 1),
        parameters=(),
        locals=(),
        contracts=(),
        body=body,
    )
    module = ModuleIR("memory.cpp", (function,), memory=model)
    return model, module, stack, heap, root, right, address, null, states


class MemoryIRTests(unittest.TestCase):
    def test_strict_schema_declares_all_owned_values(self):
        schema = json.loads(
            (
                ROOT
                / "semantic_verifier"
                / "memory_ir_schema"
                / "v7"
                / "model.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$id"], MEMORY_SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["$defs"]["operation"]["properties"]["kind"]["enum"],
            ["allocation", "lifetime", "load", "store"],
        )
        self.assertEqual(
            schema["$defs"]["pointer"]["properties"]["kind"]["enum"],
            ["address_of", "typed_null"],
        )

    def test_model_is_frozen_canonical_and_matches_fixture(self):
        model, *_ = _memory_fixture()
        expected = (FIXTURES / "expected.memory.json").read_text(encoding="utf-8")
        self.assertEqual(model.to_json(), expected)
        self.assertEqual(load_memory_model_json(expected), model)
        unicode_region = MemoryRegion.create(
            kind="global",
            owner=None,
            source_key="bellek.cpp:1:küresel",
            extent_bytes=4,
            alignment_bytes=4,
        )
        unicode_model = MemoryModel.create(regions=(unicode_region,))
        self.assertIn("küresel", unicode_model.to_json())
        self.assertEqual(
            load_memory_model_json(unicode_model.to_json()),
            unicode_model,
        )
        with self.assertRaises(FrozenInstanceError):
            model.schema = "changed"

    def test_content_identity_and_sorting_are_input_order_independent(self):
        model, *_ = _memory_fixture()
        reordered = MemoryModel.create(
            regions=reversed(model.regions),
            objects=reversed(model.objects),
            locations=reversed(model.locations),
            pointers=reversed(model.pointers),
            states=reversed(model.states),
        )
        self.assertEqual(reordered.id, model.id)
        self.assertEqual(reordered.to_json(), model.to_json())
        with self.assertRaisesRegex(MemoryIRError, "canonical content"):
            replace(model, id=ZERO_HASH)
        with self.assertRaisesRegex(MemoryIRError, "immutable tuple"):
            replace(model, regions=list(model.regions))

    def test_typed_null_address_of_and_pointer_equality_are_explicit(self):
        model, _, _, _, _, _, address, null, _ = _memory_fixture()
        address_expr = Expr.pointer(address)
        null_expr = Expr.pointer(null)
        equality = Expr.pointer_equal(address_expr, null_expr)
        self.assertEqual(address_expr.kind, "address_of")
        self.assertEqual(null_expr.kind, "null_pointer")
        self.assertEqual(equality.type, "bool")
        self.assertEqual(equality.text(), f"(address_of({address.id}) == null<ptr<i32>>)")
        location = SourceLocation("memory.cpp", 20, 1)
        function = FunctionIR(
            "pointer-equality",
            "pointer_equality",
            "bool",
            location,
            (),
            (),
            (),
            (IRNode("n1", "return", location, expression=equality),),
        )
        ModuleIR("memory.cpp", (function,), memory=model)
        with self.assertRaisesRegex(ValueError, "same canonical pointer type"):
            Expr.pointer_equal(address_expr, Expr.pointer(MemoryPointer.typed_null("u32")))
        dangling = Expr("address_of", "ptr<i32>", value=ZERO_HASH)
        bad_function = replace(
            function,
            body=(IRNode("n1", "return", location, expression=dangling),),
        )
        with self.assertRaisesRegex(ValueError, "dangling"):
            ModuleIR("memory.cpp", (bad_function,), memory=model)

    def test_layout_provenance_and_pointer_type_fail_closed(self):
        model, _, stack, _, root, right, _, _, _ = _memory_fixture()
        outside = MemoryObject.create(
            region=stack.id,
            type="record<Big>{payload:i64}",
            extent_bytes=16,
            alignment_bytes=4,
        )
        with self.assertRaisesRegex(MemoryIRError, "outside"):
            MemoryModel.create(regions=model.regions, objects=(outside,))

        dangling = MemoryPointer.address_of(
            pointee="i32",
            region=stack.id,
            location=ZERO_HASH,
            offset_bytes=4,
        )
        with self.assertRaisesRegex(MemoryIRError, "dangling"):
            MemoryModel.create(
                regions=model.regions,
                objects=(root,),
                locations=(right,),
                pointers=(dangling,),
            )

        wrong_type = MemoryPointer.address_of(
            pointee="bool",
            region=stack.id,
            location=right.id,
            offset_bytes=4,
        )
        with self.assertRaisesRegex(MemoryIRError, "pointee type"):
            MemoryModel.create(
                regions=model.regions,
                objects=(root,),
                locations=(right,),
                pointers=(wrong_type,),
            )

    def test_memory_operations_enforce_ssa_and_transition_shapes(self):
        model, module, stack, _, _, right, address, _, states = _memory_fixture()
        operation = module.functions[0].body[0].memory
        self.assertEqual(
            load_memory_operation_json(operation.to_json()),
            operation,
        )
        changed = operation.to_dict()
        changed["unexpected"] = True
        with self.assertRaisesRegex(MemoryIRError, "fields must be exactly"):
            load_memory_operation_json(
                json.dumps(changed, indent=2, sort_keys=True) + "\n"
            )
        with self.assertRaisesRegex(MemoryIRError, "load must preserve"):
            MemoryOperation.create(
                kind="load",
                state_before=states[0].id,
                state_after=states[1].id,
                pointer=address.id,
                location=right.id,
            )
        with self.assertRaisesRegex(MemoryIRError, "store must advance"):
            MemoryOperation.create(
                kind="store",
                state_before=states[0].id,
                state_after=states[0].id,
                pointer=address.id,
                location=right.id,
            )
        stack_allocation = MemoryOperation.create(
            kind="allocation",
            state_before=states[0].id,
            state_after=states[1].id,
            region=stack.id,
            allocation_before="unallocated",
            allocation_after="allocated",
        )
        with self.assertRaisesRegex(MemoryIRError, "heap region"):
            model.validate_operation(stack_allocation)

    def test_module_serialization_and_dump_keep_memory_proof_neutral(self):
        model, module, *_ = _memory_fixture()
        payload = module.to_dict()
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["memory"], model.to_dict())
        self.assertEqual(
            dump_module(module),
            (FIXTURES / "expected.memory.ir").read_text(encoding="utf-8"),
        )
        self.assertNotIn("verified", json.dumps(payload, sort_keys=True))

    def test_empty_model_is_mandatory_for_value_only_v7_modules(self):
        module = ModuleIR("value.cpp", ())
        self.assertEqual(module.memory, MemoryModel.empty())
        self.assertEqual(set(module.to_dict()["memory"]), {
            "id", "locations", "objects", "pointers", "regions", "schema", "states"
        })

    def test_malformed_and_noncanonical_json_is_rejected(self):
        model, *_ = _memory_fixture()
        payload = model.to_dict()
        payload["unexpected"] = True
        with self.assertRaisesRegex(MemoryIRError, "fields must be exactly"):
            load_memory_model_json(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        with self.assertRaisesRegex(MemoryIRError, "not canonical"):
            load_memory_model_json(json.dumps(model.to_dict(), sort_keys=True))
        with self.assertRaisesRegex(MemoryIRError, "canonical content"):
            changed = model.to_dict()
            changed["id"] = ZERO_HASH
            load_memory_model_json(json.dumps(changed, indent=2, sort_keys=True) + "\n")


class MemoryMigrationTests(unittest.TestCase):
    def test_v6_archive_hash_manifest_is_exact(self):
        lines = (ARCHIVE / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 43)
        for line in lines:
            expected, relative = line.split("  ", 1)
            self.assertEqual(
                hashlib.sha256((ARCHIVE / relative).read_bytes()).hexdigest(),
                expected,
                relative,
            )

    def test_every_v6_value_report_migrates_exactly_to_current_v7(self):
        old_root = ARCHIVE / "expected"
        current_root = ROOT / "fixtures" / "expected"
        reports = sorted(old_root.glob("*.report.json"))
        self.assertEqual(len(reports), 14)
        for old_path in reports:
            with self.subTest(report=old_path.name):
                old = json.loads(old_path.read_text(encoding="utf-8"))
                current = json.loads(
                    (current_root / old_path.name).read_text(encoding="utf-8")
                )
                self.assertEqual(old["schema"], V6_SCHEMA)
                self.assertEqual(migrate_v6_report_to_v7(old), current)
                self.assertEqual(
                    (old_root / old_path.name.replace(".report.json", ".ir")).read_bytes(),
                    (current_root / old_path.name.replace(".report.json", ".ir")).read_bytes(),
                )

    def test_non_value_v6_artifacts_do_not_migrate(self):
        for payload in (
            {"schema": V6_SCHEMA, "memory": {}},
            {"schema": V6_SCHEMA, "semantic_ir": {"schema": V6_SCHEMA, "functions": [], "records": [], "source": "x.cpp", "unsupported": [], "memory": {}}},
            {"schema": V6_SCHEMA, "type": "ptr<i32>"},
            {"schema": V6_SCHEMA, "kind": "memory_load"},
        ):
            with self.subTest(payload=payload), self.assertRaises(MemoryMigrationError):
                migrate_v6_report_to_v7(payload)

    def test_current_gate_accepts_v7_and_rejects_v6_or_mixed(self):
        require_current_schema({"schema": SCHEMA, "semantic_ir": {"schema": SCHEMA}})
        with self.assertRaisesRegex(SchemaCompatibilityError, "unsupported"):
            require_current_schema({"schema": V6_SCHEMA})
        with self.assertRaisesRegex(SchemaCompatibilityError, "mixed"):
            require_current_schema(
                {"schema": SCHEMA, "semantic_ir": {"schema": V6_SCHEMA}}
            )


if __name__ == "__main__":
    unittest.main()
