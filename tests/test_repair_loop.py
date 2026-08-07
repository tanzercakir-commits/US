from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.checker import AffineChecker
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.repair_bundle import load_repair_bundle_json
from semantic_verifier.repair_loop import (
    MAX_ITERATIONS,
    PATCH_PROPOSAL_SCHEMA,
    PATCH_SCRIPT_SCHEMA,
    REPAIR_LOOP_SCHEMA,
    LineEdit,
    PatchProposal,
    PatchProposer,
    RepairHarness,
    RepairLoopError,
    ScriptedPatchProposer,
    apply_line_edit,
    load_patch_script_json,
    load_repair_loop_json,
)
from semantic_verifier.repair_loop import _sha256


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "repair_loop"
SOURCE_PATH = FIXTURE / "source.cpp"
BUNDLE_PATH = FIXTURE / "bundle.json"
DISPLAY = "fixtures/repair_bundle/violated.cpp"


class RaisingProposer(PatchProposer):
    def propose(self, bundle, iteration):
        raise RuntimeError(f"failure {iteration}")


class RepairLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.checker = AffineChecker()
        cls.report = VerificationPipeline(
            checker=cls.checker,
        ).verify_source(cls.source, DISPLAY)
        cls.bundle = load_repair_bundle_json(
            BUNDLE_PATH.read_text(encoding="utf-8"),
            source=cls.source,
            report=cls.report,
        )

    def proposal(
        self,
        replacement: str,
        *,
        base: str | None = None,
        start: int = 4,
        end: int = 4,
    ) -> PatchProposal:
        return PatchProposal.create(
            base_source_sha256=base or _sha256(
                self.source.encode("utf-8")
            ),
            edit=LineEdit(
                start,
                end,
                (replacement,),
            ),
        )

    def run_loop(self, proposals, *, maximum=3):
        return RepairHarness(
            ScriptedPatchProposer(proposals),
            checker=AffineChecker(),
            max_iterations=maximum,
        ).run(self.source, DISPLAY, self.bundle)

    def test_first_shot_verified_matches_golden_and_preserves_file(self) -> None:
        before = SOURCE_PATH.read_bytes()
        proposal = self.proposal("  return value;")
        log = self.run_loop((proposal,), maximum=3)
        self.assertEqual(log.status, "verified")
        self.assertEqual(len(log.attempts), 1)
        self.assertEqual(log.attempts[0].status, "verified")
        self.assertEqual(
            log.to_json(),
            (FIXTURE / "expected.success.json").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(SOURCE_PATH.read_bytes(), before)
        self.assertIn("return value;", log.accepted_source)

    def test_exhausted_run_logs_exactly_n_attempts(self) -> None:
        proposal = self.proposal("  return 1;")
        log = self.run_loop((proposal,), maximum=2)
        self.assertEqual(log.status, "exhausted")
        self.assertEqual(
            [attempt.status for attempt in log.attempts],
            ["violated", "proposal_error"],
        )
        self.assertEqual(
            log.to_json(),
            (FIXTURE / "expected.exhausted.json").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIsNone(log.accepted_source)

    def test_later_shot_success_and_early_stop(self) -> None:
        stale = self.proposal(
            "  return value;",
            base="sha256:" + "0" * 64,
        )
        success = self.proposal("  return value;")
        unused = self.proposal("  return 2;")
        log = self.run_loop((stale, success, unused), maximum=3)
        self.assertEqual(log.status, "verified")
        self.assertEqual(
            [attempt.status for attempt in log.attempts],
            ["rejected", "verified"],
        )

    def test_replayed_violation_can_feed_the_next_iteration(self) -> None:
        first = self.proposal("  return 1;")
        intermediate = apply_line_edit(
            self.source,
            first.edit,
        )
        second = self.proposal(
            "  return value;",
            base=_sha256(intermediate.encode("utf-8")),
        )
        log = self.run_loop((first, second), maximum=2)
        self.assertEqual(
            [attempt.status for attempt in log.attempts],
            ["violated", "verified"],
        )
        self.assertEqual(log.status, "verified")

    def test_stale_range_noop_duplicate_and_utf8_edits_are_rejected(
        self,
    ) -> None:
        cases = {
            "stale": self.proposal(
                "  return value;",
                base="sha256:" + "0" * 64,
            ),
            "range": self.proposal(
                "  return value;",
                start=99,
                end=99,
            ),
            "noop": self.proposal("  return 0;"),
            "utf8": self.proposal("  return \ud800;"),
        }
        for name, proposal in cases.items():
            with self.subTest(name=name):
                log = self.run_loop((proposal,), maximum=1)
                self.assertEqual(log.status, "exhausted")
                self.assertEqual(
                    log.attempts[0].status,
                    "rejected",
                )

        repeated = self.proposal("  return 1;")
        duplicate = self.run_loop(
            (repeated, repeated),
            maximum=2,
        )
        self.assertEqual(
            [attempt.status for attempt in duplicate.attempts],
            ["violated", "rejected"],
        )
        self.assertIn(
            "already attempted",
            duplicate.attempts[1].diagnostic,
        )

    def test_proposer_exception_is_logged_without_escape(self) -> None:
        log = RepairHarness(
            RaisingProposer(),
            checker=AffineChecker(),
            max_iterations=2,
        ).run(self.source, DISPLAY, self.bundle)
        self.assertEqual(log.status, "exhausted")
        self.assertEqual(len(log.attempts), 2)
        self.assertTrue(
            all(
                attempt.status == "proposal_error"
                for attempt in log.attempts
            )
        )
        self.assertIn(
            "RuntimeError",
            log.attempts[0].diagnostic,
        )

    def test_contract_deletion_cannot_be_reported_as_success(self) -> None:
        proposal = self.proposal(
            "",
            start=2,
            end=4,
        )
        log = self.run_loop((proposal,), maximum=1)
        self.assertEqual(log.status, "exhausted")
        self.assertEqual(log.attempts[0].status, "rejected")
        self.assertIn(
            "contracts",
            log.attempts[0].diagnostic,
        )

    def test_nonverified_candidate_never_uses_proposer_as_referee(self) -> None:
        proposal = self.proposal("  return value * value;")
        log = self.run_loop((proposal,), maximum=1)
        self.assertEqual(log.status, "exhausted")
        self.assertNotEqual(
            log.attempts[0].status,
            "verified",
        )
        self.assertTrue(log.attempts[0].results)

    def test_max_iteration_and_edit_validation(self) -> None:
        proposal = self.proposal("  return value;")
        with self.assertRaises(RepairLoopError):
            self.run_loop((proposal,), maximum=0)
        with self.assertRaises(RepairLoopError):
            self.run_loop((proposal,), maximum=MAX_ITERATIONS + 1)
        for arguments in (
            (0, 1, ()),
            (2, 1, ()),
            (1, 1, ("bad\nline",)),
            (1, 1, ("bad\x00line",)),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(RepairLoopError):
                    LineEdit(*arguments)

    def test_patch_script_loader_is_strict_and_content_addressed(self) -> None:
        proposal = self.proposal("  return value;")
        payload = {
            "proposals": [proposal.to_dict()],
            "schema": PATCH_SCRIPT_SCHEMA,
        }
        loaded = load_patch_script_json(
            json.dumps(payload)
        )
        self.assertEqual(loaded, (proposal,))
        invalid = []
        unknown = json.loads(json.dumps(payload))
        unknown["extra"] = True
        invalid.append(json.dumps(unknown))
        stale = json.loads(json.dumps(payload))
        stale["proposals"][0]["id"] = "sha256:" + "0" * 64
        invalid.append(json.dumps(stale))
        invalid.append(
            json.dumps(payload).replace(
                '"schema":',
                '"schema":"duplicate","schema":',
                1,
            )
        )
        for text in invalid:
            with self.subTest(text=text[:80]):
                with self.assertRaises(RepairLoopError):
                    load_patch_script_json(text)

    def test_repair_log_loader_rejects_unknown_and_stale_identity(self) -> None:
        log = self.run_loop(
            (self.proposal("  return value;"),),
            maximum=1,
        )
        self.assertEqual(
            load_repair_loop_json(log.to_json()),
            log,
        )
        payload = log.to_dict()
        payload["id"] = "sha256:" + "0" * 64
        with self.assertRaises(RepairLoopError):
            load_repair_loop_json(json.dumps(payload))
        payload = log.to_dict()
        payload["extra"] = True
        with self.assertRaises(RepairLoopError):
            load_repair_loop_json(json.dumps(payload))

    def test_relocated_inputs_are_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                outputs = []
                for directory in (first_dir, second_dir):
                    path = Path(directory) / "source.cpp"
                    shutil.copyfile(SOURCE_PATH, path)
                    source = path.read_text(encoding="utf-8")
                    checker = AffineChecker()
                    report = VerificationPipeline(
                        checker=checker,
                    ).verify_source(source, DISPLAY)
                    bundle = load_repair_bundle_json(
                        BUNDLE_PATH.read_text(encoding="utf-8"),
                        source=source,
                        report=report,
                    )
                    proposal = PatchProposal.create(
                        base_source_sha256=_sha256(
                            source.encode("utf-8")
                        ),
                        edit=LineEdit(
                            4,
                            4,
                            ("  return value;",),
                        ),
                    )
                    outputs.append(
                        RepairHarness(
                            ScriptedPatchProposer((proposal,)),
                            checker=checker,
                            max_iterations=1,
                        ).run(
                            source,
                            DISPLAY,
                            bundle,
                        ).to_json()
                    )
                self.assertEqual(outputs[0], outputs[1])
                self.assertNotIn(first_dir, outputs[0])

    def test_cli_generate_check_stale_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "loop.json"
            command = [
                sys.executable,
                str(ROOT / "tools" / "run_repair_loop.py"),
                str(SOURCE_PATH),
                str(BUNDLE_PATH),
                str(FIXTURE / "success.script.json"),
                str(output),
                "--display-path",
                DISPLAY,
                "--max-iterations",
                "3",
                "--backend",
                "affine",
            ]
            generated = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(
                output.read_bytes(),
                (FIXTURE / "expected.success.json").read_bytes(),
            )
            checked = subprocess.run(
                [*command, "--check"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            output.write_bytes(b"stale\n")
            stale = subprocess.run(
                [*command, "--check"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(stale.returncode, 1)
            missing = subprocess.run(
                [
                    *command[:2],
                    str(Path(directory) / "missing.cpp"),
                    *command[3:],
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
