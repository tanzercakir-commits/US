import json
from pathlib import Path
import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.counterexample import minimize_counterexample
from semantic_verifier.model import Expr, Obligation, SCHEMA, SourceLocation
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.schema import (
    SchemaCompatibilityError,
    require_current_schema,
)
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


SOURCE = """
// cs: requires b != 0
// cs: requires !(a == -2147483648 && b == -1)
int safe_divide(int a, int b) { return a / b; }
int caller(int x, int input) { safe_divide(x, input); return 0; }
"""


def precondition_results(backend):
    pipeline = VerificationPipeline()
    pipeline.checker = backend
    report = pipeline.verify_source(SOURCE, "counterexample-quality.cpp")
    return [
        item
        for item in report.results
        if item.function == "caller" and item.kind == "precondition"
    ]


class CounterexampleMinimizationTests(unittest.TestCase):
    def test_greedy_elimination_uses_sorted_variable_order(self):
        obligation = Obligation(
            id="obl-1",
            function="f",
            kind="postcondition",
            assumptions=(),
            conclusion=Expr.boolean(False),
            location=SourceLocation("quality.cpp", 1, 1),
            description="deterministic minimization",
        )
        observed = []

        def never_proves(assumptions, _conclusion):
            observed.append(
                tuple(
                    sorted(
                        name
                        for assumption in assumptions
                        for name in assumption.variables()
                    )
                )
            )
            return False

        minimized = minimize_counterexample(
            obligation,
            {"z": 3, "a": 1, "m": 2},
            never_proves,
        )

        self.assertEqual(observed, [("m", "z"), ("a", "z"), ("a", "m")])
        self.assertEqual(list(minimized), ["a", "m", "z"])

    def test_affine_backend_removes_irrelevant_call_argument(self):
        results = precondition_results(create_backend("affine"))
        divisor_zero = next(
            item for item in results if item.counterexample == {"input": 0}
        )

        self.assertEqual(divisor_zero.status.value, "violated")
        self.assertIn("minimized from 2 to 1 bindings", divisor_zero.message)

    def test_z3_backend_removes_irrelevant_call_argument(self):
        try:
            executable = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")

        results = precondition_results(create_backend("z3", z3=executable))
        divisor_zero = next(
            item for item in results if item.counterexample == {"input": 0}
        )

        self.assertEqual(divisor_zero.status.value, "violated")
        self.assertIn("minimized from 2 to 1 bindings", divisor_zero.message)


class SchemaMigrationTests(unittest.TestCase):
    def test_current_report_schema_is_accepted(self):
        require_current_schema(
            {"schema": SCHEMA, "semantic_ir": {"schema": SCHEMA}}
        )

    def test_unknown_and_mixed_majors_are_rejected(self):
        with self.assertRaisesRegex(SchemaCompatibilityError, "unsupported"):
            require_current_schema({"schema": "codeskeptic.semantic-verification/v9"})
        with self.assertRaisesRegex(SchemaCompatibilityError, "mixed"):
            require_current_schema(
                {
                    "schema": SCHEMA,
                    "semantic_ir": {
                        "schema": "codeskeptic.semantic-verification/v0"
                    },
                }
            )

    def test_archived_fixture_bytes_remain_v0(self):
        root = Path(__file__).resolve().parents[1]
        archived = json.loads(
            (
                root
                / "fixtures"
                / "versions"
                / "v0"
                / "expected"
                / "vertical_slice.report.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(archived["schema"], "codeskeptic.semantic-verification/v0")
        self.assertEqual(SCHEMA, "codeskeptic.semantic-verification/v1")


if __name__ == "__main__":
    unittest.main()
