import unittest

from semantic_verifier.backend import create_backend
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


class LoopInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def verify_with_z3(self, source):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        pipeline = VerificationPipeline()
        pipeline.checker = create_backend("both", z3=self.z3)
        return pipeline.verify_source(source)

    def test_missing_invariant_is_explicitly_unsupported(self):
        report = VerificationPipeline().verify_source(
            "int f(int x) { while (x > 0) x = x - 1; return x; }\n"
        )

        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].status.value, "unsupported")
        self.assertIn("without a cs: invariant", report.results[0].message)

    def test_entry_preservation_and_exit_knowledge_verify_count_loop(self):
        report = self.verify_with_z3(
            "// cs: requires n >= 0\n"
            "// cs: ensures result == n\n"
            "int count(int n) {\n"
            "  int i = 0;\n"
            "  // cs: invariant i >= 0 && i <= n\n"
            "  while (i < n) i = i + 1;\n"
            "  return i;\n"
            "}\n"
        )

        self.assertTrue(report.results)
        self.assertTrue(
            all(result.status.value == "verified" for result in report.results)
        )
        kinds = [result.kind for result in report.results]
        self.assertIn("loop_invariant_entry", kinds)
        self.assertIn("loop_invariant_preservation", kinds)
        postcondition = next(
            obligation
            for obligation in report.obligations
            if obligation.kind == "postcondition"
        )
        assumptions = [item.text() for item in postcondition.assumptions]
        self.assertIn("((i#3 >= 0) && (i#3 <= n#0))", assumptions)
        self.assertIn("(!(i#3 < n#0))", assumptions)

    def test_false_entry_invariant_returns_counterexample(self):
        report = self.verify_with_z3(
            "int f(int n) {\n"
            "  int i = 0;\n"
            "  // cs: invariant i > 0\n"
            "  while (i < n) i = i + 1;\n"
            "  return i;\n"
            "}\n"
        )

        result = next(
            item for item in report.results if item.kind == "loop_invariant_entry"
        )
        self.assertEqual(result.status.value, "violated")
        self.assertIsNotNone(result.counterexample)

    def test_non_inductive_invariant_returns_counterexample(self):
        report = self.verify_with_z3(
            "// cs: requires n > 0\n"
            "int f(int n) {\n"
            "  int i = 0;\n"
            "  // cs: invariant i >= 0 && i < n\n"
            "  while (i < n) i = i + 1;\n"
            "  return i;\n"
            "}\n"
        )

        result = next(
            item
            for item in report.results
            if item.kind == "loop_invariant_preservation"
        )
        self.assertEqual(result.status.value, "violated")
        self.assertIsNotNone(result.counterexample)

    def test_exit_uses_invariant_not_last_body_iteration(self):
        report = self.verify_with_z3(
            "// cs: ensures result == 1\n"
            "int f(int x) {\n"
            "  // cs: invariant true\n"
            "  while (x < 1) x = 1;\n"
            "  return x;\n"
            "}\n"
        )

        result = next(
            item for item in report.results if item.kind == "postcondition"
        )
        self.assertEqual(result.status.value, "violated")
        self.assertIsNotNone(result.counterexample)
