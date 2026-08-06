import json
from pathlib import Path
import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.frontend import ClangJsonFrontend
from semantic_verifier.lowering import SemanticLowerer
from semantic_verifier.model import Expr, Obligation, SourceLocation
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.vc import VerificationConditionGenerator
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3
from tools.path_scaling_probe import (
    PROBE_SCHEMA,
    obligation_semantic_key,
    render_probe,
)


class _UnmergedVerificationConditionGenerator(VerificationConditionGenerator):
    @staticmethod
    def _compact_states(states):
        return states


class PathScalingProbeTests(unittest.TestCase):
    def test_probe_measures_exponential_diamonds_deterministically(self):
        first = render_probe((1, 2, 4, 8))
        second = render_probe((8, 4, 2, 1))

        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["schema"], PROBE_SCHEMA)
        self.assertEqual(
            [item["assertion_obligations"] for item in payload["cases"]],
            [1, 1, 1, 1],
        )
        self.assertEqual(
            [item["expected_paths"] for item in payload["cases"]],
            [2, 4, 16, 256],
        )
        self.assertTrue(
            all(item["duplicate_obligations"] == 0 for item in payload["cases"])
        )

    def test_decision_records_measurement_and_required_implementation(self):
        root = Path(__file__).resolve().parents[1]
        decision = (root / "docs" / "path_scaling_decision.md").read_text(
            encoding="utf-8"
        )

        for required in (
            "codeskeptic.path-scaling-probe/v0",
            "2/4/16/256",
            "zero exact duplicate obligations",
            "A5.5",
            "guarded trace templates",
        ):
            self.assertIn(required, decision)

    def test_compaction_matches_unmerged_nested_and_assignment_diamonds(self):
        try:
            executable = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")

        cases = (
            (
                "void assert(bool);\n"
                "int nested(bool b0, bool b1) { int y = 0; "
                "if (b0) { if (b1) y = 1; else y = 2; } else y = 3; "
                "assert(y > 1); return y; }\n",
                3,
                "violated",
            ),
            (
                "void assert(bool);\n"
                "int assigned(int x, bool b) { int y = x; "
                "if (b) y = x; else y = x; "
                "assert(y == x); return y; }\n",
                2,
                "verified",
            ),
        )
        frontend = ClangJsonFrontend()
        for source, unmerged_count, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                unit = frontend.parse_source(source, display_path="merge.cpp")
                module = SemanticLowerer(unit).lower()

                compact_obligations = VerificationConditionGenerator(
                    module
                ).generate()
                unmerged_obligations = _UnmergedVerificationConditionGenerator(
                    module
                ).generate()
                compact = create_backend("z3", z3=executable).check_all(
                    compact_obligations
                )
                unmerged = create_backend("z3", z3=executable).check_all(
                    unmerged_obligations
                )
                compact_assertions = [
                    result
                    for obligation, result in zip(compact_obligations, compact)
                    if obligation.kind == "assertion"
                ]
                unmerged_assertions = [
                    result
                    for obligation, result in zip(unmerged_obligations, unmerged)
                    if obligation.kind == "assertion"
                ]

                self.assertEqual(len(compact_assertions), 1)
                self.assertEqual(len(unmerged_assertions), unmerged_count)
                self.assertEqual(compact_assertions[0].status.value, expected_status)
                if expected_status == "verified":
                    self.assertTrue(
                        all(item.status.value == "verified" for item in unmerged_assertions)
                    )
                else:
                    self.assertTrue(
                        any(item.status.value == "violated" for item in unmerged_assertions)
                    )
                    self.assertEqual(
                        [step.taken for step in compact_assertions[0].trace],
                        [True, True],
                    )

    def test_replayed_models_resolve_post_join_trace_direction(self):
        try:
            executable = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")

        for taken, assignments in (
            (True, "if (b) y = 0; else y = 1;"),
            (False, "if (b) y = 1; else y = 0;"),
        ):
            with self.subTest(taken=taken):
                source = (
                    "void assert(bool);\n"
                    "int direction(bool b) { int y = 1; "
                    f"{assignments} assert(y > 0); return y; }}\n"
                )
                pipeline = VerificationPipeline()
                pipeline.checker = create_backend("z3", z3=executable)
                report = pipeline.verify_source(source, "direction.cpp")
                assertion = next(
                    result
                    for obligation, result in zip(report.obligations, report.results)
                    if obligation.kind == "assertion"
                )

                self.assertEqual(assertion.status.value, "violated")
                self.assertEqual(len(assertion.trace), 1)
                self.assertIs(assertion.trace[0].taken, taken)

    def test_semantic_key_normalizes_assumption_order_only(self):
        location = SourceLocation("probe.cpp", 1, 1)
        x = Expr.variable("x")
        lower = Expr.binary(">=", x, Expr.integer(0))
        upper = Expr.binary("<=", x, Expr.integer(10))

        def obligation(assumptions, conclusion=upper):
            return Obligation(
                id="ignored",
                function="ignored",
                kind="postcondition",
                assumptions=assumptions,
                conclusion=conclusion,
                location=location,
                description="ignored metadata",
            )

        self.assertEqual(
            obligation_semantic_key(obligation((lower, upper))),
            obligation_semantic_key(obligation((upper, lower))),
        )
        self.assertNotEqual(
            obligation_semantic_key(obligation((lower, upper))),
            obligation_semantic_key(obligation((lower,), Expr.boolean(True))),
        )


if __name__ == "__main__":
    unittest.main()
