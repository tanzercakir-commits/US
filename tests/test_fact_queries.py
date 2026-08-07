from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.fact_queries import (
    AmbiguousSymbolError,
    FactQueryError,
    FactWorld,
    QUERY_SCHEMA,
    SymbolNotFoundError,
    read_fact_index,
)


ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "fixtures" / "facts" / "expected"
WORLD_PATH = FACTS / "world.fact-index.json"
LIMITATIONS_PATH = FACTS / "limitations.fact-index.json"
TOOL = ROOT / "tools" / "query_facts.py"


class FactQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = FactWorld(read_fact_index(WORLD_PATH))
        cls.limited = FactWorld(read_fact_index(LIMITATIONS_PATH))

    @staticmethod
    def symbol(world, qualified_name, type_name=None):
        matches = [
            symbol
            for symbol in world.index.symbols
            if symbol.qualified_name == qualified_name
            and (type_name is None or symbol.type == type_name)
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"expected one symbol for {qualified_name} {type_name}"
            )
        return matches[0]

    def test_who_calls_returns_sorted_callers_and_sites(self):
        result = self.world.who_calls("store")
        payload = result.to_dict()
        self.assertEqual(payload["schema"], QUERY_SCHEMA)
        self.assertEqual(payload["query"]["kind"], "who-calls")
        self.assertEqual(payload["target"]["qualified_name"], "store")
        callers = payload["answer"]["callers"]
        self.assertEqual(len(callers), 1)
        self.assertEqual(
            callers[0]["symbol"]["qualified_name"],
            "pipeline",
        )
        self.assertEqual(len(callers[0]["call_ids"]), 1)
        self.assertEqual(
            callers[0]["sites"],
            sorted(
                callers[0]["sites"],
                key=lambda site: (
                    site["file"],
                    site["line"],
                    site["column"],
                ),
            ),
        )
        self.assertEqual(payload["limitations"], [])

    def test_exact_id_disambiguates_overload_and_name_is_explicit_error(self):
        with self.assertRaises(AmbiguousSymbolError) as raised:
            self.world.who_calls("math::normalize")
        message = str(raised.exception)
        self.assertIn("int (bool)", message)
        self.assertIn("int (int)", message)
        self.assertLess(
            message.index("int (bool)"),
            message.index("int (int)"),
        )

        integer = self.symbol(
            self.world,
            "math::normalize",
            "int (int)",
        )
        result = self.world.who_calls(integer.id)
        caller_names = [
            item["symbol"]["qualified_name"]
            for item in result.answer["callers"]
        ]
        self.assertEqual(caller_names, ["pipeline", "store"])

    def test_who_mutates_storage_with_exact_mutation_evidence(self):
        global_result = self.world.who_mutates("global_total")
        global_mutators = global_result.answer["mutators"]
        self.assertEqual(len(global_mutators), 1)
        self.assertEqual(
            global_mutators[0]["symbol"]["qualified_name"],
            "store",
        )
        self.assertEqual(
            {
                mutation["kind"]
                for mutation in global_mutators[0]["mutations"]
            },
            {"compound_assignment"},
        )

        field_result = self.world.who_mutates("Counter::value")
        self.assertEqual(
            [
                item["symbol"]["qualified_name"]
                for item in field_result.answer["mutators"]
            ],
            ["store"],
        )
        self.assertEqual(
            field_result.answer["mutators"][0]["mutations"][0]["kind"],
            "assignment",
        )

    def test_empty_exact_results_succeed_and_wrong_kinds_fail(self):
        result = self.world.who_calls("scoped")
        self.assertEqual(result.answer["callers"], [])
        with self.assertRaisesRegex(FactQueryError, "expected one of function"):
            self.world.who_calls("global_total")
        with self.assertRaisesRegex(
            FactQueryError,
            "expected one of field, parameter, variable",
        ):
            self.world.who_mutates("store")
        with self.assertRaises(SymbolNotFoundError):
            self.world.who_calls("missing::function")

    def test_neighborhood_depth_zero_one_two_uses_only_exact_edges(self):
        zero = self.world.neighborhood("pipeline", 0)
        self.assertEqual(zero.answer["depth"], 0)
        self.assertEqual(len(zero.answer["symbols"]), 1)
        self.assertEqual(zero.answer["edges"], [])

        one = self.world.neighborhood("pipeline", 1)
        one_names = {
            item["symbol"]["qualified_name"]
            for item in one.answer["symbols"]
        }
        self.assertTrue(
            {
                "pipeline",
                "pipeline::counter@parameter:0",
                "pipeline::input@parameter:1",
                "store",
                "math::normalize",
            }.issubset(one_names)
        )
        self.assertTrue(
            {"calls", "defines", "owns", "uses"}.issubset(
                {edge["kind"] for edge in one.answer["edges"]}
            )
        )

        two = self.world.neighborhood("pipeline", 2)
        two_names = {
            item["symbol"]["qualified_name"]
            for item in two.answer["symbols"]
        }
        self.assertTrue(one_names.issubset(two_names))
        self.assertIn("global_total", two_names)
        self.assertIn("Counter::value", two_names)
        self.assertIn(
            "mutates",
            {edge["kind"] for edge in two.answer["edges"]},
        )
        self.assertTrue(
            all(
                0 <= item["distance"] <= 2
                for item in two.answer["symbols"]
            )
        )

    def test_neighborhood_depth_validation_is_fail_closed(self):
        for value in (-1, 9, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    FactQueryError,
                    "between 0 and 8",
                ):
                    self.world.neighborhood("pipeline", value)
    def test_results_are_byte_stable_and_keep_relevant_limitations(self):
        first = self.limited.neighborhood("indirect", 1)
        second = self.limited.neighborhood("indirect", 1)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(
            json.loads(first.to_json()),
            first.to_dict(),
        )
        self.assertTrue(
            any(
                limitation["code"] == "indirect_call"
                for limitation in first.limitations
            )
        )
        self.assertNotIn('"verified"', first.to_json())
        self.assertNotIn('"proved"', first.to_json())

    def run_cli(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(WORLD_PATH),
                *arguments,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    def test_cli_json_and_text_outputs_are_deterministic(self):
        first = self.run_cli("who-calls", "store")
        second = self.run_cli("who-calls", "store")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["schema"], QUERY_SCHEMA)
        self.assertEqual(
            payload["answer"]["callers"][0]["symbol"]["qualified_name"],
            "pipeline",
        )

        text = self.run_cli(
            "--format",
            "text",
            "who-mutates",
            "global_total",
        )
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("query: who-mutates", text.stdout)
        self.assertIn("store", text.stdout)
        self.assertEqual(text.stderr, "")

        neighborhood = self.run_cli(
            "neighborhood",
            "pipeline",
            "--depth",
            "2",
        )
        self.assertEqual(neighborhood.returncode, 0, neighborhood.stderr)
        self.assertEqual(
            json.loads(neighborhood.stdout)["answer"]["depth"],
            2,
        )

    def test_cli_query_and_input_failures_have_distinct_exit_codes(self):
        ambiguous = self.run_cli(
            "who-calls",
            "math::normalize",
        )
        self.assertEqual(ambiguous.returncode, 2)
        self.assertIn("ambiguous", ambiguous.stderr)
        self.assertEqual(ambiguous.stdout, "")

        invalid_depth = self.run_cli(
            "neighborhood",
            "pipeline",
            "--depth",
            "9",
        )
        self.assertEqual(invalid_depth.returncode, 2)
        self.assertIn("between 0 and 8", invalid_depth.stderr)

        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(
                '{"schema":"wrong"}\n',
                encoding="utf-8",
                newline="\n",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(invalid),
                    "who-calls",
                    "store",
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 3)
        self.assertIn("input error", completed.stderr)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
