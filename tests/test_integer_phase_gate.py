import json
from pathlib import Path
import unittest

from tools.integer_phase_gate import (
    GATE_SCHEMA,
    TRUTH_TABLE_EXPECTATIONS,
    render_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class IntegerPhaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = render_gate()
        cls.second = render_gate()
        cls.payload = json.loads(cls.first)

    def test_gate_is_deterministic_and_combined_slice_is_frozen(self):
        self.assertEqual(self.first, self.second)
        self.assertEqual(self.payload["schema"], GATE_SCHEMA)
        combined = self.payload["combined_slice"]
        self.assertEqual(combined["obligations"], 60)
        self.assertEqual(
            combined["summary"],
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 0,
                "verified": 47,
                "violated": 13,
            },
        )
        self.assertEqual(combined["violations_replayed"], 13)
        self.assertEqual(
            combined["report_sha256"],
            "8e1042bb546b60daef5090d566059165cf59c8b2a8cdbd9df1c084f001e6bab3",
        )
        self.assertEqual(
            combined["source_sha256"],
            "96e447ca9d0fd6782c66ab36c03e992f4dbac3cdb0bda75069c0388b303de704",
        )

    def test_every_operator_truth_table_row_has_bipolar_evidence(self):
        evidence = self.payload["truth_table"]

        self.assertEqual(set(evidence), set(TRUTH_TABLE_EXPECTATIONS))
        self.assertEqual(len(evidence), 8)
        for row in evidence.values():
            self.assertTrue(row["positive"])
            self.assertTrue(row["negative"])
        self.assertEqual(
            len(evidence["signed_add_subtract_multiply"]["positive"]), 3
        )
        self.assertEqual(
            len(evidence["signed_add_subtract_multiply"]["negative"]), 3
        )
        self.assertEqual(
            len(evidence["unsigned_add_subtract_multiply"]["positive"]), 3
        )

    def test_profile_classifier_and_backend_matrix_are_frozen(self):
        self.assertEqual(
            self.payload["backend_matrix"],
            {
                "affine": {"QF_BV": "unsupported", "QF_LIA": "verified"},
                "both": {"QF_BV": "unsupported", "QF_LIA": "verified"},
                "z3": {"QF_BV": "verified", "QF_LIA": "verified"},
            },
        )
        self.assertEqual(
            self.payload["classifier"]["signed_linear"], "QF_LIA"
        )
        self.assertEqual(self.payload["classifier"]["bitvector"], "QF_BV")
        self.assertEqual(
            self.payload["classifier"]["signed_linear_query_sha256"],
            "8349a6ad0890ef01701c1eadd8f793fcfcd04707314b84669ea000803beb6f02",
        )
        self.assertEqual(
            self.payload["classifier"]["bitvector_query_sha256"],
            "4a5481ae329ca95489df82fe4b8541b8749249d407e0b164b4006c37b77e4794",
        )

        profile = self.payload["target_profile"]
        self.assertEqual(set(profile["types"]), {"i32", "u32", "i64", "u64"})
        self.assertEqual(
            profile["usual_conversions"]["u32"],
            {"i32": "u32", "u32": "u32", "i64": "i64", "u64": "u64"},
        )
        self.assertEqual(
            profile["assignment_samples"]["u64_max_to_i32"], "-1"
        )
        self.assertTrue(profile["validated_by_combined_slice"])

    def test_migration_evidence_and_operations_runbook_are_complete(self):
        migration = self.payload["migration"]
        self.assertEqual(migration["archive_v1"]["entries"], 16)
        self.assertEqual(
            migration["archive_v1"]["manifest_sha256"],
            "a5be682d862ea6894d66644ce0d202ea90eb07ac46600b9b13e59ef707fbf0eb",
        )
        self.assertTrue(migration["archive_v1"]["valid"])
        self.assertEqual(migration["archive_v2"]["entries"], 28)
        self.assertEqual(
            migration["archive_v2"]["manifest_sha256"],
            "99d46062dba664de1d13e968ee93716fa6447186fb349ec0956d290b9b6a7c7c",
        )
        self.assertTrue(migration["archive_v2"]["valid"])
        self.assertEqual(migration["v1_to_v3"]["count"], 5)
        self.assertTrue(migration["v1_to_v3"]["status_equivalent"])
        self.assertEqual(migration["v2_to_v3"]["count"], 9)
        self.assertTrue(migration["v2_to_v3"]["status_equivalent"])

        operations = (ROOT / "docs" / "integer_operations.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "python tools/integer_phase_gate.py",
            "python tools/regenerate_fixtures.py --check",
            "QF_LIA",
            "QF_BV",
            "signed_left_shift",
            "codeskeptic.fixed-integer-phase-gate/v1",
        ):
            self.assertIn(required, operations)


if __name__ == "__main__":
    unittest.main()
