import json
import unittest

from semantic_verifier import verify_source
from semantic_verifier.backend import create_backend
from semantic_verifier.dump import dump_results
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


class DeterminismTests(unittest.TestCase):
    def test_repeated_execution_is_byte_identical(self):
        source = (
            "// cs: ensures (x > 0 && result == 1) || "
            "(x <= 0 && result == 0)\n"
            "int classify(int x) { int y = 0; "
            "if (x > 0) y = 1; else y = 0; return y; }\n"
        )
        first = verify_source(source, "repeat.cpp").to_json()
        second = verify_source(source, "repeat.cpp").to_json()
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v1")
        self.assertEqual(payload["summary"]["verified"], 2)

    def test_result_order_follows_source_and_path_order(self):
        source = (
            "// cs: ensures result == x\n"
            "int identity(int x) { if (x > 0) return x; return x; }\n"
        )
        report = verify_source(source)
        self.assertEqual(
            [result.obligation_id for result in report.results],
            sorted(result.obligation_id for result in report.results),
        )


class Z3GoldenDeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def verify_vertical_slice(self, backend="z3"):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        pipeline = VerificationPipeline()
        pipeline.checker = create_backend(backend, z3=self.z3)
        return pipeline.verify_file("examples/vertical_slice.cpp")

    def test_repeated_z3_json_is_byte_identical(self):
        first = self.verify_vertical_slice().to_json()
        second = self.verify_vertical_slice().to_json()

        self.assertEqual(first, second)

    def test_repeated_cross_check_text_is_byte_identical(self):
        first = dump_results(self.verify_vertical_slice("both"))
        second = dump_results(self.verify_vertical_slice("both"))

        self.assertEqual(first, second)
        self.assertTrue(
            first.endswith(
                "summary: solver_error=0, unknown=0, unsupported=0, "
                "verified=10, violated=2\n"
            )
        )

    def test_transitive_chain_golden_result_is_verified(self):
        report = self.verify_vertical_slice()
        matches = [
            item
            for item in report.results
            if item.function == "transitive_chain" and item.kind == "postcondition"
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status.value, "verified")
        self.assertEqual(
            report.summary(),
            {
                "solver_error": 0,
                "unknown": 0,
                "unsupported": 0,
                "verified": 10,
                "violated": 2,
            },
        )
