from __future__ import annotations

import json
from pathlib import Path
import unittest

from semantic_verifier.fact_extractor import extract_facts
from semantic_verifier.fact_trust import (
    FACT_TRUST_SCHEMA,
    PROOF_METHOD,
    REFEREE_IDS,
    TRUST_LABELS,
    FactTrustClaim,
    FactTrustError,
    FactTrustIndex,
    ProofEvidence,
    load_fact_trust_json,
    verification_sha256,
)
from semantic_verifier.facts import FactLocation
from semantic_verifier.model import SCHEMA as VERIFICATION_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "semantic_verifier"
    / "fact_trust_schema"
    / "v1"
    / "index.schema.json"
)
SOURCE = (
    "int leaf(int value) { return value; }\n"
    "int caller(int value) { return leaf(value); }\n"
    "void dirty(int &value) { value = 1; }\n"
)
DISPLAY = "trust/example.cpp"


class FactTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = extract_facts(SOURCE, DISPLAY)
        cls.functions = {
            symbol.qualified_name: symbol.id
            for symbol in cls.index.symbols
            if symbol.kind == "function"
        }

    def evidence(
        self,
        *,
        line: int,
        obligations: tuple[str, ...],
        callees: tuple[str, ...] = (),
    ) -> ProofEvidence:
        return ProofEvidence(
            self.index.source.content_sha256,
            verification_sha256(b"canonical verification report\n"),
            VERIFICATION_SCHEMA,
            "codeskeptic.affine/v1",
            obligations,
            FactLocation(DISPLAY, line, 1),
            callees,
        )

    def claims(
        self,
        proved: frozenset[str] = frozenset(),
    ) -> tuple[FactTrustClaim, ...]:
        lines = {"leaf": 1, "caller": 2, "dirty": 3}
        direct = {
            "leaf": (),
            "caller": (self.functions["leaf"],),
            "dirty": (),
        }
        result = []
        for row in self.index.purity:
            name = next(
                key
                for key, identity in self.functions.items()
                if identity == row.function
            )
            is_proved = name in proved
            result.append(
                FactTrustClaim.create(
                    function=row.function,
                    value=row.status,
                    trust="proved" if is_proved else "derived",
                    evidence=(
                        self.evidence(
                            line=lines[name],
                            obligations=(
                                f"ob{lines[name]:05d}",
                            ),
                            callees=direct[name],
                        )
                        if is_proved
                        else None
                    ),
                )
            )
        return tuple(result)

    def test_derived_overlay_covers_d1_without_mutating_it(self) -> None:
        before = self.index.to_json()
        overlay = FactTrustIndex.derived(self.index)
        self.assertEqual(
            tuple(claim.function for claim in overlay.claims),
            tuple(sorted(row.function for row in self.index.purity)),
        )
        self.assertEqual(
            {claim.trust for claim in overlay.claims},
            {"derived"},
        )
        self.assertTrue(
            all(claim.evidence is None for claim in overlay.claims)
        )
        self.assertEqual(self.index.to_json(), before)
        self.assertEqual(
            load_fact_trust_json(
                overlay.to_json(),
                self.index,
            ),
            overlay,
        )

    def test_proved_leaf_and_call_chain_are_canonical(self) -> None:
        overlay = FactTrustIndex.create(
            self.index,
            self.claims(frozenset({"leaf", "caller"})),
        )
        claims = {
            claim.function: claim
            for claim in overlay.claims
        }
        leaf = claims[self.functions["leaf"]]
        caller = claims[self.functions["caller"]]
        self.assertEqual(leaf.trust, "proved")
        self.assertEqual(leaf.evidence.callees, ())
        self.assertEqual(
            caller.evidence.callees,
            (self.functions["leaf"],),
        )
        self.assertEqual(
            load_fact_trust_json(overlay.to_json(), self.index),
            overlay,
        )

    def test_shuffled_input_has_identical_canonical_bytes(self) -> None:
        overlay = FactTrustIndex.create(
            self.index,
            self.claims(frozenset({"leaf", "caller"})),
        )
        payload = overlay.to_dict()
        payload["claims"].reverse()
        for claim in payload["claims"]:
            evidence = claim["evidence"]
            if evidence is not None:
                evidence["obligations"].reverse()
                evidence["callees"].reverse()
        loaded = load_fact_trust_json(
            json.dumps(payload, separators=(",", ":")),
            self.index,
        )
        self.assertEqual(loaded.to_json(), overlay.to_json())

    def test_trust_value_and_evidence_rules_fail_closed(self) -> None:
        pure = self.functions["leaf"]
        dirty = self.functions["dirty"]
        evidence = self.evidence(
            line=1,
            obligations=("ob00001",),
        )
        cases = (
            lambda: FactTrustClaim.create(
                function=pure,
                value="pure",
                trust="derived",
                evidence=evidence,
            ),
            lambda: FactTrustClaim.create(
                function=pure,
                value="pure",
                trust="proved",
            ),
            lambda: FactTrustClaim.create(
                function=dirty,
                value="impure",
                trust="proved",
                evidence=evidence,
            ),
            lambda: FactTrustClaim.create(
                function=pure,
                value="invented",
            ),
            lambda: FactTrustClaim.create(
                function=pure,
                value="pure",
                trust="trusted",
            ),
            lambda: ProofEvidence(
                self.index.source.content_sha256,
                verification_sha256(b"report"),
                VERIFICATION_SCHEMA,
                "codeskeptic.affine/v1",
                (),
                FactLocation(DISPLAY, 1, 1),
            ),
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(FactTrustError):
                    case()

    def test_evidence_shape_is_strict_and_sorted(self) -> None:
        evidence = ProofEvidence(
            self.index.source.content_sha256,
            verification_sha256(b"report"),
            VERIFICATION_SCHEMA,
            "codeskeptic.affine/v1",
            ("ob00002", "ob00001"),
            FactLocation(DISPLAY, 1, 1),
            (self.functions["leaf"],),
        )
        self.assertEqual(
            evidence.obligations,
            ("ob00001", "ob00002"),
        )
        invalid = (
            {"referee": "unrecognized"},
            {"method": "other"},
            {"verification_schema": "wrong"},
            {"obligations": ("bad",)},
            {"obligations": ("ob00001", "ob00001")},
            {"callees": (self.functions["leaf"],) * 2},
        )
        base = {
            "source_sha256": self.index.source.content_sha256,
            "verification_sha256": verification_sha256(b"report"),
            "verification_schema": VERIFICATION_SCHEMA,
            "referee": "codeskeptic.affine/v1",
            "obligations": ("ob00001",),
            "frame": FactLocation(DISPLAY, 1, 1),
            "callees": (),
            "method": PROOF_METHOD,
        }
        for mutation in invalid:
            with self.subTest(mutation=mutation):
                values = {**base, **mutation}
                with self.assertRaises(FactTrustError):
                    ProofEvidence(**values)

    def test_strict_json_rejects_duplicates_unknowns_and_constants(self) -> None:
        overlay = FactTrustIndex.derived(self.index)
        text = overlay.to_json()
        payload = json.loads(text)
        payload["extra"] = True
        candidates = (
            text.replace(
                '"schema":',
                '"schema":"duplicate","schema":',
                1,
            ),
            json.dumps(payload),
            text.replace(
                '"claims":',
                '"number":NaN,"claims":',
                1,
            ),
            "[]",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(FactTrustError):
                    load_fact_trust_json(candidate, self.index)

    def test_stale_claim_and_overlay_identities_are_rejected(self) -> None:
        overlay = FactTrustIndex.derived(self.index)
        payload = overlay.to_dict()
        payload["id"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(FactTrustError, "trust.id"):
            load_fact_trust_json(json.dumps(payload), self.index)

        payload = overlay.to_dict()
        payload["claims"][0]["id"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(FactTrustError, "claim.id"):
            load_fact_trust_json(json.dumps(payload), self.index)

    def test_d1_cross_validation_rejects_missing_dangling_and_value_drift(
        self,
    ) -> None:
        derived = list(FactTrustIndex.derived(self.index).claims)
        with self.assertRaisesRegex(FactTrustError, "missing"):
            FactTrustIndex.create(self.index, derived[:-1])

        first = derived[0]
        changed_value = "pure" if first.value != "pure" else "unknown"
        drifted = [
            FactTrustClaim.create(
                function=first.function,
                value=changed_value,
            ),
            *derived[1:],
        ]
        with self.assertRaisesRegex(FactTrustError, "does not match"):
            FactTrustIndex.create(self.index, drifted)

        dangling = FactTrustClaim.create(
            function="sha256:" + "f" * 64,
            value="pure",
        )
        with self.assertRaisesRegex(FactTrustError, "dangling"):
            FactTrustIndex.create(
                self.index,
                (*derived, dangling),
            )

    def test_proved_dependencies_must_be_exact_proved_and_acyclic(self) -> None:
        with self.assertRaisesRegex(
            FactTrustError,
            "proved direct callees",
        ):
            FactTrustIndex.create(
                self.index,
                self.claims(frozenset({"caller"})),
            )

        claims = list(
            self.claims(frozenset({"leaf", "caller"}))
        )
        caller_index = next(
            index
            for index, claim in enumerate(claims)
            if claim.function == self.functions["caller"]
        )
        claims[caller_index] = FactTrustClaim.create(
            function=self.functions["caller"],
            value="pure",
            trust="proved",
            evidence=self.evidence(
                line=2,
                obligations=("ob00002",),
                callees=(),
            ),
        )
        with self.assertRaisesRegex(
            FactTrustError,
            "every exact direct callee",
        ):
            FactTrustIndex.create(self.index, claims)

        with self.assertRaisesRegex(
            FactTrustError,
            "own claim",
        ):
            FactTrustClaim.create(
                function=self.functions["leaf"],
                value="pure",
                trust="proved",
                evidence=self.evidence(
                    line=1,
                    obligations=("ob00001",),
                    callees=(self.functions["leaf"],),
                ),
            )

    def test_mutual_proof_dependency_cycle_is_rejected(self) -> None:
        source = (
            "int second(int value);\n"
            "int first(int value) { return second(value); }\n"
            "int second(int value) { return first(value); }\n"
        )
        cycle_index = extract_facts(source, "trust/cycle.cpp")
        functions = {
            symbol.qualified_name: symbol.id
            for symbol in cycle_index.symbols
            if symbol.kind == "function"
        }
        direct = {
            function: tuple(
                sorted(
                    call.callee
                    for call in cycle_index.calls
                    if call.caller == function
                )
            )
            for function in functions.values()
        }
        claims = []
        for row in cycle_index.purity:
            claims.append(
                FactTrustClaim.create(
                    function=row.function,
                    value=row.status,
                    trust="proved",
                    evidence=ProofEvidence(
                        cycle_index.source.content_sha256,
                        verification_sha256(b"cycle report"),
                        VERIFICATION_SCHEMA,
                        "codeskeptic.affine/v1",
                        ("ob00001",),
                        FactLocation("trust/cycle.cpp", 1, 1),
                        direct[row.function],
                    ),
                )
            )
        with self.assertRaisesRegex(FactTrustError, "acyclic"):
            FactTrustIndex.create(cycle_index, claims)
    def test_json_schema_matches_runtime_constants(self) -> None:
        schema = json.loads(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            FACT_TRUST_SCHEMA,
        )
        claim = schema["$defs"]["claim"]
        self.assertEqual(
            set(claim["properties"]["trust"]["enum"]),
            TRUST_LABELS,
        )
        self.assertEqual(
            set(claim["properties"]["value"]["enum"]),
            {"impure", "pure", "unknown"},
        )
        evidence = schema["$defs"]["evidence"]
        self.assertEqual(
            evidence["properties"]["method"]["const"],
            PROOF_METHOD,
        )
        self.assertEqual(
            set(evidence["properties"]["referee"]["enum"]),
            REFEREE_IDS,
        )
        self.assertEqual(
            evidence["properties"]["verification_schema"]["const"],
            VERIFICATION_SCHEMA,
        )
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
