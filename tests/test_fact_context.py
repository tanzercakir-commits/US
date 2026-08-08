from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.fact_context import (
    CONTEXT_SCHEMA,
    DEFAULT_CONTEXT_BUDGET,
    MAX_CONTEXT_BUDGET,
    ContextBudgetError,
    build_fact_context,
    minimum_fact_context_budget,
)
from semantic_verifier.fact_queries import (
    FactWorld,
    SymbolNotFoundError,
    read_fact_index,
)


ROOT = Path(__file__).resolve().parents[1]
WORLD_PATH = ROOT / "fixtures" / "facts" / "expected" / "world.fact-index.json"
LIMITATIONS_PATH = (
    ROOT / "fixtures" / "facts" / "expected" / "limitations.fact-index.json"
)
GOLDEN = ROOT / "fixtures" / "fact_context" / "pipeline.context.json"
TOOL = ROOT / "tools" / "generate_fact_context.py"


class FactContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = FactWorld(read_fact_index(WORLD_PATH))
        cls.limited = FactWorld(read_fact_index(LIMITATIONS_PATH))

    def run_cli(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                *[str(argument) for argument in arguments],
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    def test_frozen_golden_is_canonical_ascii_and_within_2k(self):
        expected = build_fact_context(
            self.world,
            "pipeline",
            DEFAULT_CONTEXT_BUDGET,
        )
        raw = GOLDEN.read_bytes()
        self.assertEqual(raw, expected.to_json().encode("utf-8"))
        self.assertEqual(len(raw), expected.size_bytes)
        self.assertLessEqual(len(raw), 2000)
        self.assertTrue(raw.isascii())
        payload = json.loads(raw)
        self.assertEqual(payload["schema"], CONTEXT_SCHEMA)
        self.assertEqual(
            payload["budget_bytes"],
            DEFAULT_CONTEXT_BUDGET,
        )
        self.assertEqual(
            payload["provenance"]["index_id"],
            self.world.index.id,
        )
        self.assertEqual(
            payload["root"]["qualified_name"],
            "pipeline",
        )
        canonical = (
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
        self.assertEqual(raw, canonical)

    def test_ranking_keeps_root_purity_and_nearest_calls_before_farther(self):
        pack = build_fact_context(self.world, "pipeline")
        items = pack.to_dict()["items"]
        self.assertEqual(items[0]["category"], "purity")
        self.assertEqual(items[0]["distance"], 0)
        self.assertEqual(
            items[0]["value"]["status"],
            "impure",
        )
        self.assertEqual(
            [
                item["value"]["kind"]
                for item in items[1:]
            ],
            ["calls", "calls"],
        )
        self.assertEqual(
            {
                item["labels"]["target"]
                for item in items[1:]
            },
            {"math::normalize", "store"},
        )
        distances = [item["distance"] for item in items]
        self.assertEqual(distances, sorted(distances))

    def test_omission_counts_exactly_cover_ranked_candidate_window(self):
        pack = build_fact_context(self.world, "pipeline")
        payload = pack.to_dict()
        included = Counter(
            {
                "limitations": sum(
                    item["category"] == "limitation"
                    for item in payload["items"]
                ),
                "purity": sum(
                    item["category"] == "purity"
                    for item in payload["items"]
                ),
                "relations": sum(
                    item["category"] == "relation"
                    for item in payload["items"]
                ),
            }
        )

        neighborhood = self.world.neighborhood("pipeline", 8)
        identities = {
            row["symbol"]["id"]
            for row in neighborhood.answer["symbols"]
        }
        expected = {
            "limitations": len(neighborhood.limitations),
            "purity": sum(
                purity.function in identities
                for purity in self.world.index.purity
            ),
            "relations": len(neighborhood.answer["edges"]),
        }
        for category, count in expected.items():
            self.assertEqual(
                included[category] + payload["omitted"][category],
                count,
            )
        self.assertEqual(
            payload["omitted"]["total"],
            sum(payload["omitted"][key] for key in expected),
        )

    def test_every_included_item_is_an_exact_indexed_fact(self):
        pack = build_fact_context(self.world, "pipeline")
        purity = {
            json.dumps(item.to_dict(), sort_keys=True)
            for item in self.world.index.purity
        }
        limitations = {
            json.dumps(item.to_dict(), sort_keys=True)
            for item in self.world.index.limitations
        }
        relations = {
            json.dumps(item, sort_keys=True)
            for item in self.world.edges
        }
        symbols = {
            symbol.id: symbol
            for symbol in self.world.index.symbols
        }

        for item in pack.items:
            value = json.dumps(item["value"], sort_keys=True)
            if item["category"] == "purity":
                self.assertIn(value, purity)
            elif item["category"] == "limitation":
                self.assertIn(value, limitations)
            else:
                self.assertIn(value, relations)
                edge = item["value"]
                self.assertEqual(
                    item["labels"],
                    {
                        "source": symbols[
                            edge["source"]
                        ].qualified_name,
                        "target": symbols[
                            edge["target"]
                        ].qualified_name,
                    },
                )

    def test_limitations_and_unknown_purity_remain_visible_not_proof(self):
        pack = build_fact_context(self.limited, "indirect")
        payload = pack.to_dict()
        self.assertEqual(payload["items"][0]["category"], "purity")
        self.assertEqual(
            payload["items"][0]["value"]["status"],
            "unknown",
        )
        codes = {
            item["value"]["code"]
            for item in payload["items"]
            if item["category"] == "limitation"
        }
        self.assertIn("indirect_call", codes)
        text = pack.to_json()
        self.assertNotIn('"verified"', text)
        self.assertNotIn('"proved"', text)
        self.assertNotIn("source_body", text)

    def test_minimum_and_invalid_budgets_fail_or_fit_explicitly(self):
        minimum = minimum_fact_context_budget(
            self.world,
            "pipeline",
        )
        self.assertGreater(minimum, 1)
        self.assertLessEqual(minimum, MAX_CONTEXT_BUDGET)
        with self.assertRaisesRegex(
            ContextBudgetError,
            f"requires at least {minimum} bytes",
        ):
            build_fact_context(
                self.world,
                "pipeline",
                minimum - 1,
            )
        exact = build_fact_context(
            self.world,
            "pipeline",
            minimum,
        )
        self.assertLessEqual(exact.size_bytes, minimum)

        for invalid in (True, 0, -1, 2001, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContextBudgetError):
                    build_fact_context(
                        self.world,
                        "pipeline",
                        invalid,
                    )

    def test_repeated_relocated_and_exact_id_inputs_are_byte_stable(self):
        first = build_fact_context(
            self.world,
            "pipeline",
        ).to_json()
        second = build_fact_context(
            self.world,
            "pipeline",
        ).to_json()
        identity = self.world.select("pipeline").id
        by_id = build_fact_context(
            self.world,
            identity,
        ).to_json()
        self.assertEqual(first, second)
        self.assertEqual(first, by_id)

        with tempfile.TemporaryDirectory() as directory:
            relocated = Path(directory) / "relocated.json"
            shutil.copyfile(WORLD_PATH, relocated)
            other = FactWorld(read_fact_index(relocated))
            relocated_output = build_fact_context(
                other,
                "pipeline",
            ).to_json()
        self.assertEqual(first, relocated_output)

    def test_cli_generate_and_check_match_frozen_golden_without_stale_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "context.json"
            generated = self.run_cli(
                WORLD_PATH,
                "pipeline",
                output,
            )
            self.assertEqual(
                generated.returncode,
                0,
                generated.stderr,
            )
            self.assertEqual(output.read_bytes(), GOLDEN.read_bytes())

            checked = self.run_cli(
                WORLD_PATH,
                "pipeline",
                output,
                "--check",
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            before = b"stale\n"
            output.write_bytes(before)
            stale = self.run_cli(
                WORLD_PATH,
                "pipeline",
                output,
                "--check",
            )
            self.assertEqual(stale.returncode, 1)
            self.assertIn("content differs", stale.stderr)
            self.assertEqual(output.read_bytes(), before)

    def test_cli_query_budget_and_input_errors_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "context.json"
            missing = self.run_cli(
                WORLD_PATH,
                "missing",
                output,
            )
            self.assertEqual(missing.returncode, 2)
            self.assertIn("matched no symbol", missing.stderr)
            self.assertFalse(output.exists())

            budget = self.run_cli(
                WORLD_PATH,
                "pipeline",
                output,
                "--budget",
                "1",
            )
            self.assertEqual(budget.returncode, 2)
            self.assertIn("root/provenance", budget.stderr)
            self.assertFalse(output.exists())

            invalid = root / "invalid.json"
            invalid.write_text(
                '{"schema":"wrong"}\n',
                encoding="utf-8",
                newline="\n",
            )
            bad_input = self.run_cli(
                invalid,
                "pipeline",
                output,
            )
            self.assertEqual(bad_input.returncode, 3)
            self.assertIn("input error", bad_input.stderr)
            self.assertFalse(output.exists())

    def test_golden_excludes_environment_and_nondeterministic_state(self):
        text = GOLDEN.read_text(encoding="ascii")
        for marker in (
            "C:\\Projects\\US",
            "C:/Projects/US",
            "AppData",
            '"clock"',
            '"duration"',
            '"random"',
            '"model"',
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)
        with self.assertRaises(SymbolNotFoundError):
            build_fact_context(self.world, "missing")


if __name__ == "__main__":
    unittest.main()
