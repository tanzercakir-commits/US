from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from semantic_verifier import verify_source
from semantic_verifier.frontend import (
    FrontendError,
    _PROFILE_VALIDATION,
    validate_integer_target_profile,
)
from semantic_verifier.integer_types import (
    FIXED_INTEGER_TYPES,
    I32,
    I64,
    TARGET_PROFILE,
    TARGET_PROFILE_ID,
    U32,
    U64,
    canonical_decimal,
    parse_canonical_decimal,
)
from semantic_verifier.model import (
    Expr,
    SCHEMA,
    SourceLocation,
    VerificationResult,
    VerificationStatus,
)
from semantic_verifier.schema import SchemaCompatibilityError, require_current_schema
from semantic_verifier.pipeline import VerificationPipeline


ROOT = Path(__file__).resolve().parents[1]


class IntegerTypeTests(unittest.TestCase):
    def test_owned_type_ranges_and_profile_are_exact(self):
        self.assertEqual(
            {
                name: (item.signed, item.width, item.minimum, item.maximum)
                for name, item in FIXED_INTEGER_TYPES.items()
            },
            {
                "i32": (True, 32, -(2**31), 2**31 - 1),
                "u32": (False, 32, 0, 2**32 - 1),
                "i64": (True, 64, -(2**63), 2**63 - 1),
                "u64": (False, 64, 0, 2**64 - 1),
            },
        )
        self.assertEqual(TARGET_PROFILE.id, TARGET_PROFILE_ID)
        self.assertEqual(TARGET_PROFILE.types, (I32, U32, I64, U64))
        with self.assertRaises(FrozenInstanceError):
            I32.width = 64

    def test_canonical_decimal_is_strict(self):
        for value in (0, -1, 2**64 - 1):
            encoded = canonical_decimal(value)
            self.assertEqual(parse_canonical_decimal(encoded), value)
        with self.assertRaises(TypeError):
            canonical_decimal(True)
        for invalid in (1, "+1", "01", "-0", " 1"):
            with self.assertRaises(ValueError):
                parse_canonical_decimal(invalid)

    def test_v2_serializes_fixed_integers_as_decimal_strings(self):
        for type_name, value in (
            ("i32", -1),
            ("u32", 2**32 - 1),
            ("i64", -(2**63)),
            ("u64", 2**64 - 1),
        ):
            self.assertEqual(
                Expr.integer(value, type_name).to_dict(),
                {"kind": "constant", "type": type_name, "value": str(value)},
            )
        self.assertIs(Expr.boolean(True).to_dict()["value"], True)
        with self.assertRaises(TypeError):
            Expr("constant", "i32", value=True).to_dict()

    def test_counterexample_integers_are_strings_but_booleans_are_not(self):
        result = VerificationResult(
            obligation_id="o1",
            function="f",
            kind="assertion",
            status=VerificationStatus.VIOLATED,
            location=SourceLocation("x.cpp", 1, 1),
            message="violated",
            counterexample={"x": -1, "ready": False},
        ).to_dict()

        self.assertEqual(result["counterexample"], {"ready": False, "x": "-1"})

    def test_existing_cpp_int_lowers_to_i32_without_accepting_new_types(self):
        report = verify_source(
            "int identity(int x) { int y = x; return y; }\n", "types.cpp"
        )
        function = report.module.functions[0]
        self.assertEqual(function.return_type, "i32")
        self.assertEqual(function.parameters[0].type, "i32")
        self.assertEqual(function.locals[0].type, "i32")
        self.assertEqual(report.summary()["unsupported"], 0)

        for source in (
            "unsigned int f(unsigned int x) { return x; }\n",
            "long long f(long long x) { return x; }\n",
        ):
            rejected = verify_source(source, "future-type.cpp")
            self.assertGreater(rejected.summary()["unsupported"], 0)

    def test_target_profile_mismatch_becomes_frontend_solver_error(self):
        message = f"target mismatch: {TARGET_PROFILE_ID}"
        with patch(
            "semantic_verifier.frontend.discover_clang", return_value="fake-clang"
        ), patch(
            "semantic_verifier.frontend.validate_integer_target_profile",
            side_effect=FrontendError(message),
        ):
            report = VerificationPipeline().verify_source(
                "int f() { return 0; }\n", "profile.cpp"
            )

        self.assertEqual(report.summary()["solver_error"], 1)
        self.assertEqual(report.results[0].kind, "frontend_initialization")
        self.assertIn(message, report.results[0].message)


    def test_target_profile_validation_is_cached(self):
        clang = str(ROOT / "fake-profile-clang")
        key = os.path.normcase(os.path.abspath(clang))
        _PROFILE_VALIDATION.pop(key, None)
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch("semantic_verifier.frontend.subprocess.run", return_value=completed) as run:
            validate_integer_target_profile(clang)
            validate_integer_target_profile(clang)
        self.assertEqual(run.call_count, 1)
        self.assertIn("static_assert", run.call_args.kwargs["input"])
        _PROFILE_VALIDATION.pop(key, None)

    def test_target_profile_mismatch_fails_closed_and_is_cached(self):
        clang = str(ROOT / "fake-mismatched-clang")
        key = os.path.normcase(os.path.abspath(clang))
        _PROFILE_VALIDATION.pop(key, None)
        completed = subprocess.CompletedProcess([], 1, "", "mismatch")
        with patch("semantic_verifier.frontend.subprocess.run", return_value=completed) as run:
            for _ in range(2):
                with self.assertRaisesRegex(FrontendError, TARGET_PROFILE_ID):
                    validate_integer_target_profile(clang)
        self.assertEqual(run.call_count, 1)
        _PROFILE_VALIDATION.pop(key, None)


class V2MigrationTests(unittest.TestCase):
    def test_v1_and_mixed_payloads_are_rejected(self):
        with self.assertRaisesRegex(SchemaCompatibilityError, "unsupported"):
            require_current_schema({"schema": "codeskeptic.semantic-verification/v1"})
        with self.assertRaisesRegex(SchemaCompatibilityError, "mixed"):
            require_current_schema(
                {
                    "schema": SCHEMA,
                    "semantic_ir": {
                        "schema": "codeskeptic.semantic-verification/v1"
                    },
                }
            )

    def test_archived_v1_hash_manifest_is_exact(self):
        archive = ROOT / "fixtures" / "versions" / "v1"
        for line in (archive / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            expected, relative = line.split("  ", 1)
            self.assertEqual(
                hashlib.sha256((archive / relative).read_bytes()).hexdigest(),
                expected,
                relative,
            )

    def test_v1_to_v2_preserves_result_statuses(self):
        archive = ROOT / "fixtures" / "versions" / "v1" / "expected"
        current = ROOT / "fixtures" / "expected"
        for old_path in sorted(archive.glob("*.report.json")):
            old = json.loads(old_path.read_text(encoding="utf-8"))
            new = json.loads((current / old_path.name).read_text(encoding="utf-8"))
            self.assertEqual(new["schema"], SCHEMA)
            self.assertEqual(new["summary"], old["summary"])
            fields = ("obligation", "function", "kind", "status")
            self.assertEqual(
                [tuple(item[field] for field in fields) for item in new["results"]],
                [tuple(item[field] for field in fields) for item in old["results"]],
            )


if __name__ == "__main__":
    unittest.main()
