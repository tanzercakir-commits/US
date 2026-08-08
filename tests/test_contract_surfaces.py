import unittest

from semantic_verifier.contract_surfaces import (
    CPP26_CONTRACT_SURFACE,
    LEGACY_CS_CONTRACT_SURFACE,
    ContractSurfaceAdapter,
    FunctionContractSurfaceRequest,
    LoopContractSurfaceRequest,
)
from semantic_verifier.cpp26_contracts import bridge_cpp26_contracts
from semantic_verifier.locations import LineMap


class ContractSurfaceAdapterTests(unittest.TestCase):
    def test_legacy_function_contracts_and_frame_are_collected(self) -> None:
        source = (
            "// cs: requires amount >= 0\n"
            "// cs: ensures result >= 0\n"
            "// cs: modifies balance\n"
            "int withdraw(int &balance, int amount);\n"
        )
        result = LEGACY_CS_CONTRACT_SURFACE.collect_function(
            FunctionContractSurfaceRequest(
                source=source,
                declaration_offset=source.index("int withdraw"),
                line_map=LineMap(source, "sample.cpp"),
                parameter_types={"balance": "i32", "amount": "i32"},
                return_type="i32",
                parameter_modes={
                    "balance": "mutable_reference",
                    "amount": "value",
                },
            )
        )

        self.assertEqual(
            [item.kind for item in result.contracts],
            ["requires", "ensures"],
        )
        self.assertEqual(result.frame.text if result.frame else None, "modifies balance")
        self.assertEqual(result.consumed_lines, (1, 2, 3))
        self.assertEqual(result.issues, ())

    def test_legacy_loop_invariant_is_collected(self) -> None:
        source = "// cs: invariant i >= 0\nwhile (i > 0) { --i; }\n"
        result = LEGACY_CS_CONTRACT_SURFACE.collect_loop(
            LoopContractSurfaceRequest(
                source=source,
                statement_offset=source.index("while"),
                line_map=LineMap(source, "loop.cpp"),
                symbol_types={"i": "i32"},
                statement_kind="WhileStmt",
            )
        )

        self.assertEqual(
            tuple(item.kind for item in result.contracts),
            ("invariant",),
        )
        self.assertEqual(result.contracts[0].expression.text(), "(i >= 0)")
        self.assertEqual(result.consumed_lines, (1,))
        self.assertEqual(result.issues, ())

    def test_cpp26_result_binding_is_lowered_and_offsets_are_owned(self) -> None:
        source = (
            "int withdraw(int amount) "
            "pre(amount >= 0) post(out: out >= 0) { return amount; }\n"
        )
        native = bridge_cpp26_contracts(source).function_contracts
        result = CPP26_CONTRACT_SURFACE.collect_function(
            FunctionContractSurfaceRequest(
                source=source,
                declaration_offset=0,
                line_map=LineMap(source, "native.cpp"),
                parameter_types={"amount": "i32"},
                return_type="i32",
                parameter_modes={"amount": "value"},
                native_contracts=native,
            )
        )

        self.assertEqual(
            tuple(item.kind for item in result.contracts),
            ("requires", "ensures"),
        )
        self.assertEqual(result.contracts[1].expression.text(), "(result >= 0)")
        self.assertEqual(
            result.consumed_native_offsets,
            tuple(item.offset for item in native),
        )
        self.assertEqual(result.issues, ())

    def test_empty_surfaces_return_the_same_neutral_result(self) -> None:
        source = "int identity(int value);\n"
        function_request = FunctionContractSurfaceRequest(
            source=source,
            declaration_offset=0,
            line_map=LineMap(source, "empty.cpp"),
            parameter_types={"value": "i32"},
            return_type="i32",
            parameter_modes={"value": "value"},
        )
        loop_request = LoopContractSurfaceRequest(
            source=source,
            statement_offset=0,
            line_map=LineMap(source, "empty.cpp"),
            symbol_types={},
            statement_kind="WhileStmt",
        )

        self.assertIsInstance(LEGACY_CS_CONTRACT_SURFACE, ContractSurfaceAdapter)
        self.assertIsInstance(CPP26_CONTRACT_SURFACE, ContractSurfaceAdapter)
        self.assertEqual(
            LEGACY_CS_CONTRACT_SURFACE.collect_function(function_request),
            CPP26_CONTRACT_SURFACE.collect_function(function_request),
        )
        self.assertEqual(
            CPP26_CONTRACT_SURFACE.collect_loop(loop_request),
            CPP26_CONTRACT_SURFACE.collect_function(function_request),
        )

    def test_malformed_legacy_contract_fails_closed_and_consumes_its_line(self) -> None:
        source = "// cs: requires amount >=\nint withdraw(int amount);\n"
        result = LEGACY_CS_CONTRACT_SURFACE.collect_function(
            FunctionContractSurfaceRequest(
                source=source,
                declaration_offset=source.index("int withdraw"),
                line_map=LineMap(source, "malformed.cpp"),
                parameter_types={"amount": "i32"},
                return_type="i32",
                parameter_modes={"amount": "value"},
            )
        )

        self.assertEqual(result.contracts, ())
        self.assertEqual(result.consumed_lines, (1,))
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].reason, "expected expression at column 10")

    def test_legacy_and_cpp26_surfaces_produce_identical_semantics(self) -> None:
        legacy_source = (
            "// cs: requires x >= 0\n"
            "// cs: ensures result >= x\n"
            "int identity(int x);\n"
        )
        native_source = (
            "int identity(const int x) "
            "pre(x >= 0) post(out: out >= x) { return x; }\n"
        )
        legacy = LEGACY_CS_CONTRACT_SURFACE.collect_function(
            FunctionContractSurfaceRequest(
                source=legacy_source,
                declaration_offset=legacy_source.index("int identity"),
                line_map=LineMap(legacy_source, "legacy.cpp"),
                parameter_types={"x": "i32"},
                return_type="i32",
                parameter_modes={"x": "value"},
            )
        )
        native_specs = bridge_cpp26_contracts(native_source).function_contracts
        native = CPP26_CONTRACT_SURFACE.collect_function(
            FunctionContractSurfaceRequest(
                source=native_source,
                declaration_offset=0,
                line_map=LineMap(native_source, "native.cpp"),
                parameter_types={"x": "i32"},
                return_type="i32",
                parameter_modes={"x": "value"},
                native_contracts=native_specs,
                const_value_parameters=frozenset({"x"}),
            )
        )

        legacy_semantics = tuple(
            (item.kind, item.expression.to_dict()) for item in legacy.contracts
        )
        native_semantics = tuple(
            (item.kind, item.expression.to_dict()) for item in native.contracts
        )
        self.assertEqual(legacy_semantics, native_semantics)
        self.assertEqual(legacy.issues, ())
        self.assertEqual(native.issues, ())


if __name__ == "__main__":
    unittest.main()
