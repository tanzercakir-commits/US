from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from semantic_verifier.invariant_research import (
    ARTIFACT_SCHEMA,
    CANDIDATE_MARKER,
    HornProblem,
    ResearchBudget,
    ResearchInputError,
    SExprParser,
    SpacerRunner,
    attach_candidate,
    emit_horn,
    extract_candidate,
    parse_problem,
    render_artifact,
    run_corpus,
)
from semantic_verifier.z3_backend import Z3DiscoveryError, discover_z3


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "invariant_inference" / "benchmarks.json"
EXPECTED = CORPUS.with_name("expected_candidates.json")


class InvariantResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.z3 = discover_z3()
        except Z3DiscoveryError:
            cls.z3 = None

    def test_strict_sexpr_parser_rejects_unbalanced_and_trailing_input(self):
        parser = SExprParser()
        with self.assertRaisesRegex(ResearchInputError, "unclosed"):
            parser.parse("(and true false")
        with self.assertRaisesRegex(ResearchInputError, "trailing"):
            parser.parse("true false")

    def test_problem_validation_is_sorted_and_fail_closed(self):
        raw = {
            "id": "case",
            "variables": ["n", "i"],
            "init": "true",
            "transition": "true",
            "bad": "false",
        }
        with self.assertRaisesRegex(ResearchInputError, "sorted"):
            parse_problem(raw)
        raw["variables"] = ["i", "n"]
        raw["bad"] = "(mystery i)"
        with self.assertRaisesRegex(ResearchInputError, "operator"):
            parse_problem(raw)

    def test_horn_emission_is_byte_identical_and_complete(self):
        problem = HornProblem(
            "count",
            ("i", "n"),
            SExprParser().parse("(and (= i 0) (>= n 0))"),
            SExprParser().parse("(and (= i_next (+ i 1)) (= n_next n))"),
            SExprParser().parse("(> i n)"),
        )
        first = emit_horn(problem)
        self.assertEqual(first, emit_horn(problem))
        self.assertIn("(declare-rel Inv_count (Int Int))", first)
        self.assertIn("(query fail_count :print-certificate true)", first)
        self.assertTrue(first.endswith("\n"))

    def test_certificate_let_is_normalized_to_contract_syntax(self):
        certificate = (
            "(forall ((A Int) (B Int)) "
            "(! (let ((bound (not (>= (+ A (* (- 1) B)) 1)))) "
            "(= (Inv_count A B) (and (not (<= A (- 1))) bound))) :weight 0))"
        )
        candidate = extract_candidate(certificate, "Inv_count", ("i", "n"))
        self.assertEqual(
            candidate,
            "(!((i <= -1)) && !(((i + (-1 * n)) >= 1)))",
        )

    def test_certificate_without_owned_relation_is_malformed(self):
        with self.assertRaisesRegex(ResearchInputError, "does not define"):
            extract_candidate("(= (Other A) true)", "Inv_count", ("i",))

    def test_candidate_attachment_is_explicit_and_unique(self):
        source = "int f() {\n  // cs: candidate\n  while (true) {}\n}\n"
        proposed = attach_candidate(source, "i >= 0")
        self.assertNotIn(CANDIDATE_MARKER, proposed)
        self.assertIn("// cs: ai invariant i >= 0", proposed)
        with self.assertRaisesRegex(ResearchInputError, "exactly one"):
            attach_candidate("int f() {}\n", "true")

    def test_subprocess_timeout_is_an_explicit_outcome(self):
        class TimeoutExecutor:
            def __call__(self, command, **kwargs):
                if "-version" in command:
                    return subprocess.CompletedProcess(
                        command, 0, "Z3 version 5.0.0 - 64 bit\n", ""
                    )
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        runner = SpacerRunner(
            z3=sys.executable,
            timeout_seconds=0.1,
            executor=TimeoutExecutor(),
        )
        problem = parse_problem(
            {
                "id": "timeout",
                "variables": ["i"],
                "init": "(= i 0)",
                "transition": "(= i_next (+ i 1))",
                "bad": "(< i 0)",
            }
        )
        proposal = runner.run(problem)
        self.assertEqual(proposal.status, "timeout")
        self.assertEqual(proposal.reason, "solver process timeout")

    def test_count_budget_prevents_every_solver_call(self):
        class NoRunRunner:
            executable = sys.executable

            def __init__(self):
                self.calls = 0

            def version(self):
                return "test solver"

            def run(self, problem):
                self.calls += 1
                raise AssertionError(problem.case_id)

        runner = NoRunRunner()
        artifact = run_corpus(
            CORPUS,
            runner=runner,
            budget=ResearchBudget(max_solver_cases=0),
        )
        self.assertEqual(runner.calls, 0)
        statuses = {case["id"]: case["status"] for case in artifact["cases"]}
        self.assertEqual(statuses["count_exact"], "no_candidate")
        self.assertEqual(statuses["unsupported"], "unsupported")
        self.assertEqual(statuses["malformed"], "malformed")

    @unittest.skipUnless(discover_z3 if True else False, "unreachable")
    def test_fixed_corpus_matches_committed_sorted_artifact(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        first = render_artifact(run_corpus(CORPUS))
        second = render_artifact(run_corpus(CORPUS))
        self.assertEqual(first, second)
        self.assertEqual(first, EXPECTED.read_text(encoding="utf-8"))
        parsed = json.loads(first)
        self.assertEqual(parsed["schema"], ARTIFACT_SCHEMA)
        ids = [case["id"] for case in parsed["cases"]]
        self.assertEqual(ids, sorted(ids))

    def test_fixed_corpus_records_every_required_outcome(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        artifact = run_corpus(CORPUS)
        cases = {case["id"]: case for case in artifact["cases"]}
        self.assertEqual(cases["count_exact"]["status"], "useful")
        self.assertEqual(cases["count_insufficient"]["status"], "insufficient")
        self.assertEqual(cases["timeout"]["status"], "timeout")
        self.assertEqual(cases["unsafe"]["status"], "no_candidate")
        self.assertEqual(cases["unsupported"]["status"], "unsupported")
        self.assertEqual(cases["malformed"]["status"], "malformed")

    def test_useful_candidate_is_reproved_as_machine_proposed(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        artifact = run_corpus(CORPUS)
        exact = next(case for case in artifact["cases"] if case["id"] == "count_exact")
        validation = exact["validation"]
        self.assertTrue(validation["machine_proposed"])
        self.assertTrue(validation["inductive"])
        self.assertTrue(validation["accepted"])
        kinds = {item["kind"]: item["status"] for item in validation["results"]}
        self.assertEqual(kinds["loop_invariant_entry"], "verified")
        self.assertEqual(kinds["loop_invariant_preservation"], "verified")

    def test_insufficient_candidate_never_promotes_to_accepted(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        artifact = run_corpus(CORPUS)
        case = next(item for item in artifact["cases"] if item["id"] == "count_insufficient")
        self.assertEqual(case["status"], "insufficient")
        self.assertTrue(case["validation"]["inductive"])
        self.assertFalse(case["validation"]["accepted"])
        self.assertIn(
            {"kind": "postcondition", "status": "violated"},
            case["validation"]["results"],
        )

    def test_cli_check_mode_accepts_the_committed_artifact(self):
        if self.z3 is None:
            self.skipTest("Z3 is not installed")
        completed = subprocess.run(
            [sys.executable, "tools/invariant_research.py", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("artifact matches", completed.stdout)


if __name__ == "__main__":
    unittest.main()