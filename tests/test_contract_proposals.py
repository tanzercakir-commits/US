from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from semantic_verifier.backend import CheckerBackend
from semantic_verifier.contract_proposals import (
    ACCEPTANCE_SCHEMA,
    PRE_SCREEN_SCHEMA,
    PROMPT_SCHEMA,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    REVIEW_SCHEMA,
    ProposalInputError,
    build_prompt_pack,
    build_review_bundle,
    candidate_overlay,
    load_request,
    load_response_json,
    pre_screen_response,
    read_request,
    render_prompt_pack,
    request_id,
    validate_accepted_source,
)
from semantic_verifier.model import VerificationResult, VerificationStatus


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "contract_proposals"
PACK = ROOT / "semantic_verifier" / "prompt_packs" / "contract_proposal" / "v1"


class ContractProposalPromptTests(unittest.TestCase):
    def request_payload(self) -> dict[str, object]:
        return json.loads((FIXTURES / "request.json").read_text(encoding="utf-8"))

    def test_request_and_response_schemas_are_versioned_and_strict(self):
        request_schema = json.loads(
            (PACK / "request.schema.json").read_text(encoding="utf-8")
        )
        response_schema = json.loads(
            (PACK / "response.schema.json").read_text(encoding="utf-8")
        )
        pre_screen_schema = json.loads(
            (PACK / "pre-screen.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(request_schema["$id"], REQUEST_SCHEMA)
        self.assertEqual(response_schema["$id"], RESPONSE_SCHEMA)
        self.assertEqual(pre_screen_schema["$id"], PRE_SCREEN_SCHEMA)
        self.assertFalse(pre_screen_schema["additionalProperties"])
        self.assertFalse(
            pre_screen_schema["properties"]["checks"]["items"]
            ["additionalProperties"]
        )
        self.assertFalse(request_schema["additionalProperties"])
        self.assertFalse(request_schema["properties"]["target"]["additionalProperties"])
        self.assertFalse(request_schema["properties"]["source"]["additionalProperties"])
        context = request_schema["properties"]["context"]
        self.assertFalse(context["additionalProperties"])
        self.assertFalse(context["properties"]["symbols"]["items"]["additionalProperties"])
        self.assertFalse(response_schema["additionalProperties"])
        proposal = response_schema["properties"]["proposals"]["items"]
        self.assertFalse(proposal["additionalProperties"])
        self.assertFalse(proposal["properties"]["anchor"]["additionalProperties"])

    def test_request_parser_normalizes_owned_context(self):
        payload = self.request_payload()
        payload["context"]["symbols"].reverse()  # type: ignore[index]
        request = load_request(payload)
        self.assertEqual([item.name for item in request.context.symbols], ["result", "value"])
        self.assertEqual(request.target.language, "c++17")

    def test_request_parser_rejects_unknown_or_ambiguous_input(self):
        unknown = self.request_payload()
        unknown["target"]["guessed_type"] = "int"  # type: ignore[index]
        with self.assertRaisesRegex(ProposalInputError, "unknown fields"):
            load_request(unknown)

        duplicate = self.request_payload()
        symbols = duplicate["context"]["symbols"]  # type: ignore[index]
        symbols.append(deepcopy(symbols[0]))  # type: ignore[union-attr,index]
        with self.assertRaisesRegex(ProposalInputError, "duplicate names"):
            load_request(duplicate)

        language = self.request_payload()
        language["target"]["language"] = "c++26"  # type: ignore[index]
        with self.assertRaisesRegex(ProposalInputError, "must be 'c\+\+17'"):
            load_request(language)

    def test_request_identity_ignores_location(self):
        original = self.request_payload()
        relocated = deepcopy(original)
        relocated["source"] = {"file": "D:/other/root/math.cpp", "line": 900}
        self.assertEqual(
            request_id(load_request(original)), request_id(load_request(relocated))
        )

    def test_request_identity_changes_with_owned_semantics(self):
        original = self.request_payload()
        baseline = request_id(load_request(original))
        variants = []
        signature = deepcopy(original)
        signature["target"][
            "signature"
        ] = "long clamp_nonnegative(long value)"  # type: ignore[index]
        variants.append(signature)
        body = deepcopy(original)
        body["target"]["body"] += "\n// changed"  # type: ignore[index,operator]
        variants.append(body)
        context = deepcopy(original)
        context["context"][
            "callee_contracts"
        ] = ["abs: ensures result >= 0"]  # type: ignore[index]
        variants.append(context)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(baseline, request_id(load_request(variant)))

    def test_frozen_prompt_is_deterministic_and_matches_golden(self):
        request = read_request(FIXTURES / "request.json")
        first = render_prompt_pack(request)
        second = render_prompt_pack(request)
        expected = (FIXTURES / "expected.prompt.json").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first, expected)
        self.assertEqual(json.loads(first)["schema"], PROMPT_SCHEMA)

    def test_prompt_and_response_preserve_untrusted_machine_provenance(self):
        prompt = build_prompt_pack(read_request(FIXTURES / "request.json"))
        boundary = prompt["trust_boundary"]
        self.assertEqual(
            boundary,
            {
                "accepted_intent": False,
                "generator": "untrusted",
                "machine_marker": "cs: ai",
                "referee_required": True,
            },
        )
        system = prompt["messages"][0]["content"]
        self.assertIn("never decide whether they are accepted or verified", system)
        self.assertIn("deterministic referee", system)
        response = prompt["response_schema"]
        self.assertEqual(response["properties"]["outcome"]["enum"], ["candidate", "declined"])
        comment = response["properties"]["proposals"]["items"]["properties"]["comment"]
        self.assertIn("// cs: ai", comment["pattern"])
        self.assertNotIn("accepted", response["properties"]["outcome"]["enum"])

    def test_cli_golden_check_is_offline_and_successful(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "contract_proposal.py"),
                "--request",
                str(FIXTURES / "request.json"),
                "--check",
                str(FIXTURES / "expected.prompt.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("prompt matches", completed.stdout)


class SolverErrorBackend(CheckerBackend):
    name = "proposal-test-solver-error"

    def check(self, obligation):
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=VerificationStatus.SOLVER_ERROR,
            location=obligation.location,
            message="solver error: injected proposal pre-screen failure",
        )


class ContractProposalPreScreenTests(unittest.TestCase):
    def request(self):
        return read_request(FIXTURES / "screen.request.json")

    def response_text(self, name: str) -> str:
        return (FIXTURES / f"{name}.response.json").read_text(encoding="utf-8")

    def candidate_response(self, request, comment, anchor=None):
        return json.dumps(
            {
                "notes": [],
                "outcome": "candidate",
                "proposals": [{
                    "anchor": anchor or {"kind": "function"},
                    "comment": comment,
                    "evidence": ["Owned source evidence."],
                    "machine_proposed": True,
                    "rationale": "Untrusted intent candidate.",
                }],
                "request_id": request_id(request),
                "schema": RESPONSE_SCHEMA,
            },
            sort_keys=True,
        )

    def test_fixture_matrix_preserves_every_rejection_status(self):
        request = self.request()
        expected = {
            "eligible": ("eligible", "eligible"),
            "contradictory": ("violated", "rejected"),
            "unsupported": ("unsupported", "rejected"),
            "unknown": ("unknown", "rejected"),
            "malformed": ("malformed", "rejected"),
            "declined": ("declined", "declined"),
        }
        for name, outcome in expected.items():
            with self.subTest(name=name):
                report = pre_screen_response(request, self.response_text(name))
                self.assertEqual((report.status, report.outcome), outcome)
                self.assertEqual(report.request_id, request_id(request))

    def test_candidate_overlay_is_separate_and_keeps_ai_marker(self):
        request = self.request()
        before = request.to_dict()
        response = load_response_json(self.response_text("eligible"), request_id(request))
        overlay = candidate_overlay(request, response)
        self.assertEqual(request.to_dict(), before)
        self.assertIn("// cs: ai ensures result >= 0", overlay)
        self.assertNotIn("// cs: ensures result >= 0", overlay)
        self.assertIn(request.target.signature, overlay)

    def test_body_violation_is_reviewable_intent_not_false_acceptance(self):
        request = self.request()
        report = pre_screen_response(
            request,
            self.candidate_response(request, "// cs: ai ensures result > 0"),
        )
        self.assertEqual(report.status, "eligible")
        self.assertGreater(report.verification_summary["violated"], 0)
        self.assertTrue(all("accepted" not in item for item in report.candidate_comments))

    def test_stale_identity_and_marker_free_contract_fail_as_malformed(self):
        request = self.request()
        stale = self.response_text("eligible").replace(
            request_id(request), "sha256:" + "0" * 64
        )
        stale_report = pre_screen_response(request, stale)
        marker_report = pre_screen_response(request, self.response_text("malformed"))
        self.assertEqual(stale_report.status, "malformed")
        self.assertIn("does not match", stale_report.reason)
        self.assertEqual(marker_report.status, "malformed")
        self.assertIn("retain", marker_report.reason)

    def test_solver_error_is_a_distinct_fail_closed_rejection(self):
        request = self.request()
        report = pre_screen_response(
            request,
            self.response_text("eligible"),
            checker=SolverErrorBackend(),
        )
        self.assertEqual(report.status, "solver_error")
        self.assertEqual(report.outcome, "rejected")
        self.assertIn("injected proposal pre-screen failure", report.reason)

    def test_invariant_requires_verified_entry_and_preservation(self):
        request = load_request({
            "schema": REQUEST_SCHEMA,
            "target": {
                "language": "c++17",
                "function": "countdown",
                "signature": "int countdown(int n)",
                "body": (
                    "{\n  int i = n;\n  while (i > 0) {\n"
                    "    i = i - 1;\n  }\n  return i;\n}"
                ),
            },
            "context": {
                "symbols": [
                    {"name": "n", "type": "i32", "role": "parameter"},
                    {"name": "i", "type": "i32", "role": "local"},
                    {"name": "result", "type": "i32", "role": "result"},
                ],
                "existing_contracts": ["// cs: requires n >= 0"],
                "callee_contracts": [],
            },
            "source": {"file": "loop.cpp", "line": 1},
        })
        useful = pre_screen_response(
            request,
            self.candidate_response(
                request,
                "// cs: ai invariant i >= 0",
                {"kind": "loop", "body_line": 3},
            ),
        )
        false_entry = pre_screen_response(
            request,
            self.candidate_response(
                request,
                "// cs: ai invariant i > 0",
                {"kind": "loop", "body_line": 3},
            ),
        )
        self.assertEqual(useful.status, "eligible")
        invariant_checks = [
            check for check in useful.checks
            if check.name.startswith("invariant_referee")
        ]
        self.assertEqual(
            [check.status for check in invariant_checks], ["verified", "verified"]
        )
        self.assertEqual(false_entry.status, "violated")
        self.assertEqual(false_entry.outcome, "rejected")

    def test_pre_screen_bytes_match_golden_and_repeat(self):
        request = self.request()
        response = self.response_text("eligible")
        first = pre_screen_response(request, response).to_json()
        second = pre_screen_response(request, response).to_json()
        expected = (FIXTURES / "expected.pre-screen.json").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first, expected)
        self.assertEqual(json.loads(first)["schema"], PRE_SCREEN_SCHEMA)

    def test_cli_pre_screen_golden_check(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "contract_proposal.py"),
                "--request", str(FIXTURES / "screen.request.json"),
                "--response", str(FIXTURES / "eligible.response.json"),
                "--check", str(FIXTURES / "expected.pre-screen.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("pre-screen matches", completed.stdout)

class ContractProposalApprovalTests(unittest.TestCase):
    def request(self):
        return read_request(FIXTURES / "screen.request.json")

    def response_text(self, name: str = "eligible") -> str:
        return (FIXTURES / f"{name}.response.json").read_text(encoding="utf-8")

    def accepted_source(self) -> str:
        return (FIXTURES / "accepted.cpp").read_text(encoding="utf-8")

    def test_review_and_acceptance_artifacts_have_exact_versioned_shapes(self):
        review = json.loads(
            (FIXTURES / "expected.review.json").read_text(encoding="utf-8")
        )
        acceptance = json.loads(
            (FIXTURES / "expected.acceptance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(review["schema"], REVIEW_SCHEMA)
        self.assertEqual(acceptance["schema"], ACCEPTANCE_SCHEMA)
        self.assertEqual(set(review), {
            "candidate_overlay", "instructions", "overlay_sha256",
            "pre_screen_status", "proposals", "reason", "request_id",
            "response_sha256", "review_id", "schema", "state", "transition",
        })
        self.assertEqual(set(acceptance), {
            "accepted_contracts", "accepted_source_sha256", "audit_id",
            "human_attestation_required", "reason", "referee_status",
            "request_id", "response_sha256", "review_id", "schema", "state",
            "transition", "verification_summary",
        })

    def test_state_machine_keeps_rejected_proposals_out_of_review(self):
        request = self.request()
        reviewable = build_review_bundle(request, self.response_text())
        rejected = build_review_bundle(request, self.response_text("contradictory"))
        declined = build_review_bundle(request, self.response_text("declined"))
        self.assertEqual(reviewable.state, "reviewable")
        self.assertEqual(reviewable.to_dict()["transition"], {
            "from": "proposed", "to": "reviewable"
        })
        self.assertIn("// cs: ai ensures", reviewable.candidate_overlay)
        self.assertEqual(rejected.state, "rejected")
        self.assertIsNone(rejected.candidate_overlay)
        self.assertEqual(rejected.proposals, ())
        self.assertEqual(declined.state, "declined")

    def test_marker_remains_reviewable_until_separate_source_removes_it(self):
        request = self.request()
        candidate = (FIXTURES / "candidate.overlay.cpp").read_text(encoding="utf-8")
        incomplete = validate_accepted_source(request, self.response_text(), candidate)
        accepted = validate_accepted_source(
            request, self.response_text(), self.accepted_source()
        )
        self.assertEqual(incomplete.state, "reviewable")
        self.assertIn("markers remain", incomplete.reason)
        self.assertEqual(accepted.state, "accepted")
        self.assertTrue(accepted.to_dict()["human_attestation_required"])
        self.assertNotIn("cs: ai", accepted.accepted_contracts[0].comment)
        self.assertTrue(accepted.matches_source(self.accepted_source()))

    def test_non_candidate_source_change_is_stale_and_fails_closed(self):
        request = self.request()
        changed = self.accepted_source().replace("return value;", "return value + 1;")
        audit = validate_accepted_source(request, self.response_text(), changed)
        self.assertEqual(audit.state, "stale")
        self.assertEqual(audit.referee_status, "not_run")
        self.assertIn("non-candidate source line", audit.reason)

    def test_human_contract_edit_is_re_screened_before_acceptance(self):
        request = self.request()
        unsupported = self.accepted_source().replace(
            "// cs: ensures result >= 0",
            "// cs: ensures result == value * value",
        )
        audit = validate_accepted_source(request, self.response_text(), unsupported)
        self.assertEqual(audit.state, "rejected")
        self.assertEqual(audit.referee_status, "unsupported")
        self.assertIn("failed referee pre-screen", audit.reason)

    def test_audit_identity_is_location_independent_and_detects_later_edits(self):
        request = self.request()
        payload = request.to_dict()
        payload["source"] = {"file": "D:/relocated/math.cpp", "line": 900}
        relocated = load_request(payload)
        first_review = build_review_bundle(request, self.response_text())
        second_review = build_review_bundle(relocated, self.response_text())
        first = validate_accepted_source(
            request, self.response_text(), self.accepted_source()
        )
        second = validate_accepted_source(
            relocated, self.response_text(), self.accepted_source()
        )
        self.assertEqual(first_review.review_id, second_review.review_id)
        self.assertEqual(first.audit_id, second.audit_id)
        changed = self.accepted_source().replace("result >= 0", "result > 0")
        self.assertFalse(first.matches_source(changed))

    def test_review_and_acceptance_bytes_match_goldens(self):
        request = self.request()
        response = self.response_text()
        review = build_review_bundle(request, response).to_json()
        acceptance = validate_accepted_source(
            request, response, self.accepted_source()
        ).to_json()
        self.assertEqual(
            review,
            (FIXTURES / "expected.review.json").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            acceptance,
            (FIXTURES / "expected.acceptance.json").read_text(encoding="utf-8"),
        )

    def test_cli_review_and_acceptance_golden_checks(self):
        common = [
            sys.executable,
            str(ROOT / "tools" / "contract_proposal.py"),
            "--request", str(FIXTURES / "screen.request.json"),
            "--response", str(FIXTURES / "eligible.response.json"),
        ]
        commands = [
            common + ["--review", "--check", str(FIXTURES / "expected.review.json")],
            common + [
                "--accepted-source", str(FIXTURES / "accepted.cpp"),
                "--check", str(FIXTURES / "expected.acceptance.json"),
            ],
        ]
        for command in commands:
            with self.subTest(command=command):
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("matches", completed.stdout)

if __name__ == "__main__":
    unittest.main()