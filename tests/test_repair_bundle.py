from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.backend import CheckerBackend, create_backend
from semantic_verifier.checker import AffineChecker
from semantic_verifier.model import (
    VerificationReport,
    VerificationStatus,
)
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.repair_bundle import (
    REPAIR_BUNDLE_SCHEMA,
    REFEREE_IDS,
    RepairBundleBuilder,
    RepairBundleError,
    load_repair_bundle_json,
)
from semantic_verifier.z3_backend import (
    Z3DiscoveryError,
    discover_z3,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "repair_bundle"
SOURCE_PATH = FIXTURE / "violated.cpp"
GOLDEN = FIXTURE / "expected.bundle.json"
DISPLAY = "fixtures/repair_bundle/violated.cpp"
SCHEMA_PATH = (
    ROOT
    / "semantic_verifier"
    / "repair_bundle_schema"
    / "v1"
    / "index.schema.json"
)


class CustomChecker(CheckerBackend):
    name = "custom"

    def check(self, obligation):
        return AffineChecker().check(obligation)


class RepairBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.checker = AffineChecker()
        cls.report = VerificationPipeline(
            checker=cls.checker,
        ).verify_source(cls.source, DISPLAY)
        cls.target = next(
            result.obligation_id
            for result in cls.report.results
            if result.status == VerificationStatus.VIOLATED
            and result.counterexample
        )

    def build(self, *, context_lines: int = 4):
        return RepairBundleBuilder(
            checker=self.checker,
            context_lines=context_lines,
        ).build(
            self.source,
            DISPLAY,
            self.report,
            self.target,
        )

    def test_affine_replayed_violation_matches_frozen_golden(self) -> None:
        bundle = self.build()
        self.assertEqual(
            bundle.to_json(),
            GOLDEN.read_text(encoding="utf-8"),
        )
        loaded = load_repair_bundle_json(
            bundle.to_json(),
            source=self.source,
            report=self.report,
        )
        self.assertEqual(loaded, bundle)
        self.assertEqual(
            bundle.result["status"],
            "violated",
        )
        self.assertTrue(bundle.result["counterexample"])
        self.assertEqual(
            bundle.obligation["id"],
            bundle.result["obligation"],
        )

    def test_source_slice_and_contract_provenance_are_exact(self) -> None:
        bundle = self.build()
        self.assertEqual(bundle.source_slice.start_line, 1)
        self.assertEqual(bundle.source_slice.end_line, 5)
        self.assertEqual(
            tuple(line.text for line in bundle.source_slice.lines),
            tuple(self.source.splitlines()),
        )
        self.assertEqual(
            [
                (
                    contract.kind,
                    contract.machine_proposed,
                    contract.location.line,
                )
                for contract in bundle.contracts
            ],
            [
                ("requires", True, 1),
                ("ensures", False, 2),
            ],
        )

    def test_source_slice_radius_is_bounded_and_clamped(self) -> None:
        bundle = self.build(context_lines=0)
        self.assertEqual(
            bundle.source_slice.start_line,
            bundle.result["location"]["line"],
        )
        self.assertEqual(
            bundle.source_slice.end_line,
            bundle.result["location"]["line"],
        )
        with self.assertRaises(RepairBundleError):
            RepairBundleBuilder(
                checker=self.checker,
                context_lines=21,
            )
        with self.assertRaises(RepairBundleError):
            RepairBundleBuilder(
                checker=self.checker,
                context_lines=True,
            )

    def test_shuffled_input_serializes_to_identical_canonical_bytes(self) -> None:
        bundle = self.build()
        payload = bundle.to_dict()
        payload["contracts"].reverse()
        payload["source_slice"]["lines"].reverse()
        payload["source_slice"]["lines"].reverse()
        loaded = load_repair_bundle_json(
            json.dumps(payload, separators=(",", ":")),
            source=self.source,
            report=self.report,
        )
        self.assertEqual(loaded.to_json(), bundle.to_json())

    def test_strict_json_rejects_duplicate_unknown_and_nested_unknown_fields(
        self,
    ) -> None:
        payload = self.build().to_dict()
        cases = []
        root_unknown = json.loads(json.dumps(payload))
        root_unknown["extra"] = True
        cases.append(json.dumps(root_unknown))
        nested_unknown = json.loads(json.dumps(payload))
        nested_unknown["obligation"]["conclusion"]["extra"] = True
        cases.append(json.dumps(nested_unknown))
        cases.append(
            self.build().to_json().replace(
                '"schema":',
                '"schema":"duplicate","schema":',
                1,
            )
        )
        cases.append(
            self.build().to_json().replace(
                '"contracts":',
                '"number":NaN,"contracts":',
                1,
            )
        )
        for candidate in cases:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(RepairBundleError):
                    load_repair_bundle_json(
                        candidate,
                        source=self.source,
                        report=self.report,
                    )

    def test_stale_identity_source_and_report_links_fail_closed(self) -> None:
        base = self.build().to_dict()
        mutations = []
        identity = json.loads(json.dumps(base))
        identity["id"] = "sha256:" + "0" * 64
        mutations.append((identity, self.source, self.report))
        source_hash = json.loads(json.dumps(base))
        source_hash["source"]["sha256"] = "sha256:" + "0" * 64
        mutations.append((source_hash, self.source, self.report))
        report_hash = json.loads(json.dumps(base))
        report_hash["verification"]["sha256"] = "sha256:" + "0" * 64
        mutations.append((report_hash, self.source, self.report))
        for payload, source, report in mutations:
            with self.subTest(payload=payload):
                with self.assertRaises(RepairBundleError):
                    load_repair_bundle_json(
                        json.dumps(payload),
                        source=source,
                        report=report,
                    )

    def test_result_and_obligation_drift_from_report_is_rejected(self) -> None:
        base = self.build().to_dict()
        result = json.loads(json.dumps(base))
        result["result"]["message"] += " changed"
        result["id"] = self.build().id
        with self.assertRaises(RepairBundleError):
            load_repair_bundle_json(
                json.dumps(result),
                source=self.source,
                report=self.report,
            )

        obligation = json.loads(json.dumps(base))
        obligation["obligation"]["description"] += " changed"
        with self.assertRaises(RepairBundleError):
            load_repair_bundle_json(
                json.dumps(obligation),
                source=self.source,
                report=self.report,
            )

    def test_nonviolated_missing_and_report_reproduction_targets_fail(self) -> None:
        verified = next(
            result.obligation_id
            for result in self.report.results
            if result.status == VerificationStatus.VERIFIED
        )
        builder = RepairBundleBuilder(checker=self.checker)
        for target in (verified, "ob99999"):
            with self.subTest(target=target):
                with self.assertRaises(RepairBundleError):
                    builder.build(
                        self.source,
                        DISPLAY,
                        self.report,
                        target,
                    )
        with self.assertRaisesRegex(
            RepairBundleError,
            "reproduction mismatch",
        ):
            builder.build(
                self.source.replace("return 0;", "return 1;"),
                DISPLAY,
                self.report,
                self.target,
            )

    def test_independent_replay_must_reproduce_exact_result(self) -> None:
        checker = AffineChecker()
        report = VerificationPipeline(
            checker=checker,
        ).verify_source(self.source, DISPLAY)
        target = next(
            result.obligation_id
            for result in report.results
            if result.status == VerificationStatus.VIOLATED
        )
        original = checker.check
        calls = 0

        def changed_replay(obligation):
            nonlocal calls
            calls += 1
            result = original(obligation)
            if calls > len(report.obligations):
                return replace(
                    result,
                    message=result.message + " changed",
                )
            return result

        with patch.object(checker, "check", side_effect=changed_replay):
            with self.assertRaisesRegex(
                RepairBundleError,
                "replay did not reproduce",
            ):
                RepairBundleBuilder(checker=checker).build(
                    self.source,
                    DISPLAY,
                    report,
                    target,
                )

    def test_referee_identity_is_bound_to_exact_builtin_checker(self) -> None:
        with self.assertRaisesRegex(
            RepairBundleError,
            "not an admitted",
        ):
            RepairBundleBuilder(checker=CustomChecker())
        with self.assertRaisesRegex(
            RepairBundleError,
            "does not match",
        ):
            RepairBundleBuilder(
                checker=AffineChecker(),
                referee="codeskeptic.z3/v1",
            )

    def test_relocated_source_with_frozen_display_path_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                outputs = []
                for directory in (first_dir, second_dir):
                    path = Path(directory) / "copy.cpp"
                    shutil.copyfile(SOURCE_PATH, path)
                    source = path.read_text(encoding="utf-8")
                    checker = AffineChecker()
                    report = VerificationPipeline(
                        checker=checker,
                    ).verify_source(source, DISPLAY)
                    target = next(
                        result.obligation_id
                        for result in report.results
                        if result.status == VerificationStatus.VIOLATED
                        and result.counterexample
                    )
                    outputs.append(
                        RepairBundleBuilder(
                            checker=checker,
                        ).build(
                            source,
                            DISPLAY,
                            report,
                            target,
                        ).to_json()
                    )
                self.assertEqual(outputs[0], outputs[1])
                self.assertNotIn(first_dir, outputs[0])
                self.assertNotIn(second_dir, outputs[0])

    def test_z3_replay_path_when_installed(self) -> None:
        try:
            z3 = discover_z3()
        except Z3DiscoveryError:
            self.skipTest("Z3 is not installed")
        checker = create_backend("z3", z3=z3)
        report = VerificationPipeline(
            checker=checker,
        ).verify_source(self.source, DISPLAY)
        target = next(
            result.obligation_id
            for result in report.results
            if result.status == VerificationStatus.VIOLATED
            and result.counterexample
        )
        bundle = RepairBundleBuilder(
            checker=checker,
            referee="codeskeptic.z3/v1",
        ).build(
            self.source,
            DISPLAY,
            report,
            target,
        )
        self.assertEqual(
            bundle.referee,
            "codeskeptic.z3/v1",
        )

    def test_cli_generate_check_stale_and_error_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.json"
            command = [
                sys.executable,
                str(ROOT / "tools" / "generate_repair_bundle.py"),
                str(SOURCE_PATH),
                str(output),
                "--display-path",
                DISPLAY,
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
            self.assertEqual(output.read_bytes(), GOLDEN.read_bytes())
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

    def test_json_schema_matches_runtime_contract(self) -> None:
        schema = json.loads(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            REPAIR_BUNDLE_SCHEMA,
        )
        self.assertEqual(
            set(schema["properties"]["referee"]["enum"]),
            REFEREE_IDS,
        )
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
