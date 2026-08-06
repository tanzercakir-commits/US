import unittest

from semantic_verifier.contracts import (
    ContractExpressionParser,
    ContractSyntaxError,
    invariants_before,
)
from semantic_verifier.locations import LineMap


class ContractParserTests(unittest.TestCase):
    def test_parses_arithmetic_and_boolean_contract(self):
        expression = ContractExpressionParser(
            "result == balance - amount && result >= 0",
            {"result": "i32", "balance": "i32", "amount": "i32"},
        ).parse()
        self.assertEqual(expression.type, "bool")
        self.assertEqual(expression.op, "&&")

    def test_return_alias_is_canonical_result(self):
        expression = ContractExpressionParser(
            "return > x", {"result": "i32", "x": "i32"}
        ).parse()
        self.assertIn("result", expression.variables())
        self.assertNotIn("return", expression.variables())

    def test_unknown_name_is_explicit_error(self):
        with self.assertRaisesRegex(ContractSyntaxError, "unknown name"):
            ContractExpressionParser("missing != 0", {"x": "i32"}).parse()

    def test_type_mismatch_is_explicit_error(self):
        with self.assertRaisesRegex(ContractSyntaxError, "requires i32"):
            ContractExpressionParser("flag + 1 > 0", {"flag": "bool"}).parse()

    def test_parses_contiguous_invariant_block_before_while(self):
        source = (
            "// cs: invariant i >= 0\n"
            "// cs: ai invariant total >= i\n"
            "while (i < n) {}\n"
        )
        invariants, issues = invariants_before(
            source,
            source.index("while"),
            LineMap(source, "loop.cpp"),
            {"i": "i32", "n": "i32", "total": "i32"},
            "WhileStmt",
        )
        self.assertEqual(issues, ())
        self.assertEqual(
            [item.kind for item in invariants], ["invariant", "invariant"]
        )
        self.assertFalse(invariants[0].machine_proposed)
        self.assertTrue(invariants[1].machine_proposed)

    def test_invariant_does_not_expose_result_name(self):
        source = "// cs: invariant result >= 0\nwhile (true) {}\n"
        invariants, issues = invariants_before(
            source,
            source.index("while"),
            LineMap(source, "loop.cpp"),
            {},
            "WhileStmt",
        )
        self.assertEqual(invariants, ())
        self.assertIn("unknown name 'result'", issues[0].reason)

    def test_invariant_expression_must_be_boolean(self):
        source = "// cs: invariant i + 1\nwhile (true) {}\n"
        invariants, issues = invariants_before(
            source,
            source.index("while"),
            LineMap(source, "loop.cpp"),
            {"i": "i32"},
            "WhileStmt",
        )
        self.assertEqual(invariants, ())
        self.assertEqual(
            issues[0].reason, "invariant expression must be boolean"
        )

    def test_invariant_cannot_attach_to_non_while_statement(self):
        source = "// cs: invariant x > 0\nif (x) {}\n"
        invariants, issues = invariants_before(
            source,
            source.index("if"),
            LineMap(source, "branch.cpp"),
            {"x": "i32"},
            "IfStmt",
        )
        self.assertEqual(invariants, ())
        self.assertIn("only be attached to a while", issues[0].reason)
