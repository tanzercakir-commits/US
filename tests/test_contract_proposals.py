from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from semantic_verifier.contract_proposals import (
    PROMPT_SCHEMA,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    ProposalInputError,
    build_prompt_pack,
    load_request,
    read_request,
    render_prompt_pack,
    request_id,
)


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
        self.assertEqual(request_schema["$id"], REQUEST_SCHEMA)
        self.assertEqual(response_schema["$id"], RESPONSE_SCHEMA)
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
        signature["target"]["signature"] = "long clamp_nonnegative(long value)"  # type: ignore[index]
        variants.append(signature)
        body = deepcopy(original)
        body["target"]["body"] += "\n// changed"  # type: ignore[index,operator]
        variants.append(body)
        context = deepcopy(original)
        context["context"]["callee_contracts"] = ["abs: ensures result >= 0"]  # type: ignore[index]
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


if __name__ == "__main__":
    unittest.main()