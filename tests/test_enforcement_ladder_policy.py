from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "research" / "enforcement_ladder_policy.json"


class EnforcementLadderPolicyTests(unittest.TestCase):
    def load_policy(self):
        return json.loads(POLICY.read_text(encoding="utf-8"))

    def test_policy_shape_and_all_five_status_routes_are_frozen(self):
        policy = self.load_policy()
        self.assertEqual(
            set(policy),
            {
                "artifact_identity",
                "capability",
                "invariants",
                "routes",
                "schema",
                "states",
            },
        )
        self.assertEqual(
            policy["schema"], "codeskeptic.enforcement-ladder-policy/v1"
        )
        self.assertEqual(
            set(policy["routes"]),
            {"verified", "violated", "unknown", "unsupported", "solver_error"},
        )

    def test_only_static_verified_claims_verification(self):
        states = self.load_policy()["states"]
        claiming = {
            name for name, detail in states.items() if detail["claims_verified"]
        }
        self.assertEqual(claiming, {"static_verified"})
        self.assertIn(
            "fallback_never_promotes_to_verified",
            self.load_policy()["invariants"],
        )

    def test_unproven_routes_descend_only_when_exactly_eligible(self):
        policy = self.load_policy()
        for status in ("unknown", "unsupported"):
            route = policy["routes"][status]
            self.assertEqual(route["eligible_fallback"], "property_test")
            self.assertEqual(route["ineligible_fallback"], "manual_required")
            self.assertFalse(route["terminal_for_generation"])
        capability = policy["capability"]
        self.assertEqual(capability["predicate_policy"], "exact_owned_expression_only")
        self.assertEqual(capability["ineligible_route"], "manual_required")
        self.assertFalse(capability["eligible"]["frame_contract"])
        self.assertEqual(capability["eligible"]["required_contract"], "ensures")

    def test_defect_and_infrastructure_routes_cannot_generate_fallbacks(self):
        routes = self.load_policy()["routes"]
        self.assertTrue(routes["violated"]["requires_replay"])
        for status in ("verified", "violated", "solver_error"):
            self.assertEqual(routes[status]["fallback"], "none")
            self.assertTrue(routes[status]["terminal_for_generation"])
        self.assertEqual(routes["violated"]["state"], "defect_replayed")
        self.assertEqual(routes["solver_error"]["state"], "infrastructure_error")


if __name__ == "__main__":
    unittest.main()