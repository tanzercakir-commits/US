import json
from pathlib import Path
import unittest

from semantic_verifier import verify_source
from semantic_verifier.backend import create_backend
from semantic_verifier.counterexample import (
    minimize_counterexample,
    obligation_variable_cone,
)
from semantic_verifier.dump import dump_results
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
            conclusion=Expr.binary(
                "==",
                Expr.binary(
                    "+",
                    Expr.binary(
                        "+",
                        Expr.variable("a"),
                        Expr.variable("m"),
                    ),
                    Expr.variable("z"),
                ),
                Expr.integer(0),
            ),
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

    def test_obligation_cone_closes_transitively(self):
        x = Expr.variable("x")
        y = Expr.variable("y")
        z = Expr.variable("z")
        noise = Expr.variable("noise")
        obligation = Obligation(
            id="obl-cone",
            function="f",
            kind="postcondition",
            assumptions=(
                Expr.binary("==", x, y),
                Expr.binary("==", y, z),
                Expr.binary("==", noise, Expr.integer(0)),
            ),
            conclusion=Expr.binary(">", z, Expr.integer(0)),
            location=SourceLocation("quality.cpp", 1, 1),
            description="transitive relevance cone",
        )

        self.assertEqual(obligation_variable_cone(obligation), {"x", "y", "z"})

    def test_projection_drops_noise_even_when_greedy_prover_is_inconclusive(self):
        x = Expr.variable("x")
        noise = Expr.variable("noise")
        obligation = Obligation(
            id="obl-projection",
            function="f",
            kind="postcondition",
            assumptions=(Expr.binary(">=", noise, Expr.integer(0)),),
            conclusion=Expr.binary(">=", x, Expr.integer(0)),
            location=SourceLocation("quality.cpp", 1, 1),
            description="relevance projection",
        )

        minimized = minimize_counterexample(
            obligation,
            {"noise": 0, "x": -1},
            lambda _assumptions, _conclusion: False,
        )

        self.assertEqual(minimized, {"x": -1})

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


class CounterexampleTraceTests(unittest.TestCase):
    def test_branch_trace_is_machine_and_human_readable(self):
        report = verify_source(
            "void assert(bool);\n"
            "int traced(int x) {\n"
            "    if (x > 0) {\n"
            "        assert(x > 1);\n"
            "    }\n"
            "    return 0;\n"
            "}\n",
            "trace.cpp",
        )
        result = report.results[0]

        self.assertEqual(result.status.value, "violated")
        self.assertEqual(len(result.trace), 1)
        step = result.to_dict()["trace"][0]
        self.assertEqual(step["kind"], "branch")
        self.assertIs(step["taken"], True)
        self.assertEqual(
            step["location"],
            {"file": "trace.cpp", "line": 3, "column": 5},
        )
        self.assertEqual(step["condition"]["op"], ">")
        self.assertIn(
            "trace: when branch condition (x#0 > 0) is true at trace.cpp:3:5",
            dump_results(report),
        )

    def test_false_branch_trace_preserves_direction(self):
        report = verify_source(
            "void assert(bool);\n"
            "int traced_false(int x) {\n"
            "    if (x > 0) return 0;\n"
            "    assert(x < 0);\n"
            "    return 0;\n"
            "}\n",
            "trace-false.cpp",
        )
        result = report.results[0]

        self.assertEqual(result.counterexample, {"x": 0})
        self.assertEqual(len(result.trace), 1)
        self.assertIs(result.trace[0].taken, False)
        self.assertIn("is false at trace-false.cpp:3:5", dump_results(report))


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

    def test_archived_fixture_bytes_remain_v0_through_v3(self):
        root = Path(__file__).resolve().parents[1]
        for version in ("v0", "v1", "v2", "v3"):
            archived = json.loads(
                (
                    root
                    / "fixtures"
                    / "versions"
                    / version
                    / "expected"
                    / "vertical_slice.report.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                archived["schema"], f"codeskeptic.semantic-verification/{version}"
            )
            with self.assertRaisesRegex(SchemaCompatibilityError, "unsupported"):
                require_current_schema(archived)

        self.assertEqual(SCHEMA, "codeskeptic.semantic-verification/v4")


if __name__ == "__main__":
    unittest.main()
