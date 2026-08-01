import json
import unittest

from semantic_verifier import verify_source


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
        self.assertEqual(payload["schema"], "codeskeptic.semantic-verification/v0")
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
