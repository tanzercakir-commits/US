from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from semantic_verifier.model import SCHEMA
from tools.semantic_extensions_phase_gate import (
    FEATURES,
    GATE_SCHEMA,
    render_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class SemanticExtensionsPhaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render_gate()
        cls.payload = json.loads(cls.rendered)

    def test_gate_serialization_and_combined_slice_are_frozen(self):
        self.assertEqual(self.payload["schema"], GATE_SCHEMA)
        self.assertEqual(
            self.rendered,
            json.dumps(
                self.payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
        )
        self.assertEqual(
            hashlib.sha256(self.rendered.encode("utf-8")).hexdigest(),
            "f1e16132f84c1e28142358fddfc83cd33a1904cb347c30728aecb1256510e1d4",
        )
        combined = self.payload["combined_slice"]
        self.assertEqual(
            combined["source_sha256"],
            "cf873a215439b5b052443203854137057b8a958e2914f4244fc54aa5a06aaf53",
        )
        self.assertEqual(
            combined["capable_report_sha256"],
            "16b2bf4cbe8c44f0b83241f053bdaa6156cb18a61552b222c031255219dde001",
        )
        self.assertEqual(combined["capable_summary"]["verified"], 8)
        self.assertEqual(combined["default_summary"]["unsupported"], 8)

    def test_backend_capability_matrix_is_complete_and_fail_closed(self):
        matrix = self.payload["backend_capability_matrix"]
        self.assertEqual(set(matrix), set(FEATURES))
        self.assertEqual(matrix["fixed_signed"]["logic"], "QF_LIA")
        self.assertEqual(matrix["fixed_signed"]["default_summary"]["unsupported"], 0)
        for feature in set(matrix) - {"fixed_signed"}:
            self.assertEqual(matrix[feature]["capable_backend"], "z3")
            self.assertEqual(matrix[feature]["capable_summary"]["unsupported"], 0)
            self.assertGreater(matrix[feature]["default_summary"]["unsupported"], 0)
            self.assertEqual(matrix[feature]["default_summary"]["solver_error"], 0)

    def test_capable_backend_results_and_counterexamples_replay(self):
        expected_hashes = {
            "arrays": "9bdc50f234f5e94846851c288bdecc7ccfed38e8778e0eca2a38eaf482046e4d",
            "bitwise_shifts": "7ada3f0438a98d31d514dcfe1f74a45861799cd4fd6294663e7c15518ef9bf50",
            "fixed_signed": "edbe5fbcf6a7ef5ddf3911b36edd8b4b55b128761d8fe10dd23ac6619f2b549c",
            "fixed_unsigned": "4008982ba630b34ec1a061843ce26bc264f17838728fb27352b24ea4a9180cf0",
            "frames": "fce1bc263ede56b2fb8745ac809b88445beb16e32ded6cad931f96e7da103187",
            "references": "435f9d80f3d9427da1b4d6759df89168cfae365cc79584ef14a27c29612b627e",
            "value_structs": "fd23e5919a5f1056dd16c1e863e7faca4f85206a9486dd94aee4756589a1c553",
        }
        actual = {
            name: row["capable_report_sha256"]
            for name, row in self.payload["backend_capability_matrix"].items()
        }
        self.assertEqual(actual, expected_hashes)
        self.assertEqual(self.payload["replay"]["violations_replayed"], 13)
        self.assertEqual(
            self.payload["replay"]["integer_gate_report_sha256"],
            "520b8500568f66d918bb1047c84fee9dfef425c30213148f8fdb5937bdc201fb",
        )

    def test_schema_migration_and_legacy_v1_archive_are_frozen(self):
        self.assertEqual(self.payload["report_schema"], SCHEMA)
        migration = self.payload["migration"]
        self.assertTrue(migration["archive_v1"]["valid"])
        self.assertEqual(migration["archive_v1"]["entries"], 16)
        self.assertEqual(
            migration["archive_v1"]["manifest_sha256"],
            "a5be682d862ea6894d66644ce0d202ea90eb07ac46600b9b13e59ef707fbf0eb",
        )
        for version, count in (
            ("v1", 5),
            ("v2", 9),
            ("v3", 10),
            ("v4", 11),
            ("v5", 12),
            ("v6", 14),
        ):
            evidence = migration[f"{version}_to_v7"]
            self.assertEqual(evidence["count"], count)
            self.assertTrue(evidence["status_equivalent"])

    def test_current_fixtures_regenerate_twice_and_match_committed_bytes(self):
        fixtures = self.payload["fixtures"]
        self.assertTrue(fixtures["regenerations_byte_identical"])
        self.assertEqual(fixtures["artifacts"], 28)
        self.assertEqual(
            fixtures["combined_sha256"],
            "86cf127b51545bbb892f6d3743b3b653a2b5daaeffc38d6aa61b61d08eefd2d1",
        )
        self.assertIn("semantic_extensions_gate.ir", fixtures["files"])
        self.assertIn("semantic_extensions_gate.report.json", fixtures["files"])
        self.assertEqual(
            (ROOT / "examples" / "semantic_extensions_gate.cpp").read_bytes(),
            (ROOT / "fixtures" / "cases" / "semantic_extensions_gate.cpp").read_bytes(),
        )

    def test_inferred_candidates_are_independently_accepted_or_rejected(self):
        inference = self.payload["inference"]
        self.assertEqual(
            inference["artifact_sha256"],
            "e644ec4c61032510888f44d162d57bc4b72a87f16b2a067f0b3120f498fdc0e1",
        )
        self.assertTrue(inference["ordinary_referee"]["useful_inductive"])
        self.assertTrue(inference["ordinary_referee"]["useful_accepted"])
        self.assertTrue(inference["ordinary_referee"]["insufficient_inductive"])
        self.assertFalse(inference["ordinary_referee"]["insufficient_accepted"])
        self.assertEqual(inference["statuses"]["unsafe"], "no_candidate")
        self.assertEqual(inference["statuses"]["timeout"], "timeout")

    def test_negative_boundaries_are_all_explicitly_unsupported(self):
        boundary = self.payload["negative_boundary"]
        self.assertEqual(
            set(boundary),
            {"array_element_reference", "dynamic_array", "missing_frame", "pointer", "short_type"},
        )
        for evidence in boundary.values():
            summary = evidence["summary"]
            self.assertGreater(summary["unsupported"], 0)
            self.assertEqual(summary["verified"], 0)
            self.assertEqual(summary["violated"], 0)
            self.assertEqual(summary["unknown"], 0)
            self.assertEqual(summary["solver_error"], 0)
            self.assertTrue(evidence["reasons"])

    def test_operations_runbook_contains_every_gate_command_and_policy(self):
        operations = (
            ROOT / "docs" / "semantic_extensions_operations.md"
        ).read_text(encoding="utf-8")
        for required in (
            "python tools/semantic_extensions_phase_gate.py",
            "python tools/invariant_research.py --check",
            "python tools/integer_phase_gate.py",
            "python tools/regenerate_fixtures.py --check",
            "python -m unittest discover -s tests",
            "codeskeptic.semantic-extensions-phase-gate/v1",
            "proposal-only",
            "fail closed",
        ):
            self.assertIn(required, operations)


if __name__ == "__main__":
    unittest.main()
