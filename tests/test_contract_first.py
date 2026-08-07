from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.backend import CheckerBackend
from semantic_verifier.contract_first import (
    RUN_SCHEMA,
    ContractFirstInputError,
    run_contract_first,
)
from semantic_verifier.model import VerificationResult, VerificationStatus


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "contract_first"
MANIFEST = FIXTURE / "task.json"
PILOT = ROOT / "pilots" / "contract_first" / "guarded_absolute"
PILOT_MANIFEST = PILOT / "task.json"


class StatusBackend(CheckerBackend):
    def __init__(self, status: VerificationStatus):
        self.status = status
        self.name = f"contract-first-{status.value}"

    def check(self, obligation):
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=self.status,
            location=obligation.location,
            message=f"injected {self.status.value}",
        )


class ContractFirstWorkflowTests(unittest.TestCase):
    def copied_task(self, parent: Path) -> Path:
        target = parent / "task"
        shutil.copytree(FIXTURE, target)
        return target / "task.json"

    def rewrite_artifact(self, manifest: Path, key: str, content: str) -> None:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        artifact = payload["artifacts"][key]
        path = manifest.parent / artifact["path"]
        path.write_text(content, encoding="utf-8", newline="\n")
        artifact["sha256"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_frozen_run_is_complete_deterministic_and_matches_golden(self):
        first = run_contract_first(MANIFEST)
        second = run_contract_first(MANIFEST)
        expected = (FIXTURE / "expected.run.json").read_text(encoding="utf-8")
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.to_json(), expected)
        self.assertEqual(first.to_dict()["schema"], RUN_SCHEMA)
        self.assertEqual(first.verification_summary, {
            "solver_error": 0,
            "unknown": 0,
            "unsupported": 0,
            "verified": 3,
            "violated": 0,
        })
        self.assertEqual(
            [step.name for step in first.transitions],
            [
                "request_to_proposed",
                "proposed_to_accepted",
                "accepted_to_implementation",
                "implementation_to_verification",
            ],
        )

    def test_relocation_does_not_change_the_run_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            relocated = self.copied_task(Path(temporary))
            self.assertEqual(
                run_contract_first(MANIFEST).to_json(),
                run_contract_first(relocated).to_json(),
            )

    def test_unsafe_path_and_hash_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["artifacts"]["proposed"]["path"] = "../proposed.cpp"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ContractFirstInputError, "unsafe"):
                run_contract_first(manifest)

        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            (manifest.parent / "implemented.cpp").write_text(
                "// drift\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ContractFirstInputError, "hash drift"):
                run_contract_first(manifest)

    def test_proposal_and_approval_markers_are_not_interchangeable(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            proposed = (manifest.parent / "proposed.cpp").read_text(encoding="utf-8")
            self.rewrite_artifact(manifest, "proposed", proposed.replace("cs: ai", "cs:"))
            with self.assertRaisesRegex(ContractFirstInputError, "retain cs: ai"):
                run_contract_first(manifest)

        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            accepted = (manifest.parent / "accepted.cpp").read_text(encoding="utf-8")
            self.rewrite_artifact(manifest, "accepted", accepted.replace("cs:", "cs: ai"))
            with self.assertRaisesRegex(ContractFirstInputError, "marker-free"):
                run_contract_first(manifest)

    def test_implementation_cannot_change_accepted_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            source = (manifest.parent / "implemented.cpp").read_text(encoding="utf-8")
            changed = source.replace("result == value + 1", "result >= value")
            self.rewrite_artifact(manifest, "implemented", changed)
            with self.assertRaisesRegex(ContractFirstInputError, "differ from the accepted"):
                run_contract_first(manifest)

    def test_violation_and_unsupported_implementation_never_complete(self):
        variants = {
            "violated": "return value;",
            "unsupported": "return value * value;",
        }
        for expected, replacement in variants.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                manifest = self.copied_task(Path(temporary))
                source = (manifest.parent / "implemented.cpp").read_text(encoding="utf-8")
                changed = source.replace("return value + 1;", replacement)
                self.rewrite_artifact(manifest, "implemented", changed)
                with self.assertRaisesRegex(ContractFirstInputError, expected):
                    run_contract_first(manifest)

    def test_unknown_and_solver_error_backends_never_complete(self):
        for status in (VerificationStatus.UNKNOWN, VerificationStatus.SOLVER_ERROR):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ContractFirstInputError, status.value):
                    run_contract_first(MANIFEST, checker=StatusBackend(status))

    def test_expected_summary_is_an_exact_ratchet(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.copied_task(Path(temporary))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["verification"]["expected_summary"]["verified"] = 2
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ContractFirstInputError, "summary differs"):
                run_contract_first(manifest)

    def test_cli_golden_check(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "contract_first_workflow.py"),
                "--manifest",
                str(MANIFEST),
                "--check",
                str(FIXTURE / "expected.run.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("run matches", completed.stdout)

    def test_guarded_absolute_pilot_matches_golden_repeatedly(self):
        first = run_contract_first(PILOT_MANIFEST)
        second = run_contract_first(PILOT_MANIFEST)
        expected = (PILOT / "expected.run.json").read_text(encoding="utf-8")
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.to_json(), expected)
        self.assertEqual(first.verification_summary, {
            "solver_error": 0,
            "unknown": 0,
            "unsupported": 0,
            "verified": 6,
            "violated": 0,
        })

    def test_guarded_absolute_approval_records_the_human_edit(self):
        proposed = (PILOT / "proposed.cpp").read_text(encoding="utf-8")
        accepted = (PILOT / "accepted.cpp").read_text(encoding="utf-8")
        implemented = (PILOT / "implemented.cpp").read_text(encoding="utf-8")
        self.assertIn("cs: ai requires value > -2147483648", proposed)
        self.assertIn("cs: requires value != -2147483648", accepted)
        self.assertNotIn("cs: ai", accepted)
        accepted_contracts = [
            line for line in accepted.splitlines() if line.startswith("// cs:")
        ]
        implementation_contracts = [
            line for line in implemented.splitlines() if line.startswith("// cs:")
        ]
        self.assertEqual(implementation_contracts, accepted_contracts)

    def test_guarded_absolute_seeded_mismatch_fails_deterministically(self):
        manifest = PILOT / "mismatch.task.json"
        expected = (PILOT / "expected.mismatch.txt").read_text(
            encoding="utf-8"
        ).strip()
        messages = []
        for _ in range(2):
            with self.assertRaises(ContractFirstInputError) as raised:
                run_contract_first(manifest)
            messages.append(f"contract-first error: {raised.exception}")
        self.assertEqual(messages, [expected, expected])

    def test_guarded_absolute_comparison_states_scope_and_tradeoff(self):
        comparison = (PILOT / "comparison.md").read_text(encoding="utf-8")
        self.assertIn("does not claim", comparison)
        self.assertIn("implementation-first", comparison)
        self.assertIn("six verified obligations", comparison)
        self.assertIn("postcondition violation", comparison)


if __name__ == "__main__":
    unittest.main()