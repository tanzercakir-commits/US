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
            "d27330e7f930043bca16b955d17b39b912f9ff345f4f260f7aab02d717fff2a9",
        )
        combined = self.payload["combined_slice"]
        self.assertEqual(
            combined["source_sha256"],
            "cf873a215439b5b052443203854137057b8a958e2914f4244fc54aa5a06aaf53",
        )
        self.assertEqual(
            combined["capable_report_sha256"],
            "61900547219d9123505f075124eaee32de04b74f35594a2ba13a660c396bf71b",
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
            "arrays": "77f4db51dc131201bdce850c38cd5be9941dc628a8be72e16a3da30761106e18",
            "bitwise_shifts": "bef9be95b2f3a8870227e4a692094daf8260594e6829571b5644bb22ca142fe4",
            "fixed_signed": "65629c6ce8d0ab8730b69ab9677a3d3414f93e1d39de3f999a7427a31ed05768",
            "fixed_unsigned": "205605dbecbf6e00b76a23fd7b0ba3fd7d48506f1fbca7505f511ab55bb7c106",
            "frames": "56a5d8f7a06b22e0d09055728a20eb174c588888b86defc1679a9c0be04df6fc",
            "references": "baeee20e50512a5d5d646e25a9d2ff76e199c82f2c5663ce786ada052c22186c",
            "value_structs": "681dad8cfdb82d9cbd2d11127db302411bd37f2f1cfe4f5f554f0605a79e2022",
        }
        actual = {
            name: row["capable_report_sha256"]
            for name, row in self.payload["backend_capability_matrix"].items()
        }
        self.assertEqual(actual, expected_hashes)
        self.assertEqual(self.payload["replay"]["violations_replayed"], 13)
        self.assertEqual(
            self.payload["replay"]["integer_gate_report_sha256"],
            "a5cfa8f7dcfaf526f9a4c4d157675e52fe7ec851e746068c344ff3932cc1ed69",
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
        for version, count in (("v1", 5), ("v2", 9), ("v3", 10), ("v4", 11), ("v5", 12)):
            evidence = migration[f"{version}_to_v6"]
            self.assertEqual(evidence["count"], count)
            self.assertTrue(evidence["status_equivalent"])

    def test_current_fixtures_regenerate_twice_and_match_committed_bytes(self):
        fixtures = self.payload["fixtures"]
        self.assertTrue(fixtures["regenerations_byte_identical"])
        self.assertEqual(fixtures["artifacts"], 28)
        self.assertEqual(
            fixtures["combined_sha256"],
            "676757a052db3c9c54122f862c7cf67c11f31717b058bfcee6005e5e77cb8344",
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
            "codeskeptic.semantic-extensions-phase-gate/v0",
            "proposal-only",
            "fail closed",
        ):
            self.assertIn(required, operations)


if __name__ == "__main__":
    unittest.main()