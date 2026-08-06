import json
from pathlib import Path
import unittest

from tools.scaling_phase_gate import GATE_SCHEMA, render_gate


class ScalingPhaseGateTests(unittest.TestCase):
    def test_affine_gate_is_deterministic_and_meets_frozen_targets(self):
        first = render_gate(backend_name="affine", budget_checks=5)
        second = render_gate(backend_name="affine", budget_checks=5)
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(payload["schema"], GATE_SCHEMA)
        self.assertTrue(payload["cache"]["byte_identical"])
        self.assertEqual(payload["cache"]["warm_backend_calls"], 0)
        self.assertTrue(payload["budget"]["byte_identical"])
        self.assertEqual(payload["budget"]["first_backend_calls"], 5)
        self.assertEqual(payload["budget"]["second_backend_calls"], 5)
        self.assertGreater(payload["budget"]["summary"]["unknown"], 0)
        self.assertEqual(
            payload["path_probe"]["assertion_obligations"],
            [1, 1, 1, 1],
        )

    def test_operations_runbook_contains_every_phase_gate_command(self):
        root = Path(__file__).resolve().parents[1]
        runbook = (root / "docs" / "scaling_operations.md").read_text(
            encoding="utf-8"
        )
        for command in (
            "python tools/scaling_phase_gate.py --backend both",
            "python tools/path_scaling_probe.py",
            "python -m unittest discover -s tests",
            "python tools/regenerate_fixtures.py --check",
        ):
            self.assertIn(command, runbook)


if __name__ == "__main__":
    unittest.main()
