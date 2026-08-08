from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from semantic_verifier.experiment_corpus import load_experiment_corpus
from semantic_verifier.referee_search import (
    CANDIDATES_PER_CASE,
    CANDIDATE_SET_SCHEMA,
    LIMITATIONS,
    PROVENANCE,
    SEARCH_REPORT_SCHEMA,
    TOTAL_EVALUATIONS,
    CandidateEvaluation,
    CandidateSet,
    EvaluationResult,
    RefereeSearchError,
    SearchCase,
    SearchCaseResult,
    _canonical_json,
    _content_id,
    build_frozen_candidate_set,
    evaluate_candidate_set,
    load_candidate_set_json,
    load_search_report_json,
)
from semantic_verifier.repair_loop import LineEdit, PatchProposal, apply_line_edit
from tools.run_referee_search import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "experiment_e2" / "corpus"
SEARCH_ROOT = ROOT / "benchmarks" / "referee_search"
CANDIDATES_PATH = SEARCH_ROOT / "candidates.json"
REPORT_PATH = SEARCH_ROOT / "report.json"
SCHEMA_ROOT = ROOT / "semantic_verifier" / "referee_search_schema" / "v1"
DOC_PATH = ROOT / "docs" / "referee_guided_search.md"


class RefereeSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_experiment_corpus(CORPUS_ROOT)
        cls.candidate_text = CANDIDATES_PATH.read_text(encoding="utf-8")
        cls.candidates = load_candidate_set_json(cls.candidate_text, cls.corpus)
        cls.report_text = REPORT_PATH.read_text(encoding="utf-8")
        cls.report = load_search_report_json(cls.report_text, cls.candidates)
        cls.recomputed = evaluate_candidate_set(cls.corpus, cls.candidates)

    @staticmethod
    def reidentify_candidates(payload: dict[str, object]) -> str:
        content = {
            "cases": payload["cases"],
            "corpus": payload["corpus"],
            "n": payload["n"],
            "provenance": payload["provenance"],
            "schema": payload["schema"],
        }
        payload["id"] = _content_id("referee-search-candidates", content)
        return _canonical_json(payload)

    @staticmethod
    def set_proposal(
        payload: dict[str, object],
        case_index: int,
        rank_index: int,
        proposal: PatchProposal,
    ) -> None:
        payload["cases"][case_index]["candidates"][rank_index]["proposal"] = (
            proposal.to_dict()
        )

    def test_frozen_candidate_set_is_exact_complete_and_original_based(self) -> None:
        self.assertEqual(json.loads(self.candidate_text)["schema"], CANDIDATE_SET_SCHEMA)
        self.assertEqual(self.candidates.provenance, PROVENANCE)
        self.assertEqual(self.candidates.n, CANDIDATES_PER_CASE)
        self.assertEqual(len(self.candidates.cases), 20)
        identities = []
        correct_ranks = []
        for case, row in zip(self.corpus.cases, self.candidates.cases):
            self.assertEqual(row.case, case.id)
            self.assertEqual([item.rank for item in row.candidates], [1, 2, 3, 4])
            case_correct = []
            for ranked in row.candidates:
                identities.append(ranked.proposal.id)
                self.assertEqual(ranked.proposal.base_source_sha256, case.source_sha256)
                candidate = apply_line_edit(case.source_text, ranked.proposal.edit)
                self.assertNotEqual(candidate, case.source_text)
                if candidate == case.repaired_source():
                    case_correct.append(ranked.rank)
            correct_ranks.append(case_correct)
        self.assertEqual(len(identities), TOTAL_EVALUATIONS)
        self.assertEqual(len(set(identities)), TOTAL_EVALUATIONS)
        self.assertEqual(correct_ranks[:4], [[1]] * 4)
        self.assertEqual(correct_ranks[4:9], [[2]] * 5)
        self.assertEqual(correct_ranks[9:14], [[3]] * 5)
        self.assertEqual(correct_ranks[14:18], [[4]] * 4)
        self.assertEqual(correct_ranks[18:], [[], []])
        self.assertEqual(self.candidate_text, build_frozen_candidate_set(self.corpus).to_json())

    def test_report_recomputes_all_eighty_without_early_stop(self) -> None:
        self.assertEqual(self.report_text, self.recomputed.to_json())
        self.assertEqual(self.report.content_dict()["evaluated"], 80)
        self.assertEqual(len(self.report.cases), 20)
        for row in self.report.cases:
            self.assertEqual([item.rank for item in row.evaluations], [1, 2, 3, 4])
            if row.selected_rank is not None:
                self.assertEqual(len(row.evaluations[row.selected_rank :]), 4 - row.selected_rank)
        metrics = self.report._metrics()
        self.assertEqual(
            metrics,
            {
                "arms": {
                    "best_of_n": {
                        "rate": {"denominator": 10, "numerator": 9},
                        "successes": 18,
                        "total": 20,
                    },
                    "single_shot": {
                        "rate": {"denominator": 5, "numerator": 1},
                        "successes": 4,
                        "total": 20,
                    },
                },
                "outcome": "passed",
                "threshold": {"denominator": 5, "numerator": 2},
                "uplift": {"denominator": 10, "numerator": 7},
            },
        )

    def test_selection_is_referee_only_lowest_rank_and_rank_one_is_single_shot(self) -> None:
        selected = 0
        single = 0
        for candidate_row, result_row in zip(self.candidates.cases, self.report.cases):
            by_rank = {item.rank: item for item in result_row.evaluations}
            passing = [rank for rank in range(1, 5) if by_rank[rank].status == "verified"]
            expected_rank = passing[0] if passing else None
            self.assertEqual(result_row.selected_rank, expected_rank)
            self.assertEqual(
                result_row.single_shot_verified,
                by_rank[1].status == "verified",
            )
            self.assertEqual(
                by_rank[1].proposal,
                candidate_row.candidates[0].proposal.id,
            )
            if expected_rank is None:
                self.assertIsNone(result_row.selected_proposal)
            else:
                selected += 1
                self.assertEqual(result_row.selected_proposal, by_rank[expected_rank].proposal)
            single += result_row.single_shot_verified
        self.assertEqual((single, selected), (4, 18))

    def test_unknown_unsupported_and_solver_error_cannot_be_selected(self) -> None:
        for status in ("unknown", "unsupported", "solver_error"):
            result = EvaluationResult("ob-test", "postcondition", status)
            evaluation = CandidateEvaluation(
                1,
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "sha256:" + "3" * 64,
                (result,),
                "blocked",
            )
            self.assertEqual(evaluation.status, "blocked")
            with self.assertRaises(RefereeSearchError):
                replace(evaluation, status="verified")

    def test_candidate_loader_rejects_incomplete_reordered_and_stale_links(self) -> None:
        mutations = []
        missing = json.loads(self.candidate_text)
        missing["cases"].pop()
        mutations.append(missing)
        reordered = json.loads(self.candidate_text)
        reordered["cases"][0], reordered["cases"][1] = (
            reordered["cases"][1],
            reordered["cases"][0],
        )
        mutations.append(reordered)
        duplicate_rank = json.loads(self.candidate_text)
        duplicate_rank["cases"][0]["candidates"][1]["rank"] = 1
        mutations.append(duplicate_rank)
        stale_corpus = json.loads(self.candidate_text)
        stale_corpus["corpus"] = "sha256:" + "0" * 64
        mutations.append(stale_corpus)
        for payload in mutations:
            with self.subTest(kind=len(payload["cases"])), self.assertRaises(RefereeSearchError):
                load_candidate_set_json(self.reidentify_candidates(payload), self.corpus)

    def test_candidate_loader_rejects_noop_contract_and_cross_case_edits(self) -> None:
        first = self.corpus.cases[0]
        second = self.corpus.cases[1]
        payloads = []

        noop = json.loads(self.candidate_text)
        noop_proposal = PatchProposal.create(
            base_source_sha256=first.source_sha256,
            edit=LineEdit(4, 4, (first.source_text.splitlines()[3],)),
        )
        self.set_proposal(noop, 0, 0, noop_proposal)
        payloads.append(noop)

        contract = json.loads(self.candidate_text)
        contract_proposal = PatchProposal.create(
            base_source_sha256=first.source_sha256,
            edit=LineEdit(1, 1, ("// cs: requires value >= 0",)),
        )
        self.set_proposal(contract, 0, 0, contract_proposal)
        payloads.append(contract)

        cross_case = json.loads(self.candidate_text)
        cross_proposal = PatchProposal.create(
            base_source_sha256=first.source_sha256,
            edit=LineEdit(4, 4, ("  return value * 999;",)),
        )
        self.set_proposal(cross_case, 1, 0, cross_proposal)
        self.assertNotEqual(first.source_sha256, second.source_sha256)
        payloads.append(cross_case)

        for payload in payloads:
            with self.assertRaises(RefereeSearchError):
                load_candidate_set_json(self.reidentify_candidates(payload), self.corpus)

    def test_strict_json_and_report_tamper_fail_closed(self) -> None:
        with self.assertRaises(RefereeSearchError):
            load_candidate_set_json("\ufeff" + self.candidate_text, self.corpus)
        with self.assertRaises(RefereeSearchError):
            load_candidate_set_json(json.dumps(json.loads(self.candidate_text)), self.corpus)
        duplicate = self.candidate_text.replace(
            '  "id":', '  "schema": "duplicate",\n  "id":', 1
        )
        with self.assertRaises(RefereeSearchError):
            load_candidate_set_json(duplicate, self.corpus)

        missing_evaluation = json.loads(self.report_text)
        missing_evaluation["cases"][0]["evaluations"].pop()
        false_selection = json.loads(self.report_text)
        false_selection["cases"][0]["selected"]["rank"] = 4
        false_uplift = json.loads(self.report_text)
        false_uplift["uplift"] = {"denominator": 1, "numerator": 1}
        incomplete = json.loads(self.report_text)
        incomplete["evaluated"] = 79
        for payload in (
            missing_evaluation,
            false_selection,
            false_uplift,
            incomplete,
        ):
            content = {key: value for key, value in payload.items() if key != "id"}
            payload["id"] = _content_id("referee-search-report", content)
            with self.assertRaises(RefereeSearchError):
                load_search_report_json(_canonical_json(payload), self.candidates)

    def test_relocation_and_repeated_generation_are_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "relocated"
            corpus_root = target / "corpus"
            shutil.copytree(CORPUS_ROOT, corpus_root)
            corpus = load_experiment_corpus(corpus_root)
            candidates = build_frozen_candidate_set(corpus)
            report = evaluate_candidate_set(corpus, candidates)
            self.assertEqual(candidates.to_json(), self.candidate_text)
            self.assertEqual(report.to_json(), self.report_text)

    def test_structural_schemas_are_strict_and_match_artifacts(self) -> None:
        candidate_schema = json.loads(
            (SCHEMA_ROOT / "candidates.schema.json").read_text(encoding="utf-8")
        )
        report_schema = json.loads(
            (SCHEMA_ROOT / "report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(candidate_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(report_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(candidate_schema["additionalProperties"])
        self.assertFalse(report_schema["additionalProperties"])
        self.assertEqual(candidate_schema["properties"]["schema"]["const"], CANDIDATE_SET_SCHEMA)
        self.assertEqual(report_schema["properties"]["schema"]["const"], SEARCH_REPORT_SCHEMA)
        self.assertEqual(report_schema["properties"]["evaluated"]["const"], 80)
        self.assertEqual(json.loads(self.candidate_text)["schema"], CANDIDATE_SET_SCHEMA)
        self.assertEqual(json.loads(self.report_text)["schema"], SEARCH_REPORT_SCHEMA)

    def test_cli_generate_check_mismatch_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            candidates_path = target / "candidates.json"
            report_path = target / "report.json"
            arguments = [str(CORPUS_ROOT), str(candidates_path), str(report_path)]
            self.assertEqual(cli_main(arguments), 0)
            self.assertEqual(candidates_path.read_text(encoding="utf-8"), self.candidate_text)
            self.assertEqual(report_path.read_text(encoding="utf-8"), self.report_text)
            self.assertEqual(cli_main(arguments + ["--check"]), 0)

            alternative_rows = list(self.candidates.cases)
            first = alternative_rows[0]
            ranked = list(first.candidates)
            ranked[1] = replace(
                ranked[1],
                proposal=PatchProposal.create(
                    base_source_sha256=self.corpus.cases[0].source_sha256,
                    edit=LineEdit(4, 4, ("  return value * 998;",)),
                ),
            )
            alternative_rows[0] = SearchCase(first.case, tuple(ranked))
            alternative = CandidateSet.create(
                corpus=self.corpus.id,
                cases=alternative_rows,
            )
            candidates_path.write_text(alternative.to_json(), encoding="utf-8", newline="\n")
            self.assertEqual(cli_main(arguments + ["--check"]), 1)
            self.assertEqual(
                cli_main([str(target / "missing"), str(candidates_path), str(report_path)]),
                2,
            )

    def test_report_and_documentation_preserve_proxy_limitations(self) -> None:
        self.assertEqual(self.report.content_dict()["limitations"], list(LIMITATIONS))
        document = " ".join(DOC_PATH.read_text(encoding="utf-8").lower().split())
        for phrase in (
            "oracle-seeded",
            "not model output",
            "does not establish consciousness",
            "causality",
            "model search uplift",
        ):
            self.assertIn(phrase, document)


if __name__ == "__main__":
    unittest.main()
