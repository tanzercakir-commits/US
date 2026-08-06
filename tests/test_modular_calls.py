from pathlib import Path
import unittest

from semantic_verifier import verify_source
from semantic_verifier.backend import create_backend
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


def results_for(report, *, function, kind):
    return [
        result
        for result in report.results
        if result.function == function and result.kind == kind
    ]


class ModularCallVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def test_call_postcondition_is_substituted_into_caller_state(self):
        report = verify_source(
            "// cs: ensures result == x\n"
            "int identity(int x) { return x; }\n"
            "// cs: ensures result == x\n"
            "int caller(int x) { int q = identity(x); return q; }\n"
        )
        postcondition = results_for(
            report, function="caller", kind="postcondition"
        )[0]
        obligation = next(
            item
            for item in report.obligations
            if item.id == postcondition.obligation_id
        )

        self.assertEqual(postcondition.status.value, "verified")
        self.assertIn(
            "(q#0 == x#0)",
            [assumption.text() for assumption in obligation.assumptions],
        )
        self.assertIn(
            "(q#0 >= -2147483648)",
            [assumption.text() for assumption in obligation.assumptions],
        )

    def test_call_target_is_havoc_when_callee_has_no_ensures(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        source = (
            "int unconstrained(int x) { return x; }\n"
            "// cs: ensures result == 0\n"
            "int caller(int x) { int q = 0; q = unconstrained(x); return q; }\n"
        )
        pipeline = VerificationPipeline()
        pipeline.checker = create_backend("z3", z3=self.z3)
        report = pipeline.verify_source(source)
        postcondition = results_for(
            report, function="caller", kind="postcondition"
        )[0]
        obligation = next(
            item
            for item in report.obligations
            if item.id == postcondition.obligation_id
        )

        self.assertEqual(postcondition.status.value, "violated")
        assumptions = [item.text() for item in obligation.assumptions]
        self.assertIn("(q#0 == 0)", assumptions)
        self.assertNotIn("(q#1 == q#0)", assumptions)
        self.assertIn("q#1", postcondition.counterexample)

    def test_existing_requires_obligation_is_unchanged(self):
        report = verify_source(
            "// cs: requires x > 0\n"
            "// cs: ensures result == x\n"
            "int positive(int x) { return x; }\n"
            "int caller() { int q = positive(0); return q; }\n"
        )
        precondition = results_for(
            report, function="caller", kind="precondition"
        )[0]
        obligation = next(
            item
            for item in report.obligations
            if item.id == precondition.obligation_id
        )

        self.assertEqual(precondition.status.value, "violated")
        self.assertEqual(obligation.conclusion.text(), "(0 > 0)")
        self.assertFalse(
            any(
                "q#0" in assumption.variables()
                for assumption in obligation.assumptions
            )
        )

    def test_external_ensures_only_contract_supports_result_call(self):
        report = verify_source(
            "// cs: ensures result == x\n"
            "int external_identity(int x);\n"
            "// cs: ensures result == x\n"
            "int caller(int x) { int q = external_identity(x); return q; }\n"
        )

        self.assertFalse(
            any(result.status.value == "unsupported" for result in report.results)
        )
        caller_postcondition = results_for(
            report, function="caller", kind="postcondition"
        )[0]
        self.assertEqual(caller_postcondition.status.value, "verified")

    def test_modular_example_has_verified_chain_and_replayed_violation(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        pipeline = VerificationPipeline()
        pipeline.checker = create_backend("both", z3=self.z3)
        path = Path("examples/modular_calls.cpp")

        first = pipeline.verify_file(path)
        second = pipeline.verify_file(path)

        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(
            first.summary(),
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 0,
                "verified": 6,
                "violated": 1,
            },
        )
        precondition = results_for(
            first, function="withdraw", kind="precondition"
        )[0]
        postcondition = results_for(
            first, function="withdraw", kind="postcondition"
        )[0]
        self.assertEqual(precondition.status.value, "verified")
        self.assertEqual(postcondition.status.value, "verified")
        violation = results_for(
            first, function="unchecked_validate", kind="precondition"
        )[0]
        self.assertEqual(violation.status.value, "violated")
        self.assertIn("candidate", violation.counterexample)
        self.assertLess(violation.counterexample["candidate"], 0)


if __name__ == "__main__":
    unittest.main()
