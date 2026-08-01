import unittest

from semantic_verifier import verify_source
from semantic_verifier.checker import DeterministicChecker
from semantic_verifier.model import Expr, Obligation, SourceLocation


def results_for(report, *, kind):
    return [result for result in report.results if result.kind == kind]


class ContractConsistencyTests(unittest.TestCase):
    def test_declaration_only_stored_error_is_reported(self):
        report = verify_source(
            "// cs: requires result == 0\n"
            "int f(int x);\n"
        )

        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("unknown name 'result'", report.results[0].message)

    def test_declaration_only_unsupported_contract_logic_is_reported(self):
        report = verify_source(
            "// cs: ensures 0 * (1 / 0) == 0\n"
            "int f();\n"
        )

        result = results_for(report, kind="contract_well_formed")[0]
        self.assertEqual(result.status.value, "unsupported")

    def test_supported_external_postcondition_has_fragment_result(self):
        report = verify_source(
            "// cs: ensures result >= x\n"
            "int f(int x);\n"
        )

        result = results_for(report, kind="contract_well_formed")[0]
        self.assertEqual(result.status.value, "verified")

    def test_contradictory_requirements_have_consistency_violation(self):
        report = verify_source(
            "// cs: requires x != x\n"
            "// cs: ensures result == 123\n"
            "int f(int x) { return 0; }\n"
        )

        result = results_for(report, kind="contract_consistency")[0]
        self.assertEqual(result.status.value, "violated")
        self.assertNotIn("counterexample", result.to_dict())
        obligation = next(
            item for item in report.obligations if item.kind == "contract_consistency"
        )
        self.assertEqual(obligation.mode, "satisfiable")
        self.assertGreaterEqual(report.summary()["violated"], 1)

    def test_satisfiability_mode_verified_and_unknown(self):
        location = SourceLocation("contract.cpp", 1, 1)
        x = Expr.variable("x#0", "int")
        verified = Obligation(
            id="ob1",
            function="f",
            kind="contract_consistency",
            assumptions=(Expr.binary("==", x, Expr.integer(1), "bool"),),
            conclusion=None,
            location=location,
            description="consistent",
            mode="satisfiable",
        )
        unknown = Obligation(
            id="ob2",
            function="g",
            kind="contract_consistency",
            assumptions=(
                Expr.binary(
                    "==",
                    Expr.binary("*", Expr.integer(100), x, "int"),
                    Expr.integer(5000),
                    "bool",
                ),
            ),
            conclusion=None,
            location=location,
            description="search does not contain x = 50",
            mode="satisfiable",
        )

        checker = DeterministicChecker()
        self.assertEqual(checker.check(verified).status.value, "verified")
        self.assertEqual(checker.check(unknown).status.value, "unknown")

    def test_infeasible_fallthrough_path_is_discharged(self):
        report = verify_source("int f() { if (true) return 0; }\n")

        result = results_for(report, kind="missing_return")[0]
        self.assertEqual(result.status.value, "verified")

    def test_reachable_fallthrough_is_a_concrete_violation(self):
        report = verify_source("int f() {}\n")

        result = results_for(report, kind="missing_return")[0]
        self.assertEqual(result.status.value, "violated")
        payload = result.to_dict()
        self.assertIn("counterexample", payload)
        self.assertEqual(payload["counterexample"], {})


if __name__ == "__main__":
    unittest.main()
