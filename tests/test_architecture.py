from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.architecture import (
    ARCHITECTURE_RESULT_SCHEMA,
    FORBIDDEN_DEPENDENCY_RULE_ID,
    INCOMPLETE_EVIDENCE_RULE_ID,
    enforce_architecture,
)
from semantic_verifier.architecture_policy import (
    ArchitectureLayer,
    ArchitecturePolicy,
    DependencyRule,
    LayerSelector,
    read_architecture_policy,
)
from semantic_verifier.fact_queries import read_fact_index


ROOT = Path(__file__).resolve().parents[1]
WORLD_PATH = ROOT / "fixtures" / "facts" / "expected" / "world.fact-index.json"
LIMITATIONS_PATH = (
    ROOT / "fixtures" / "facts" / "expected" / "limitations.fact-index.json"
)
POLICY_PATH = ROOT / "fixtures" / "architecture" / "policy.json"
RESULT_GOLDEN = (
    ROOT / "fixtures" / "architecture" / "expected.result.json"
)
SARIF_GOLDEN = (
    ROOT / "fixtures" / "architecture" / "expected.sarif.json"
)
TOOL = ROOT / "tools" / "check_architecture.py"


def policy_for(layers, decision_for=None):
    names = tuple(layer.name for layer in layers)
    rules = tuple(
        DependencyRule(
            source,
            target,
            (
                decision_for(source, target)
                if decision_for is not None
                else "allow"
            ),
        )
        for source in names
        for target in names
    )
    return ArchitecturePolicy.create(
        layers=layers,
        dependencies=rules,
    )


class ArchitectureEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = read_fact_index(WORLD_PATH)
        cls.limited_index = read_fact_index(LIMITATIONS_PATH)
        cls.policy = read_architecture_policy(POLICY_PATH)
        cls.report = enforce_architecture(cls.index, cls.policy)

    def run_cli(self, index, policy, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(index),
                str(policy),
                *arguments,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    def test_frozen_result_is_canonical_and_reports_all_call_decisions(self):
        expected = RESULT_GOLDEN.read_text(encoding="utf-8")
        self.assertEqual(self.report.to_json(), expected)
        payload = json.loads(expected)
        self.assertEqual(payload["schema"], ARCHITECTURE_RESULT_SCHEMA)
        self.assertEqual(payload["status"], "violation")
        self.assertEqual(
            payload["summary"],
            {
                "allowed": 2,
                "calls": 3,
                "decided": 3,
                "forbidden": 1,
                "undecided_calls": 0,
                "unknowns": 0,
            },
        )
        self.assertEqual(payload["unknowns"], [])
        self.assertEqual(self.report.exit_code, 1)

    def test_forbidden_dependency_carries_exact_call_and_source_evidence(self):
        forbidden = [
            decision
            for decision in self.report.decisions
            if decision.decision == "forbid"
        ]
        self.assertEqual(len(forbidden), 1)
        decision = forbidden[0]
        self.assertEqual(decision.source_layer, "orchestration")
        self.assertEqual(decision.target_layer, "storage")
        self.assertEqual(
            decision.caller["qualified_name"],
            "pipeline",
        )
        self.assertEqual(
            decision.callee["qualified_name"],
            "store",
        )
        self.assertEqual(
            decision.location,
            {
                "column": 12,
                "file": "fixtures/facts/cases/world.cpp",
                "line": 25,
            },
        )
        matching_call = next(
            call
            for call in self.index.calls
            if call.id == decision.call_id
        )
        self.assertEqual(
            matching_call.location.to_dict(),
            decision.location,
        )

    def test_allowed_and_forbidden_rows_cover_each_direct_call_once(self):
        self.assertEqual(
            {decision.call_id for decision in self.report.decisions},
            {call.id for call in self.index.calls},
        )
        self.assertEqual(
            len(self.report.decisions),
            len(self.index.calls),
        )
        pairs = {
            (
                decision.caller["qualified_name"],
                decision.callee["qualified_name"],
            ): decision.decision
            for decision in self.report.decisions
        }
        self.assertEqual(
            pairs,
            {
                ("pipeline", "math::normalize"): "allow",
                ("pipeline", "store"): "forbid",
                ("store", "math::normalize"): "allow",
            },
        )
        locations = [
            (
                item.location["file"],
                item.location["line"],
                item.location["column"],
            )
            for item in self.report.decisions
        ]
        self.assertEqual(locations, sorted(locations))

    def test_sarif_golden_has_stable_rules_uri_region_and_fingerprint(self):
        expected = SARIF_GOLDEN.read_text(encoding="utf-8")
        self.assertEqual(self.report.to_sarif(), expected)
        payload = json.loads(expected)
        self.assertEqual(payload["version"], "2.1.0")
        run = payload["runs"][0]
        self.assertEqual(
            [rule["id"] for rule in run["tool"]["driver"]["rules"]],
            [
                FORBIDDEN_DEPENDENCY_RULE_ID,
                INCOMPLETE_EVIDENCE_RULE_ID,
            ],
        )
        self.assertEqual(len(run["results"]), 1)
        result = run["results"][0]
        self.assertEqual(
            result["ruleId"],
            FORBIDDEN_DEPENDENCY_RULE_ID,
        )
        physical = result["locations"][0]["physicalLocation"]
        self.assertEqual(
            physical["artifactLocation"],
            {
                "uri": "fixtures/facts/cases/world.cpp",
                "uriBaseId": "%SRCROOT%",
            },
        )
        self.assertEqual(
            physical["region"],
            {
                "startColumn": 12,
                "startLine": 25,
            },
        )
        self.assertEqual(
            result["partialFingerprints"]["callFactId"],
            next(
                decision.call_id
                for decision in self.report.decisions
                if decision.decision == "forbid"
            ),
        )
        for marker in (
            "C:\\Projects\\US",
            "C:/Projects/US",
            '"clock"',
            '"duration"',
            '"random"',
            '"verified"',
            '"proved"',
        ):
            self.assertNotIn(marker, expected)

    def test_single_source_layer_and_explicit_self_allow_are_clean(self):
        policy = policy_for(
            (
                ArchitectureLayer(
                    "all",
                    (
                        LayerSelector(
                            "source_prefix",
                            "fixtures/facts/cases",
                        ),
                    ),
                ),
            )
        )
        report = enforce_architecture(self.index, policy)
        self.assertEqual(report.status, "clean")
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(len(report.decisions), 3)
        self.assertTrue(
            all(
                decision.decision == "allow"
                for decision in report.decisions
            )
        )
        self.assertEqual(
            report.to_sarif_dict()["runs"][0]["results"],
            [],
        )

    def test_unclassified_call_endpoints_are_unknown_not_allowed(self):
        policy = policy_for(
            (
                ArchitectureLayer(
                    "entry",
                    (
                        LayerSelector(
                            "qualified_name",
                            "pipeline",
                        ),
                    ),
                ),
            )
        )
        report = enforce_architecture(self.index, policy)
        self.assertEqual(report.status, "unknown")
        self.assertEqual(report.exit_code, 2)
        self.assertEqual(report.decisions, ())
        self.assertGreater(len(report.unknowns), 0)
        self.assertEqual(
            {
                unknown.code
                for unknown in report.unknowns
            },
            {"unclassified_call_endpoint"},
        )
        self.assertEqual(
            report.to_dict()["summary"]["undecided_calls"],
            3,
        )

    def test_overlapping_selectors_are_ambiguous_without_order_tie_break(self):
        policy = policy_for(
            (
                ArchitectureLayer(
                    "exact",
                    (
                        LayerSelector(
                            "qualified_name",
                            "pipeline",
                        ),
                    ),
                ),
                ArchitectureLayer(
                    "source",
                    (
                        LayerSelector(
                            "source_prefix",
                            "fixtures/facts/cases",
                        ),
                    ),
                ),
            )
        )
        report = enforce_architecture(self.index, policy)
        ambiguous = [
            unknown
            for unknown in report.unknowns
            if unknown.code == "ambiguous_call_endpoint"
        ]
        self.assertEqual(report.status, "unknown")
        self.assertEqual(len(ambiguous), 2)
        for unknown in ambiguous:
            self.assertEqual(
                unknown.evidence["layers"],
                ["exact", "source"],
            )
            self.assertEqual(
                unknown.evidence["endpoint"],
                "caller",
            )
        self.assertEqual(len(report.decisions), 1)

    def test_fact_limitations_make_forbidden_result_unknown_by_precedence(self):
        layers = (
            ArchitectureLayer(
                "caller",
                (
                    LayerSelector(
                        "qualified_name",
                        "declaration_call",
                    ),
                ),
            ),
            ArchitectureLayer(
                "external",
                (
                    LayerSelector(
                        "qualified_name",
                        "external",
                    ),
                ),
            ),
        )
        policy = policy_for(
            layers,
            lambda source, target: (
                "forbid"
                if (source, target) == ("caller", "external")
                else "allow"
            ),
        )
        report = enforce_architecture(self.limited_index, policy)
        self.assertEqual(len(report.decisions), 1)
        self.assertEqual(
            report.decisions[0].decision,
            "forbid",
        )
        self.assertEqual(
            len(report.unknowns),
            len(self.limited_index.limitations),
        )
        self.assertEqual(
            {
                unknown.code
                for unknown in report.unknowns
            },
            {"fact_index_limitation"},
        )
        self.assertEqual(report.status, "unknown")
        self.assertEqual(report.exit_code, 2)
        sarif_rules = {
            result["ruleId"]
            for result in report.to_sarif_dict()["runs"][0]["results"]
        }
        self.assertEqual(
            sarif_rules,
            {
                FORBIDDEN_DEPENDENCY_RULE_ID,
                INCOMPLETE_EVIDENCE_RULE_ID,
            },
        )

    def test_repeated_and_relocated_inputs_are_byte_stable(self):
        first_json = self.report.to_json()
        first_sarif = self.report.to_sarif()
        second = enforce_architecture(self.index, self.policy)
        self.assertEqual(second.to_json(), first_json)
        self.assertEqual(second.to_sarif(), first_sarif)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = root / "index.json"
            policy_path = root / "policy.json"
            shutil.copyfile(WORLD_PATH, index_path)
            shutil.copyfile(POLICY_PATH, policy_path)
            relocated = enforce_architecture(
                read_fact_index(index_path),
                read_architecture_policy(policy_path),
            )
        self.assertEqual(relocated.to_json(), first_json)
        self.assertEqual(relocated.to_sarif(), first_sarif)

    def test_cli_formats_exit_codes_and_input_failure(self):
        expected_outputs = {
            "json": self.report.to_json(),
            "sarif": self.report.to_sarif(),
            "text": self.report.to_text(),
        }
        for output_format, expected in expected_outputs.items():
            completed = self.run_cli(
                WORLD_PATH,
                POLICY_PATH,
                "--format",
                output_format,
            )
            with self.subTest(output_format=output_format):
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(completed.stdout, expected)
                self.assertEqual(completed.stderr, "")

        unknown = self.run_cli(
            LIMITATIONS_PATH,
            POLICY_PATH,
        )
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(
            json.loads(unknown.stdout)["status"],
            "unknown",
        )

        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(
                '{"schema":"wrong"}\n',
                encoding="utf-8",
                newline="\n",
            )
            bad = self.run_cli(
                invalid,
                POLICY_PATH,
            )
        self.assertEqual(bad.returncode, 3)
        self.assertEqual(bad.stdout, "")
        self.assertIn("architecture input error", bad.stderr)


if __name__ == "__main__":
    unittest.main()
