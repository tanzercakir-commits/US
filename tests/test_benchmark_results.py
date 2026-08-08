from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.benchmark_corpus import (
    BenchmarkCorpusCheck,
    load_benchmark_corpus,
)
from semantic_verifier.benchmark_results import (
    BENCHMARK_RUN_SCHEMA,
    BENCHMARK_SUMMARY_SCHEMA,
    CONFIGURATION_SHA256,
    REFERENCE_CONFIGURATION,
    BenchmarkResultError,
    BenchmarkRun,
    _canonical_line,
    _content_id,
    append_benchmark_run,
    capture_benchmark_run,
    load_benchmark_run_json_line,
    load_benchmark_run_ledger,
    summarize_benchmark_runs,
    summary_json,
)
from tools.record_benchmark_run import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpus"
LEDGER_PATH = ROOT / "benchmarks" / "results" / "runs.jsonl"
REVISION = "f46fbdfce48934c12b2038aa8d38a78571cfa887"


class BenchmarkResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_benchmark_corpus(CORPUS_ROOT)
        cls.ledger_text = LEDGER_PATH.read_text(encoding="utf-8")
        cls.runs = load_benchmark_run_ledger(cls.ledger_text)
        cls.frozen_run = cls.runs[0]
        cls.checked = BenchmarkCorpusCheck(cls.corpus.id, cls.frozen_run.cases)

    def make_run(
        self,
        *,
        observation: str = "f1-calibration-002",
        duration_ns: int = 123,
        corpus: str | None = None,
    ) -> BenchmarkRun:
        return BenchmarkRun.create(
            observation=observation,
            recorded_on="2026-08-07",
            source_revision=REVISION,
            corpus=corpus or self.corpus.id,
            duration_ns=duration_ns,
            cases=self.frozen_run.cases,
        )

    @staticmethod
    def reidentify(payload: dict[str, object]) -> str:
        content = {key: value for key, value in payload.items() if key != "id"}
        payload["id"] = _content_id("benchmark-run", content)
        return _canonical_line(payload)

    def test_frozen_first_calibration_row_is_complete_and_exact(self) -> None:
        self.assertEqual(len(self.runs), 1)
        self.assertEqual(self.frozen_run.observation, "f1-calibration-001")
        self.assertEqual(self.frozen_run.recorded_on, "2026-08-07")
        self.assertEqual(self.frozen_run.source_revision, REVISION)
        self.assertEqual(self.frozen_run.corpus, self.corpus.id)
        self.assertGreater(self.frozen_run.duration_ns, 0)
        self.assertEqual(
            self.frozen_run.counts,
            {"unknown": 10, "unsupported": 0, "verified": 20, "violated": 10},
        )
        self.assertEqual(
            self.frozen_run.rates,
            {
                "unknown": {"denominator": 4, "numerator": 1},
                "unsupported": {"denominator": 1, "numerator": 0},
                "verified": {"denominator": 2, "numerator": 1},
                "violated": {"denominator": 4, "numerator": 1},
            },
        )
        payload = json.loads(self.ledger_text)
        self.assertEqual(payload["schema"], BENCHMARK_RUN_SCHEMA)
        self.assertEqual(payload["configuration"], REFERENCE_CONFIGURATION)
        self.assertEqual(payload["configuration_sha256"], CONFIGURATION_SHA256)

    def test_injected_timing_changes_event_but_not_logic_or_decision(self) -> None:
        def capture(values: list[int], observation: str) -> BenchmarkRun:
            iterator = iter(values)
            return capture_benchmark_run(
                self.corpus,
                observation=observation,
                recorded_on="2026-08-07",
                source_revision=REVISION,
                timer_ns=lambda: next(iterator),
                observe=lambda corpus: self.checked,
            )

        fast = capture([100, 110], "f1-calibration-002")
        slow = capture([100, 10_100], "f1-calibration-003")
        self.assertEqual((fast.duration_ns, slow.duration_ns), (10, 10_000))
        self.assertNotEqual(fast.id, slow.id)
        self.assertEqual(fast.logic_sha256, slow.logic_sha256)
        self.assertEqual(fast.logic_sha256, self.frozen_run.logic_sha256)
        self.assertEqual(fast.cases, slow.cases)
        self.assertEqual(fast.counts, slow.counts)
        self.assertEqual(fast.rates, slow.rates)

    def test_timer_and_observation_boundaries_fail_closed(self) -> None:
        for values in ([10, 9], [True, 10], [10, False]):
            iterator = iter(values)
            with self.assertRaises(BenchmarkResultError):
                capture_benchmark_run(
                    self.corpus,
                    observation="f1-calibration-002",
                    recorded_on="2026-08-07",
                    source_revision=REVISION,
                    timer_ns=lambda: next(iterator),
                    observe=lambda corpus: self.checked,
                )
        for changes in (
            {"observation": "ad-hoc"},
            {"recorded_on": "07-08-2026"},
            {"source_revision": "f46fbdf"},
            {"duration_ns": True},
        ):
            with self.assertRaises(BenchmarkResultError):
                BenchmarkRun.create(
                    observation=changes.get("observation", "f1-calibration-002"),
                    recorded_on=changes.get("recorded_on", "2026-08-07"),
                    source_revision=changes.get("source_revision", REVISION),
                    corpus=self.corpus.id,
                    duration_ns=changes.get("duration_ns", 1),
                    cases=self.frozen_run.cases,
                )

    def test_append_preserves_prefix_and_rejects_duplicate_or_mixed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "runs.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(self.ledger_text, encoding="utf-8", newline="\n")
            prefix = path.read_bytes()
            second = self.make_run()
            append_benchmark_run(path, second)
            self.assertTrue(path.read_bytes().startswith(prefix))
            self.assertEqual(load_benchmark_run_ledger(path.read_text(encoding="utf-8")), (self.frozen_run, second))
            with self.assertRaises(BenchmarkResultError):
                append_benchmark_run(path, second)
            duplicate_label = replace(second, id=second.id)
            with self.assertRaises(BenchmarkResultError):
                append_benchmark_run(path, duplicate_label)
            mixed = self.make_run(
                observation="f1-calibration-003",
                corpus="sha256:" + "0" * 64,
            )
            with self.assertRaises(BenchmarkResultError):
                append_benchmark_run(path, mixed)

    def test_loader_rejects_counts_rates_logic_configuration_and_case_tamper(self) -> None:
        payloads = []
        for mutate in (
            lambda value: value["counts"].update({"verified": 19}),
            lambda value: value["rates"].update(
                {"verified": {"denominator": 1, "numerator": 1}}
            ),
            lambda value: value.update({"logic_sha256": "sha256:" + "0" * 64}),
            lambda value: value["configuration"].update({"checker": "other"}),
            lambda value: value["cases"].pop(),
            lambda value: value["cases"].reverse(),
            lambda value: value.update({"duration_ns": True}),
        ):
            payload = json.loads(self.ledger_text)
            mutate(payload)
            payloads.append(payload)
        for payload in payloads:
            with self.assertRaises(BenchmarkResultError):
                load_benchmark_run_json_line(self.reidentify(payload))

    def test_ledger_rejects_truncation_blank_duplicate_bom_and_carriage_return(self) -> None:
        invalid = (
            self.ledger_text.rstrip("\n"),
            self.ledger_text + "\n",
            self.ledger_text + self.ledger_text,
            "\ufeff" + self.ledger_text,
            self.ledger_text.replace("\n", "\r\n"),
            self.ledger_text.replace('"id":', '"id":"duplicate","id":', 1),
        )
        for text in invalid:
            with self.assertRaises(BenchmarkResultError):
                load_benchmark_run_ledger(text)

    def test_summary_separates_logical_points_from_informational_timing(self) -> None:
        second = self.make_run(duration_ns=999)
        summary = summarize_benchmark_runs((self.frozen_run, second))
        self.assertEqual(summary["schema"], BENCHMARK_SUMMARY_SCHEMA)
        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(
            [item["logic_sha256"] for item in summary["logical_points"]],
            [self.frozen_run.logic_sha256, self.frozen_run.logic_sha256],
        )
        self.assertEqual(
            [item["duration_ns"] for item in summary["timing_ns"]],
            [self.frozen_run.duration_ns, 999],
        )
        changed = self.make_run(duration_ns=1234)
        self.assertEqual(changed.logic_sha256, second.logic_sha256)
        self.assertEqual(changed.counts, second.counts)

    def test_relocated_ledger_loads_to_identical_summary_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "relocated" / "runs.jsonl"
            target.parent.mkdir(parents=True)
            shutil.copy2(LEDGER_PATH, target)
            relocated = load_benchmark_run_ledger(target.read_text(encoding="utf-8"))
            self.assertEqual(summary_json(relocated), summary_json(self.runs))

    def test_cli_record_summarize_duplicate_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "runs.jsonl"
            run = self.make_run()
            arguments = [
                "record",
                str(CORPUS_ROOT),
                str(ledger),
                "--observation",
                run.observation,
                "--recorded-on",
                run.recorded_on,
                "--source-revision",
                run.source_revision,
            ]
            with patch("tools.record_benchmark_run.capture_benchmark_run", return_value=run):
                self.assertEqual(cli_main(arguments), 0)
                self.assertEqual(cli_main(arguments), 2)
            self.assertEqual(cli_main(["summarize", str(ledger)]), 0)
            self.assertEqual(cli_main(["summarize", str(Path(directory) / "missing")]), 2)


if __name__ == "__main__":
    unittest.main()
