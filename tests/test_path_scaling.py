import json
from pathlib import Path
import unittest

from semantic_verifier.model import Expr, Obligation, SourceLocation
from tools.path_scaling_probe import (
    PROBE_SCHEMA,
    obligation_semantic_key,
    render_probe,
)


class PathScalingProbeTests(unittest.TestCase):
    def test_probe_measures_exponential_diamonds_deterministically(self):
        first = render_probe((1, 2, 4, 8))
        second = render_probe((8, 4, 2, 1))

        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["schema"], PROBE_SCHEMA)
        self.assertEqual(
            [item["assertion_obligations"] for item in payload["cases"]],
            [2, 4, 16, 256],
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
