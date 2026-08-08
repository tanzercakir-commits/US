from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.architecture_policy import (
    ARCHITECTURE_POLICY_SCHEMA,
    ArchitectureLayer,
    ArchitecturePolicy,
    ArchitecturePolicyError,
    DependencyRule,
    LayerSelector,
    load_architecture_policy,
    load_architecture_policy_json,
    read_architecture_policy,
)
from semantic_verifier.fact_queries import FactWorld, read_fact_index


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "fixtures" / "architecture" / "policy.json"
WORLD_PATH = ROOT / "fixtures" / "facts" / "expected" / "world.fact-index.json"
TOOL = ROOT / "tools" / "validate_architecture_policy.py"


def complete_rules(names, decision="allow"):
    return tuple(
        DependencyRule(source, target, decision)
        for source in names
        for target in names
    )


class ArchitecturePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = read_architecture_policy(POLICY_PATH)
        cls.world = FactWorld(read_fact_index(WORLD_PATH))

    def test_frozen_policy_round_trips_canonically_with_content_id(self):
        text = POLICY_PATH.read_text(encoding="utf-8")
        self.assertEqual(self.policy.to_json(), text)
        self.assertEqual(
            self.policy.to_dict()["schema"],
            ARCHITECTURE_POLICY_SCHEMA,
        )
        self.assertRegex(
            self.policy.id,
            r"^sha256:[0-9a-f]{64}$",
        )
        loaded = load_architecture_policy_json(text)
        self.assertEqual(loaded, self.policy)
        self.assertEqual(
            json.loads(loaded.to_json()),
            loaded.to_dict(),
        )

    def test_shuffled_arrays_have_identical_canonical_bytes(self):
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        payload["layers"].reverse()
        payload["dependencies"].reverse()
        for layer in payload["layers"]:
            layer["selectors"].reverse()
        shuffled = load_architecture_policy(payload)
        self.assertEqual(shuffled, self.policy)
        self.assertEqual(shuffled.to_json(), self.policy.to_json())

    def test_exact_prefix_and_unclassified_symbols_are_explicit(self):
        self.assertEqual(
            self.policy.classify(self.world.select("pipeline")),
            ("orchestration",),
        )
        self.assertEqual(
            self.policy.classify(self.world.select("store")),
            ("storage",),
        )
        normalize = [
            symbol
            for symbol in self.world.index.symbols
            if symbol.qualified_name == "math::normalize"
        ]
        self.assertEqual(len(normalize), 2)
        for symbol in normalize:
            self.assertEqual(
                self.policy.classify(symbol),
                ("utility",),
            )
        self.assertEqual(
            self.policy.classify(self.world.select("global_total")),
            (),
        )

    def test_source_prefix_normalizes_and_multiple_matches_do_not_tie_break(self):
        source_selector = LayerSelector(
            "source_prefix",
            r".\fixtures\facts\cases",
        )
        self.assertEqual(
            source_selector.value,
            "fixtures/facts/cases",
        )
        layers = (
            ArchitectureLayer(
                "namespace",
                (
                    LayerSelector(
                        "qualified_name_prefix",
                        "math::",
                    ),
                ),
            ),
            ArchitectureLayer("source", (source_selector,)),
        )
        policy = ArchitecturePolicy.create(
            layers=layers,
            dependencies=complete_rules(
                ("namespace", "source"),
            ),
        )
        normalize = next(
            symbol
            for symbol in self.world.index.symbols
            if symbol.qualified_name == "math::normalize"
        )
        self.assertEqual(
            policy.classify(normalize),
            ("namespace", "source"),
        )

    def test_complete_matrix_has_every_self_and_cross_decision(self):
        names = tuple(layer.name for layer in self.policy.layers)
        self.assertEqual(
            len(self.policy.dependencies),
            len(names) * len(names),
        )
        expected = {
            ("orchestration", "storage"): "forbid",
            ("orchestration", "utility"): "allow",
            ("storage", "utility"): "allow",
            ("utility", "storage"): "forbid",
        }
        for source in names:
            for target in names:
                decision = self.policy.decision(source, target)
                self.assertIn(decision, {"allow", "forbid"})
                if source == target:
                    self.assertEqual(decision, "allow")
        for pair, decision in expected.items():
            self.assertEqual(self.policy.decision(*pair), decision)
        with self.assertRaises(ArchitecturePolicyError):
            self.policy.decision("missing", "utility")

    def test_schema_unknown_fields_duplicate_keys_and_nonfinite_fail(self):
        valid = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cases = []

        wrong_schema = dict(valid)
        wrong_schema["schema"] = "wrong"
        cases.append(wrong_schema)

        extra = dict(valid)
        extra["unexpected"] = True
        cases.append(extra)

        layer_extra = json.loads(json.dumps(valid))
        layer_extra["layers"][0]["unexpected"] = True
        cases.append(layer_extra)

        selector_extra = json.loads(json.dumps(valid))
        selector_extra["layers"][0]["selectors"][0]["extra"] = True
        cases.append(selector_extra)

        rule_extra = json.loads(json.dumps(valid))
        rule_extra["dependencies"][0]["extra"] = True
        cases.append(rule_extra)

        stale_id = json.loads(json.dumps(valid))
        stale_id["dependencies"][0]["decision"] = "forbid"
        cases.append(stale_id)

        for payload in cases:
            with self.subTest(keys=sorted(payload)):
                with self.assertRaises(ArchitecturePolicyError):
                    load_architecture_policy(payload)

        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "duplicate JSON object key",
        ):
            load_architecture_policy_json(
                '{"schema":"a","schema":"b"}'
            )
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "non-finite",
        ):
            load_architecture_policy_json('{"value":NaN}')

    def test_duplicate_layers_selectors_pairs_and_missing_pairs_fail(self):
        layer_a = ArchitectureLayer(
            "a",
            (LayerSelector("qualified_name", "a::run"),),
        )
        layer_b = ArchitectureLayer(
            "b",
            (LayerSelector("qualified_name", "b::run"),),
        )
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "duplicate layer",
        ):
            ArchitecturePolicy.create(
                layers=(layer_a, layer_a),
                dependencies=complete_rules(("a",)),
            )

        duplicate_selector = ArchitectureLayer(
            "b",
            (LayerSelector("qualified_name", "a::run"),),
        )
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "duplicate selectors",
        ):
            ArchitecturePolicy.create(
                layers=(layer_a, duplicate_selector),
                dependencies=complete_rules(("a", "b")),
            )

        rules = list(complete_rules(("a", "b")))
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "missing dependency pairs",
        ):
            ArchitecturePolicy.create(
                layers=(layer_a, layer_b),
                dependencies=rules[:-1],
            )
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "duplicate dependency pairs",
        ):
            ArchitecturePolicy.create(
                layers=(layer_a, layer_b),
                dependencies=(*rules, rules[0]),
            )
        with self.assertRaisesRegex(
            ArchitecturePolicyError,
            "unknown layer",
        ):
            ArchitecturePolicy.create(
                layers=(layer_a, layer_b),
                dependencies=(
                    *rules,
                    DependencyRule("a", "missing", "allow"),
                ),
            )

    def test_invalid_names_selectors_decisions_and_paths_fail(self):
        invalid_constructors = (
            lambda: ArchitectureLayer(
                "Bad_Name",
                (LayerSelector("qualified_name", "x"),),
            ),
            lambda: ArchitectureLayer("empty", ()),
            lambda: LayerSelector("glob", "*"),
            lambda: DependencyRule("a", "b", "maybe"),
            lambda: LayerSelector("source_prefix", "../src"),
            lambda: LayerSelector("source_prefix", "/src"),
            lambda: LayerSelector("source_prefix", "C:/src"),
            lambda: LayerSelector("source_prefix", "src//core"),
        )
        for constructor in invalid_constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaises(ArchitecturePolicyError):
                    constructor()

    def test_cli_emits_canonical_policy_and_rejects_bad_input(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(POLICY_PATH),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, self.policy.to_json())
        self.assertEqual(completed.stderr, "")

        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(
                '{"schema":"wrong"}\n',
                encoding="utf-8",
                newline="\n",
            )
            bad = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(invalid),
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertIn("architecture-policy error", bad.stderr)


if __name__ == "__main__":
    unittest.main()
