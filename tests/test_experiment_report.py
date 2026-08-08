from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.experiment_corpus import (
    ExperimentCorpusError,
    load_experiment_corpus,
)
from semantic_verifier.experiment_e2 import (
    ARM_COMPILER,
    ARM_SEMANTIC,
    ExperimentTrials,
    load_experiment_inputs,
    load_experiment_trials_json,
)
from semantic_verifier.experiment_report import (
    LIMITATIONS,
    ExactRational,
    ExperimentReportError,
    build_experiment_report,
    exact_median,
    load_experiment_report_json,
)
from tools.report_experiment_e2 import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "benchmarks" / "experiment_e2"
CORPUS_ROOT = EXPERIMENT_ROOT / "corpus"
CONTEXT_ROOT = EXPERIMENT_ROOT / "contexts"
PROPOSAL_ROOT = EXPERIMENT_ROOT / "proposals"
TRIAL_PATH = EXPERIMENT_ROOT / "results" / "trials.json"
REPORT_PATH = EXPERIMENT_ROOT / "results" / "report.json"
TOOL = ROOT / "tools" / "report_experiment_e2.py"


class ExperimentReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_experiment_corpus(CORPUS_ROOT)
        cls.inputs = load_experiment_inputs(
            cls.corpus,
            CONTEXT_ROOT,
            PROPOSAL_ROOT,
        )
        cls.trials = load_experiment_trials_json(
            TRIAL_PATH.read_text(encoding="utf-8"),
            cls.inputs,
        )
        cls.report_text = REPORT_PATH.read_text(encoding="utf-8")
        cls.report = load_experiment_report_json(
            cls.report_text,
            cls.trials,
        )

    def test_frozen_report_is_exact_complete_recomputation(self) -> None:
        rebuilt = build_experiment_report(self.trials)
        self.assertEqual(rebuilt, self.report)
        self.assertEqual(rebuilt.to_json(), self.report_text)
        self.assertEqual(self.report.corpus, self.trials.corpus)
        self.assertEqual(self.report.trials, self.trials.id)
        self.assertTrue(self.report.id.startswith("sha256:"))

    def test_predeclared_medians_improvement_and_outcome_are_exact(self) -> None:
        self.assertEqual(self.report.threshold, ExactRational(2, 5))
        self.assertEqual(self.report.arms[0].median, ExactRational(7, 2))
        self.assertEqual(self.report.arms[1].median, ExactRational(1, 1))
        self.assertEqual(self.report.improvement, ExactRational(5, 7))
        self.assertEqual(self.report.outcome, "passed")
        self.assertGreaterEqual(
            self.report.improvement.fraction(),
            self.report.threshold.fraction(),
        )

    def test_arm_summaries_include_every_censored_score(self) -> None:
        compiler, semantic = self.report.arms
        self.assertEqual(compiler.arm, ARM_COMPILER)
        self.assertEqual(compiler.succeeded, 16)
        self.assertEqual(compiler.exhausted, 4)
        self.assertEqual(
            compiler.scores,
            (5,) * 4 + (4,) * 6 + (3,) * 5 + (2,) * 3 + (1,) * 2,
        )
        self.assertEqual(semantic.arm, ARM_SEMANTIC)
        self.assertEqual(semantic.succeeded, 20)
        self.assertEqual(semantic.exhausted, 0)
        self.assertEqual(semantic.scores, (1,) * 20)

    def test_all_twenty_pairs_trace_exact_trial_and_loop_ids(self) -> None:
        self.assertEqual(len(self.report.pairs), 20)
        rows = {(row.case, row.arm): row for row in self.trials.trials}
        for pair in self.report.pairs:
            compiler = rows[(pair.case, ARM_COMPILER)]
            semantic = rows[(pair.case, ARM_SEMANTIC)]
            self.assertEqual(pair.compiler_trial, compiler.id)
            self.assertEqual(pair.semantic_trial, semantic.id)
            self.assertEqual(pair.compiler_loop, compiler.loop.id)
            self.assertEqual(pair.semantic_loop, semantic.loop.id)
            self.assertEqual(pair.compiler_score, compiler.score)
            self.assertEqual(pair.semantic_score, semantic.score)
            self.assertEqual(pair.delta, compiler.score - semantic.score)

    def test_exhausted_cases_are_not_filtered_from_primary_population(self) -> None:
        exhausted = [
            pair for pair in self.report.pairs
            if pair.compiler_score == 5
        ]
        self.assertEqual(
            [pair.case for pair in exhausted],
            [f"e2-case-{index:02d}" for index in range(1, 5)],
        )
        self.assertEqual(len(self.report.pairs), 20)

    def test_provenance_and_limitations_bound_the_claim(self) -> None:
        self.assertEqual(self.report.proposer, self.trials.proposer)
        self.assertEqual(
            self.report.evidence_scope,
            "recorded-scripted-proxy",
        )
        self.assertEqual(self.report.limitations, LIMITATIONS)
        rendered = " ".join(self.report.limitations).lower()
        self.assertIn("does not establish consciousness", rendered)
        self.assertIn("does not measure an independently sampled ai model", rendered)
        self.assertIn("does not establish", rendered)
        self.assertIn("causality", rendered)

    def test_reversed_trial_input_produces_identical_report_bytes(self) -> None:
        reordered = ExperimentTrials.create(
            self.corpus,
            tuple(reversed(self.trials.trials)),
        )
        self.assertEqual(reordered.id, self.trials.id)
        self.assertEqual(
            build_experiment_report(reordered).to_json(),
            self.report_text,
        )

    def test_numeric_threshold_median_improvement_and_outcome_tamper_fail(self) -> None:
        mutations = (
            lambda value: value["hypothesis"]["semantic_bundle_reduction_threshold"].update({"numerator": 1}),
            lambda value: value["arms"][ARM_COMPILER]["median"].update({"numerator": 3}),
            lambda value: value["improvement"].update({"numerator": 1}),
            lambda value: value.update({"outcome": "failed"}),
            lambda value: value["arms"][ARM_COMPILER]["scores"].__setitem__(0, 4),
            lambda value: value["pairs"][0].update({"delta": 0}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = json.loads(self.report_text)
                mutate(payload)
                with self.assertRaises(ExperimentReportError):
                    load_experiment_report_json(json.dumps(payload), self.trials)

    def test_corpus_trial_proposer_scope_pair_trace_and_limit_tamper_fail(self) -> None:
        mutations = (
            lambda value: value.update({"corpus": "sha256:" + "0" * 64}),
            lambda value: value.update({"trials": "sha256:" + "0" * 64}),
            lambda value: value.update({"proposer": "other"}),
            lambda value: value.update({"evidence_scope": "other"}),
            lambda value: value["pairs"][0].update({"compiler_trial": "sha256:" + "0" * 64}),
            lambda value: value["limitations"].pop(),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = json.loads(self.report_text)
                mutate(payload)
                with self.assertRaises(ExperimentReportError):
                    load_experiment_report_json(json.dumps(payload), self.trials)

    def test_report_json_rejects_bool_unknown_schema_duplicate_and_nonfinite(self) -> None:
        payload = json.loads(self.report_text)
        payload["improvement"]["numerator"] = True
        with self.assertRaises(ExperimentReportError):
            load_experiment_report_json(json.dumps(payload), self.trials)
        payload = json.loads(self.report_text)
        payload["unknown"] = 1
        with self.assertRaises(ExperimentReportError):
            load_experiment_report_json(json.dumps(payload), self.trials)
        payload = json.loads(self.report_text)
        payload["schema"] = "future"
        with self.assertRaises(ExperimentReportError):
            load_experiment_report_json(json.dumps(payload), self.trials)
        duplicate = self.report_text.replace(
            '  "corpus":',
            '  "corpus": "sha256:' + "0" * 64 + '",\n  "corpus":',
            1,
        )
        with self.assertRaises(ExperimentReportError):
            load_experiment_report_json(duplicate, self.trials)
        nonfinite = self.report_text.replace('"numerator": 5', '"numerator": NaN', 1)
        with self.assertRaises(ExperimentReportError):
            load_experiment_report_json(nonfinite, self.trials)

    def test_exact_median_and_rational_rules_never_use_float_decisions(self) -> None:
        self.assertEqual(exact_median([3, 1, 2]), ExactRational(2, 1))
        self.assertEqual(exact_median([4, 1]), ExactRational(5, 2))
        with self.assertRaises(ExperimentReportError):
            exact_median([])
        with self.assertRaises(ExperimentReportError):
            exact_median([True])
        with self.assertRaises(ExperimentReportError):
            ExactRational(2, 4)
        with self.assertRaises(ExperimentReportError):
            ExactRational(1, 0)

    def test_cli_real_check_emits_exact_honest_outcome(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(CORPUS_ROOT),
                str(CONTEXT_ROOT),
                str(PROPOSAL_ROOT),
                str(TRIAL_PATH),
                str(REPORT_PATH),
                "--check",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(self.report.id, completed.stdout)
        self.assertIn("passed", completed.stdout)
        self.assertIn("improvement=5/7", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_cli_generate_check_mismatch_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "tools.report_experiment_e2.load_experiment_corpus",
            return_value=self.corpus,
        ), patch(
            "tools.report_experiment_e2.load_experiment_inputs",
            return_value=self.inputs,
        ), patch(
            "tools.report_experiment_e2.load_experiment_trials_json",
            return_value=self.trials,
        ), patch(
            "tools.report_experiment_e2.build_experiment_report",
            return_value=self.report,
        ):
            output = Path(directory) / "report.json"
            arguments = [
                "corpus", "contexts", "proposals", str(TRIAL_PATH), str(output)
            ]
            self.assertEqual(cli_main(arguments), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), self.report_text)
            self.assertEqual(cli_main(arguments + ["--check"]), 0)
            output.write_text("{}\n", encoding="utf-8")
            self.assertEqual(cli_main(arguments + ["--check"]), 1)
        with patch(
            "tools.report_experiment_e2.load_experiment_corpus",
            side_effect=ExperimentCorpusError("broken"),
        ):
            self.assertEqual(
                cli_main(["corpus", "contexts", "proposals", "trials", "output"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
