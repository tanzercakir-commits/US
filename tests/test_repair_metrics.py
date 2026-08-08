from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.checker import AffineChecker
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.repair_bundle import load_repair_bundle_json
from semantic_verifier.repair_loop import (
    RepairLoopLog,
    load_repair_loop_json,
)
from semantic_verifier.repair_metrics import (
    REPAIR_METRIC_SCHEMA,
    RepairMetric,
    RepairMetricsError,
    append_metric,
    load_metric_json,
    load_metrics_jsonl,
    measure_repair,
    summarize_metrics,
    summary_json,
)


ROOT = Path(__file__).resolve().parents[1]
LOOP_FIXTURE = ROOT / "fixtures" / "repair_loop"
FIXTURE = ROOT / "fixtures" / "repair_metrics"
SOURCE = LOOP_FIXTURE / "source.cpp"
BUNDLE = LOOP_FIXTURE / "bundle.json"
SUCCESS = LOOP_FIXTURE / "expected.success.json"
EXHAUSTED = LOOP_FIXTURE / "expected.exhausted.json"
DISPLAY = "fixtures/repair_bundle/violated.cpp"


class RepairMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        report = VerificationPipeline(
            checker=AffineChecker(),
        ).verify_source(cls.source, DISPLAY)
        cls.bundle = load_repair_bundle_json(
            BUNDLE.read_text(encoding="utf-8"),
            source=cls.source,
            report=report,
        )
        cls.success = load_repair_loop_json(
            SUCCESS.read_text(encoding="utf-8")
        )
        cls.exhausted = load_repair_loop_json(
            EXHAUSTED.read_text(encoding="utf-8")
        )
        cls.rows = load_metrics_jsonl(
            (FIXTURE / "expected.jsonl").read_text(
                encoding="utf-8"
            )
        )

    def test_frozen_success_and_failure_rows_link_exact_artifacts(self) -> None:
        self.assertEqual(len(self.rows), 2)
        by_status = {
            row.final_status: row for row in self.rows
        }
        success = by_status["verified"]
        exhausted = by_status["exhausted"]
        self.assertEqual(success.loop, self.success.id)
        self.assertEqual(success.iterations, 1)
        self.assertEqual(success.elapsed_ns, 1000)
        self.assertTrue(success.success)
        self.assertEqual(exhausted.loop, self.exhausted.id)
        self.assertEqual(exhausted.iterations, 2)
        self.assertEqual(exhausted.elapsed_ns, 2500)
        self.assertFalse(exhausted.success)
        self.assertTrue(
            all(row.bundle == self.bundle.id for row in self.rows)
        )

    def test_from_artifacts_derives_only_loop_outcomes(self) -> None:
        row = RepairMetric.from_artifacts(
            self.bundle,
            self.success,
            17,
        )
        self.assertEqual(row.iterations, 1)
        self.assertEqual(row.final_status, "verified")
        self.assertEqual(
            row.obligation,
            self.bundle.obligation["id"],
        )
        wrong_bundle_loop = RepairLoopLog.create(
            initial_bundle="sha256:" + "0" * 64,
            initial_source_sha256=self.exhausted.initial_source_sha256,
            max_iterations=self.exhausted.max_iterations,
            attempts=self.exhausted.attempts,
            status="exhausted",
        )
        with self.assertRaises(RepairMetricsError):
            RepairMetric.from_artifacts(
                self.bundle,
                wrong_bundle_loop,
                1,
            )

    def test_metric_value_rules_reject_invalid_types_and_states(self) -> None:
        base = {
            "bundle": self.bundle.id,
            "loop": self.success.id,
            "obligation": self.bundle.obligation["id"],
            "iterations": 1,
            "success": True,
            "final_status": "verified",
            "elapsed_ns": 1,
        }
        cases = (
            {"iterations": 0},
            {"iterations": True},
            {"success": 1},
            {"final_status": "exhausted"},
            {"final_status": "unknown"},
            {"elapsed_ns": -1},
            {"elapsed_ns": True},
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaises(RepairMetricsError):
                    RepairMetric.create(**{**base, **mutation})

    def test_stale_identity_and_strict_json_fail_closed(self) -> None:
        row = self.rows[0]
        payload = row.to_dict()
        payload["id"] = "sha256:" + "0" * 64
        with self.assertRaises(RepairMetricsError):
            load_metric_json(json.dumps(payload))
        payload = row.to_dict()
        payload["extra"] = True
        with self.assertRaises(RepairMetricsError):
            load_metric_json(json.dumps(payload))
        duplicate = row.to_json_line().replace(
            '"schema":',
            '"schema":"duplicate","schema":',
            1,
        )
        with self.assertRaises(RepairMetricsError):
            load_metric_json(duplicate)

    def test_measurement_boundary_calls_clock_exactly_around_loop(self) -> None:
        events = []
        values = iter((100, 145))

        def clock():
            events.append("clock")
            return next(values)

        def run():
            events.append("run")
            return self.success

        loop, metric = measure_repair(
            run,
            self.bundle,
            clock_ns=clock,
        )
        self.assertIs(loop, self.success)
        self.assertEqual(metric.elapsed_ns, 45)
        self.assertEqual(events, ["clock", "run", "clock"])

    def test_timing_never_changes_loop_artifact_or_decision(self) -> None:
        first_loop, first = measure_repair(
            lambda: self.success,
            self.bundle,
            clock_ns=iter((0, 10)).__next__,
        )
        second_loop, second = measure_repair(
            lambda: self.success,
            self.bundle,
            clock_ns=iter((0, 999)).__next__,
        )
        self.assertEqual(
            first_loop.to_json(),
            second_loop.to_json(),
        )
        self.assertEqual(first.success, second.success)
        self.assertNotEqual(first.id, second.id)

    def test_invalid_or_backwards_clock_values_fail(self) -> None:
        clocks = (
            iter((10, 9)).__next__,
            iter((False, 1)).__next__,
            iter((0, "one")).__next__,
        )
        for clock in clocks:
            with self.subTest(clock=clock):
                with self.assertRaises(RepairMetricsError):
                    measure_repair(
                        lambda: self.success,
                        self.bundle,
                        clock_ns=clock,
                    )

    def test_append_preserves_prior_bytes_and_adds_one_canonical_line(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.jsonl"
            first, second = self.rows
            append_metric(path, first)
            prior = path.read_bytes()
            append_metric(path, second)
            actual = path.read_bytes()
            self.assertTrue(actual.startswith(prior))
            self.assertEqual(
                actual,
                (FIXTURE / "expected.jsonl").read_bytes(),
            )

    def test_duplicate_loop_and_malformed_prior_do_not_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.jsonl"
            append_metric(path, self.rows[0])
            before = path.read_bytes()
            duplicate_loop = RepairMetric.create(
                bundle=self.bundle.id,
                loop=self.rows[0].loop,
                obligation=self.bundle.obligation["id"],
                iterations=1,
                success=True,
                final_status="verified",
                elapsed_ns=999,
            )
            with self.assertRaises(RepairMetricsError):
                append_metric(path, duplicate_loop)
            self.assertEqual(path.read_bytes(), before)
            path.write_bytes(b"not-json\n")
            malformed = path.read_bytes()
            with self.assertRaises(RepairMetricsError):
                append_metric(path, self.rows[1])
            self.assertEqual(path.read_bytes(), malformed)

    def test_jsonl_requires_canonical_complete_unique_rows(self) -> None:
        text = (FIXTURE / "expected.jsonl").read_text(
            encoding="utf-8"
        )
        with self.assertRaises(RepairMetricsError):
            load_metrics_jsonl(text.rstrip("\n"))
        with self.assertRaises(RepairMetricsError):
            load_metrics_jsonl("\n")
        with self.assertRaises(RepairMetricsError):
            load_metrics_jsonl(
                self.rows[0].to_json_line() * 2
            )
        noncanonical = json.dumps(
            self.rows[0].to_dict(),
            indent=2,
        ) + "\n"
        with self.assertRaises(RepairMetricsError):
            load_metrics_jsonl(noncanonical)

    def test_summary_is_exact_and_order_independent(self) -> None:
        expected = (FIXTURE / "expected.summary.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(summary_json(self.rows), expected)
        self.assertEqual(
            summarize_metrics(tuple(reversed(self.rows))),
            summarize_metrics(self.rows),
        )

    def test_cli_summary_and_record_append_error_paths(self) -> None:
        summary = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "record_repair_metrics.py"),
                "summary",
                str(FIXTURE / "expected.jsonl"),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertEqual(
            summary.stdout,
            (FIXTURE / "expected.summary.json").read_text(
                encoding="utf-8"
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "metrics.jsonl"
            loop_output = root / "loop.json"
            command = [
                sys.executable,
                str(ROOT / "tools" / "record_repair_metrics.py"),
                "record",
                str(SOURCE),
                str(BUNDLE),
                str(LOOP_FIXTURE / "success.script.json"),
                str(loop_output),
                str(ledger),
                "--display-path",
                DISPLAY,
                "--max-iterations",
                "3",
                "--backend",
                "affine",
            ]
            recorded = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            row = load_metric_json(recorded.stdout)
            self.assertGreaterEqual(row.elapsed_ns, 0)
            self.assertEqual(
                loop_output.read_bytes(),
                SUCCESS.read_bytes(),
            )
            prior = ledger.read_bytes()
            duplicate = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertEqual(ledger.read_bytes(), prior)
            self.assertEqual(SOURCE.read_text(encoding="utf-8"), self.source)


if __name__ == "__main__":
    unittest.main()
