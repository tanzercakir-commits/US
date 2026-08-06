from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IntegerSemanticsDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = (ROOT / "docs" / "integer_semantics_decision.md").read_text(
            encoding="utf-8"
        )
        cls.plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")

    def test_decision_selects_homogeneous_lia_and_bv_lanes(self):
        for required in (
            "per-obligation homogeneous dual encoding",
            "never mix SMT `Int` and `BitVec` sorts",
            "codeskeptic.cxx17-fixed-integers/",
            "QF_LIA lane",
            "QF_BV lane",
            "Under the unchanged fail-closed cross-check policy",
        ):
            self.assertIn(required, self.decision)

    def test_truth_tables_cover_types_conversions_and_undefined_behavior(self):
        for required in (
            "`i32`",
            "`u32`",
            "`i64`",
            "`u64`",
            "18446744073709551615",
            "usual arithmetic conversions",
            "signed minimum divided/remaindered by `-1`",
            "`0 <= E2 < width`",
            "pinned arithmetic shift",
            "canonical base-10 string",
        ):
            self.assertIn(required, self.decision)

    def test_primary_references_and_implementation_stages_are_frozen(self):
        for reference in (
            "https://timsong-cpp.github.io/cppwp/n4659/basic.fundamental",
            "https://timsong-cpp.github.io/cppwp/n4659/conv.integral",
            "https://timsong-cpp.github.io/cppwp/n4659/expr.shift",
            "https://smt-lib.org/theories-FixedSizeBitVectors.shtml",
            "https://microsoft.github.io/z3guide/docs/theories/Bitvectors/",
        ):
            self.assertIn(reference, self.decision)
        for stage in range(8, 13):
            marker = f"#### A6.{stage}"
            self.assertIn(marker, self.plan)
            section = self.plan.split(marker, 1)[1].split("####", 1)[0]
            for field in ("- Goal:", "- Output/file set:", "- DoD:", "- Depends:"):
                self.assertIn(field, section)


if __name__ == "__main__":
    unittest.main()
