import unittest

from semantic_verifier.contracts import (
    ContractExpressionParser,
    ContractSyntaxError,
)


class ContractParserTests(unittest.TestCase):
    def test_parses_arithmetic_and_boolean_contract(self):
        expression = ContractExpressionParser(
            "result == balance - amount && result >= 0",
            {"result": "int", "balance": "int", "amount": "int"},
        ).parse()
        self.assertEqual(expression.type, "bool")
        self.assertEqual(expression.op, "&&")

    def test_return_alias_is_canonical_result(self):
        expression = ContractExpressionParser(
            "return > x", {"result": "int", "x": "int"}
        ).parse()
        self.assertIn("result", expression.variables())
        self.assertNotIn("return", expression.variables())

    def test_unknown_name_is_explicit_error(self):
        with self.assertRaisesRegex(ContractSyntaxError, "unknown name"):
            ContractExpressionParser("missing != 0", {"x": "int"}).parse()

    def test_type_mismatch_is_explicit_error(self):
        with self.assertRaisesRegex(ContractSyntaxError, "requires int"):
            ContractExpressionParser("flag + 1 > 0", {"flag": "bool"}).parse()
