from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from semantic_verifier.benchmark_corpus import BenchmarkStatus
from semantic_verifier.benchmark_results import (
    BenchmarkResultError,
    BenchmarkRun,
    _canonical_line,
    load_benchmark_run_ledger,
)
from semantic_verifier.benchmark_trend import (
    BENCHMARK_TREND_SCHEMA,
    INITIAL_CALIBRATION_LABELS,
    BenchmarkTrendError,
    derive_benchmark_trend,
    load_benchmark_trend_json,
)
from tools.check_benchmark_trend import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "benchmarks" / "results" / "runs.jsonl"
TREND_PATH = ROOT / "benchmarks" / "results" / "trend.json"
REVISION = "552e2b587e8d0b837bbb85c48686b0e090396537"


class BenchmarkTrendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger_text = LEDGER_PATH.read_text(encoding="utf-8")
        cls.runs = load_benchmark_run_ledger(cls.ledger_text)
        cls.trend_text = TREND_PATH.read_text(encoding="utf-8")
        cls.trend = load_benchmark_trend_json(cls.trend_text, cls.runs)

    def make_run(
        self,
        observation: str,
        *,
        changes: dict[str, str] | None = None,
        duration_ns: int = 100,
    ) -> BenchmarkRun:
        changed = changes or {}
        cases = tuple(
            BenchmarkStatus(item.function, changed.get(item.function, item.status))
            for item in self.runs[0].cases
        )
        return BenchmarkRun.create(
            observation=observation,
            recorded_on="2026-08-07",
            source_revision=REVISION,
            corpus=self.runs[0].corpus,
            duration_ns=duration_ns,
            cases=cases,
        )

    def test_frozen_complete_trend_is_green_and_exact(self) -> None:
        self.assertEqual(len(self.runs), 3)
        self.assertEqual(
            tuple(run.observation for run in self.runs), INITIAL_CALIBRATION_LABELS
        )
        self.assertEqual(self.trend.status, "green")
        self.assertEqual(self.trend.regressions, ())
        self.assertEqual(self.trend.to_dict()["schema"], BENCHMARK_TREND_SCHEMA)
        self.assertEqual(self.trend.to_dict()["point_count"], 3)
        self.assertTrue(self.trend.id.startswith("sha256:"))
        self.assertTrue(self.trend.logic_sha256.startswith("sha256:"))
        for point in self.trend.to_dict()["points"]:
            self.assertEqual(point["counts"]["solver_error"], 0)

    def test_verified_loss_and_violated_promotion_are_red(self) -> None:
        rows = self.runs + (
            self.make_run(
                "A1.1-synthetic-regression",
                changes={
                    "bench_affine_basic_01": "unknown",
                    "bench_affine_counterexample_01": "verified",
                },
            ),
        )
        trend = derive_benchmark_trend(rows)
        self.assertEqual(trend.status, "red")
        codes = {item.code for item in trend.regressions}
        self.assertIn("verified-loss", codes)
        self.assertIn("violated-promotion", codes)

    def test_unknown_unsupported_growth_and_unreviewed_promotion_are_red(self) -> None:
        rows = self.runs + (
            self.make_run(
                "A1.1-synthetic-unknown-growth",
                changes={"bench_affine_basic_01": "unknown"},
            ),
            self.make_run(
                "A1.2-synthetic-unreviewed-promotion",
                changes={"bench_search_frontier_01": "verified"},
            ),
            self.make_run(
                "A1.3-synthetic-unsupported-growth",
                changes={"bench_affine_basic_02": "unsupported"},
            ),
        )
        trend = derive_benchmark_trend(rows)
        codes = {item.code for item in trend.regressions}
        self.assertEqual(trend.status, "red")
        self.assertIn("reviewed-baseline-required", codes)
        self.assertIn("unsupported-coverage-increased", codes)
        self.assertIn("verified-loss", codes)
        self.assertIn("unknown-coverage-increased", codes)

    def test_short_reordered_cherry_picked_and_false_calibration_fail_closed(self) -> None:
        invalid_sequences = (
            self.runs[:2],
            (self.runs[1], self.runs[0], self.runs[2]),
            (self.runs[0], self.runs[2], self.runs[1]),
            (
                self.runs[0],
                self.runs[1],
                self.make_run("f1-calibration-004"),
            ),
        )
        for rows in invalid_sequences:
            with self.assertRaises(BenchmarkTrendError):
                derive_benchmark_trend(rows)

    def test_artifact_rejects_omitted_reordered_stale_and_false_points(self) -> None:
        mutations = []
        for mutate in (
            lambda value: value["points"].pop(),
            lambda value: value["points"].reverse(),
            lambda value: value.update({"id": "sha256:" + "0" * 64}),
            lambda value: value["points"][2].update(
                {"observation": "A1.1-false-history"}
            ),
        ):
            payload = json.loads(self.trend_text)
            mutate(payload)
            mutations.append(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        for text in mutations:
            with self.assertRaises(BenchmarkTrendError):
                load_benchmark_trend_json(text, self.runs)

    def test_timing_is_displayed_but_does_not_change_logic_or_gate(self) -> None:
        fast = tuple(
            self.make_run(label, duration_ns=index + 1)
            for index, label in enumerate(INITIAL_CALIBRATION_LABELS)
        )
        slow = tuple(
            self.make_run(label, duration_ns=(index + 1) * 10_000)
            for index, label in enumerate(INITIAL_CALIBRATION_LABELS)
        )
        fast_trend = derive_benchmark_trend(fast)
        slow_trend = derive_benchmark_trend(slow)
        self.assertNotEqual(fast_trend.id, slow_trend.id)
        self.assertEqual(fast_trend.logic_sha256, slow_trend.logic_sha256)
        self.assertEqual(fast_trend.status, slow_trend.status)
        self.assertEqual(fast_trend.regressions, slow_trend.regressions)
        self.assertNotEqual(
            fast_trend.to_dict()["points"][0]["duration_ns"],
            slow_trend.to_dict()["points"][0]["duration_ns"],
        )

    def test_missing_case_and_solver_error_rows_fail_before_trending(self) -> None:
        payload = json.loads(self.runs[2].to_json_line())
        payload["cases"].pop()
        missing_case = "".join(
            run.to_json_line() for run in self.runs[:2]
        ) + _canonical_line(payload)
        with self.assertRaises(BenchmarkResultError):
            load_benchmark_run_ledger(missing_case)
        solver_error = self.ledger_text.replace(
            '"status":"unknown"', '"status":"solver_error"', 1
        )
        with self.assertRaises(BenchmarkResultError):
            load_benchmark_run_ledger(solver_error)

    def test_relocated_generation_and_check_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "relocated"
            root.mkdir()
            ledger = root / "runs.jsonl"
            artifact = root / "trend.json"
            shutil.copy2(LEDGER_PATH, ledger)
            self.assertEqual(cli_main([str(ledger), str(artifact)]), 0)
            self.assertEqual(artifact.read_bytes(), TREND_PATH.read_bytes())
            self.assertEqual(cli_main([str(ledger), str(artifact), "--check"]), 0)

    def test_loader_rejects_noncanonical_duplicate_and_carriage_return(self) -> None:
        invalid = (
            self.trend_text.rstrip("\n"),
            self.trend_text.replace("\n", "\r\n"),
            self.trend_text.replace('  "id":', '  "id":"duplicate",\n  "id":', 1),
            "\ufeff" + self.trend_text,
        )
        for text in invalid:
            with self.assertRaises(BenchmarkTrendError):
                load_benchmark_trend_json(text, self.runs)

    def test_cli_returns_green_zero_red_one_and_strict_error_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            green = root / "green.json"
            red = root / "red.json"
            red_ledger = root / "red.jsonl"
            bad_ledger = root / "bad.jsonl"
            red_rows = self.runs + (
                self.make_run(
                    "A1.1-synthetic-regression",
                    changes={"bench_affine_basic_01": "unknown"},
                ),
            )
            red_ledger.write_text(
                "".join(run.to_json_line() for run in red_rows),
                encoding="utf-8",
                newline="\n",
            )
            bad_ledger.write_text("not-json\n", encoding="utf-8", newline="\n")
            self.assertEqual(cli_main([str(LEDGER_PATH), str(green)]), 0)
            self.assertEqual(cli_main([str(red_ledger), str(red)]), 1)
            self.assertEqual(cli_main([str(bad_ledger), str(root / "bad.json")]), 2)
            green.write_text("{}\n", encoding="utf-8", newline="\n")
            self.assertEqual(
                cli_main([str(LEDGER_PATH), str(green), "--check"]), 2
            )


if __name__ == "__main__":
    unittest.main()
