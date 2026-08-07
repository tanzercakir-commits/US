from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
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
    ARMS,
    EVIDENCE_SCOPE,
    MAX_PROPOSALS,
    PROPOSER,
    REFEREE,
    ExperimentContext,
    ExperimentE2Error,
    ExperimentProposalScript,
    _validate_script_chain,
    load_experiment_context_json,
    load_experiment_inputs,
    load_experiment_script_json,
    load_experiment_trials_json,
    run_experiment,
)
from semantic_verifier.repair_loop import LineEdit, PatchProposal
from tools.run_experiment_e2 import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "benchmarks" / "experiment_e2"
CORPUS_ROOT = EXPERIMENT_ROOT / "corpus"
CONTEXT_ROOT = EXPERIMENT_ROOT / "contexts"
PROPOSAL_ROOT = EXPERIMENT_ROOT / "proposals"
RESULT_PATH = EXPERIMENT_ROOT / "results" / "trials.json"


class ExperimentE2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_experiment_corpus(CORPUS_ROOT)
        cls.inputs = load_experiment_inputs(
            cls.corpus,
            CONTEXT_ROOT,
            PROPOSAL_ROOT,
        )
        cls.frozen_text = RESULT_PATH.read_text(encoding="utf-8")
        cls.frozen = load_experiment_trials_json(
            cls.frozen_text,
            cls.inputs,
        )

    def test_contexts_are_twenty_exact_isolated_pairs(self) -> None:
        self.assertEqual(len(self.inputs.contexts), 40)
        for case in self.corpus.cases:
            compiler = self.inputs.context_for(case.id, ARM_COMPILER)
            semantic = self.inputs.context_for(case.id, ARM_SEMANTIC)
            self.assertEqual(compiler.target_source, case.source_sha256)
            self.assertEqual(semantic.target_source, case.source_sha256)
            self.assertEqual(compiler.corpus, self.corpus.id)
            self.assertEqual(semantic.corpus, self.corpus.id)
            self.assertIsNone(compiler.bundle)
            self.assertNotIn("// cs:", compiler.redacted_source)
            self.assertNotIn("requires", compiler.to_json())
            self.assertNotIn("ensures", compiler.to_json())
            self.assertIsNotNone(semantic.bundle)
            self.assertEqual(
                semantic.bundle.id,
                self.inputs.bundle_for(case.id).id,
            )
            self.assertNotIn("oracle", semantic.to_json().lower())

    def test_proposal_scripts_have_fixed_provenance_and_links(self) -> None:
        self.assertEqual(len(self.inputs.scripts), 40)
        self.assertEqual(
            {script.proposer for script in self.inputs.scripts},
            {PROPOSER},
        )
        self.assertEqual(
            {script.evidence_scope for script in self.inputs.scripts},
            {EVIDENCE_SCOPE},
        )
        for script in self.inputs.scripts:
            context = self.inputs.context_for(script.case, script.arm)
            self.assertEqual(script.context, context.id)
            self.assertLessEqual(len(script.proposals), MAX_PROPOSALS)
            self.assertGreaterEqual(len(script.proposals), 1)

    def test_frozen_results_are_twenty_complete_pairs(self) -> None:
        self.assertEqual(len(self.frozen.trials), 40)
        self.assertEqual(self.frozen.corpus, self.corpus.id)
        self.assertEqual(self.frozen.max_proposals, 4)
        self.assertEqual(self.frozen.referee, REFEREE)
        self.assertEqual(self.frozen.proposer, PROPOSER)
        self.assertEqual(self.frozen.evidence_scope, EVIDENCE_SCOPE)
        self.assertEqual(
            {(row.case, row.arm) for row in self.frozen.trials},
            {(case.id, arm) for case in self.corpus.cases for arm in ARMS},
        )
        self.assertEqual(self.frozen.to_json(), self.frozen_text)

    def test_outcomes_include_success_exhaustion_and_censored_scores(self) -> None:
        compiler = [
            row for row in self.frozen.trials
            if row.arm == ARM_COMPILER
        ]
        semantic = [
            row for row in self.frozen.trials
            if row.arm == ARM_SEMANTIC
        ]
        self.assertEqual(sum(row.status == "verified" for row in compiler), 16)
        self.assertEqual(sum(row.status == "exhausted" for row in compiler), 4)
        self.assertEqual([row.score for row in compiler], [5] * 4 + [4] * 6 + [3] * 5 + [2] * 3 + [1] * 2)
        self.assertEqual(sum(row.status == "verified" for row in semantic), 20)
        self.assertEqual([row.score for row in semantic], [1] * 20)
        for row in self.frozen.trials:
            expected = row.attempts if row.status == "verified" else 5
            self.assertEqual(row.score, expected)
            self.assertEqual(row.loop.max_iterations, 4)
            self.assertEqual(row.loop.initial_bundle, row.bundle)
            if row.status == "verified":
                self.assertEqual(row.loop.attempts[-1].status, "verified")
                self.assertIsNotNone(row.loop.accepted_source)

    def test_runner_reproduces_frozen_bytes_without_source_mutation(self) -> None:
        before = {
            path: path.read_bytes()
            for path in (CORPUS_ROOT / "cases").glob("*.cpp")
        }
        reproduced = run_experiment(self.inputs)
        after = {path: path.read_bytes() for path in before}
        self.assertEqual(reproduced.to_json(), self.frozen_text)
        self.assertEqual(after, before)

    def test_shuffled_rows_load_to_identical_canonical_artifact(self) -> None:
        payload = json.loads(self.frozen_text)
        payload["trials"] = list(reversed(payload["trials"]))
        shuffled = json.dumps(payload, separators=(",", ":"))
        loaded = load_experiment_trials_json(shuffled, self.inputs)
        self.assertEqual(loaded, self.frozen)
        self.assertEqual(loaded.to_json(), self.frozen_text)

    def test_missing_duplicate_and_unpaired_trials_fail_closed(self) -> None:
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode):
                payload = json.loads(self.frozen_text)
                if mode == "missing":
                    payload["trials"].pop()
                else:
                    payload["trials"][-1] = deepcopy(payload["trials"][0])
                with self.assertRaises(ExperimentE2Error):
                    load_experiment_trials_json(json.dumps(payload), self.inputs)

    def test_result_scores_loops_links_and_fields_are_tamper_evident(self) -> None:
        mutations = (
            lambda value: value["trials"][0].update({"score": True}),
            lambda value: value["trials"][0].update({"score": 4}),
            lambda value: value["trials"][0].update({"context": "sha256:" + "0" * 64}),
            lambda value: value["trials"][0]["loop"]["attempts"][0].update({"proposal": "sha256:" + "0" * 64}),
            lambda value: value["trials"][0].update({"unknown": 1}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = json.loads(self.frozen_text)
                mutate(payload)
                with self.assertRaises(ExperimentE2Error):
                    load_experiment_trials_json(json.dumps(payload), self.inputs)

    def test_result_envelope_and_json_are_strict(self) -> None:
        mutations = (
            lambda value: value.update({"corpus": "sha256:" + "0" * 64}),
            lambda value: value.update({"max_proposals": 5}),
            lambda value: value.update({"referee": "other"}),
            lambda value: value.update({"proposer": "other"}),
            lambda value: value.update({"evidence_scope": "other"}),
            lambda value: value.update({"schema": "future"}),
            lambda value: value.update({"unknown": 1}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = json.loads(self.frozen_text)
                mutate(payload)
                with self.assertRaises(ExperimentE2Error):
                    load_experiment_trials_json(json.dumps(payload), self.inputs)
        duplicate = self.frozen_text.replace(
            '  "corpus":',
            '  "corpus": "sha256:' + "0" * 64 + '",\n  "corpus":',
            1,
        )
        with self.assertRaises(ExperimentE2Error):
            load_experiment_trials_json(duplicate, self.inputs)

    def test_context_and_script_contamination_fail_closed(self) -> None:
        compiler = self.inputs.context_for("e2-case-01", ARM_COMPILER)
        bundle = self.inputs.bundle_for("e2-case-01")
        with self.assertRaises(ExperimentE2Error):
            replace(compiler, bundle=bundle)
        semantic = self.inputs.context_for("e2-case-01", ARM_SEMANTIC)
        with self.assertRaises(ExperimentE2Error):
            replace(semantic, diagnostic="TEST FAILURE")

        script = self.inputs.script_for("e2-case-01", ARM_COMPILER)
        with self.assertRaises(ExperimentE2Error):
            replace(script, proposer="other")
        with self.assertRaises(ExperimentE2Error):
            ExperimentProposalScript.create(
                arm=script.arm,
                case=script.case,
                context=script.context,
                proposals=(script.proposals[0], script.proposals[0]),
            )
        stale = PatchProposal.create(
            base_source_sha256="sha256:" + "0" * 64,
            edit=LineEdit(4, 4, ("  return value;",)),
        )
        stale_script = ExperimentProposalScript.create(
            arm=script.arm,
            case=script.case,
            context=script.context,
            proposals=(stale,),
        )
        with self.assertRaises(ExperimentE2Error):
            _validate_script_chain(self.corpus.cases[0], stale_script)

    def test_context_and_script_loaders_require_exact_canonical_data(self) -> None:
        context = self.inputs.context_for("e2-case-01", ARM_COMPILER)
        payload = context.to_dict()
        payload["unknown"] = 1
        with self.assertRaises(ExperimentE2Error):
            load_experiment_context_json(json.dumps(payload), context)
        with self.assertRaises(ExperimentE2Error):
            load_experiment_context_json(
                json.dumps(context.to_dict(), separators=(",", ":")),
                context,
            )

        script = self.inputs.script_for("e2-case-01", ARM_COMPILER)
        script_payload = script.to_dict()
        script_payload["context"] = "sha256:" + "0" * 64
        with self.assertRaises(ExperimentE2Error):
            load_experiment_script_json(json.dumps(script_payload))
        with self.assertRaises(ExperimentE2Error):
            load_experiment_script_json(
                json.dumps(script.to_dict(), separators=(",", ":"))
            )

    def test_missing_and_extra_input_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            contexts = target / "contexts"
            proposals = target / "proposals"
            shutil.copytree(CONTEXT_ROOT, contexts)
            shutil.copytree(PROPOSAL_ROOT, proposals)
            (contexts / "extra.json").write_text("{}\n", encoding="utf-8")
            with patch(
                "semantic_verifier.experiment_e2.expected_contexts",
                return_value=(self.inputs.contexts, self.inputs.bundles),
            ), self.assertRaises(ExperimentE2Error):
                load_experiment_inputs(self.corpus, contexts, proposals)

    def test_relocated_inputs_and_results_preserve_exact_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "experiment_e2"
            shutil.copytree(EXPERIMENT_ROOT, target)
            corpus = load_experiment_corpus(target / "corpus")
            with patch(
                "semantic_verifier.experiment_e2.expected_contexts",
                return_value=(self.inputs.contexts, self.inputs.bundles),
            ):
                inputs = load_experiment_inputs(
                    corpus,
                    target / "contexts",
                    target / "proposals",
                )
            loaded = load_experiment_trials_json(
                (target / "results" / "trials.json").read_text(encoding="utf-8"),
                inputs,
            )
            self.assertEqual(loaded.to_json(), self.frozen_text)
            self.assertEqual(
                (target / "results" / "trials.json").read_bytes(),
                RESULT_PATH.read_bytes(),
            )

    def test_cli_generate_check_mismatch_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "tools.run_experiment_e2.load_experiment_corpus",
            return_value=self.corpus,
        ), patch(
            "tools.run_experiment_e2.load_experiment_inputs",
            return_value=self.inputs,
        ), patch(
            "tools.run_experiment_e2.run_experiment",
            return_value=self.frozen,
        ):
            output = Path(directory) / "trials.json"
            arguments = [
                "corpus", "contexts", "proposals", str(output)
            ]
            self.assertEqual(cli_main(arguments), 0)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                self.frozen_text,
            )
            self.assertEqual(cli_main(arguments + ["--check"]), 0)
            output.write_text("{}\n", encoding="utf-8")
            self.assertEqual(cli_main(arguments + ["--check"]), 1)
        with patch(
            "tools.run_experiment_e2.load_experiment_corpus",
            side_effect=ExperimentCorpusError("broken"),
        ):
            self.assertEqual(
                cli_main([
                    "corpus", "contexts", "proposals", "output"
                ]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
