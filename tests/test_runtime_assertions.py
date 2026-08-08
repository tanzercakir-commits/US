from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.backend import CheckerBackend, create_backend
from semantic_verifier.frontend import discover_clang
from semantic_verifier.model import VerificationResult, VerificationStatus
from semantic_verifier.pipeline import VerificationPipeline
from semantic_verifier.runtime_assertions import build_runtime_assertions


ROOT = Path(__file__).resolve().parents[1]
PROPERTY = ROOT / "fixtures" / "enforcement_ladder" / "property"
RUNTIME = ROOT / "fixtures" / "enforcement_ladder" / "runtime"
SOURCE = PROPERTY / "square_bounded.cpp"


class StatusBackend(CheckerBackend):
    def __init__(self, status: VerificationStatus):
        self.status = status
        self.name = f"runtime-{status.value}"

    def check(self, obligation):
        return VerificationResult(
            obligation_id=obligation.id,
            function=obligation.function,
            kind=obligation.kind,
            status=self.status,
            location=obligation.location,
            message=f"injected {self.status.value}",
        )


class RuntimeAssertionsTests(unittest.TestCase):
    def source_text(self) -> str:
        return SOURCE.read_text(encoding="utf-8")

    def affine_bundle(self):
        report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_file(SOURCE)
        return build_runtime_assertions(
            self.source_text(),
            report,
            display_path=SOURCE.as_posix(),
        )

    def wrapper_name(self) -> str:
        return str(self.affine_bundle().manifest["runtime_targets"][0]["wrapper"])

    def compile_driver(self, implementation: str, main_body: str):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = root / "driver.cpp"
            driver.write_text(
                (
                    "#include <cstdlib>\n"
                    "[[noreturn]] void codeskeptic_contract_failure("
                    "const char*, const char*, const char*) { std::exit(86); }\n"
                    f"int {self.wrapper_name()}(int);\n"
                    f"{implementation}\n"
                    f"int main() {{ {main_body} }}\n"
                ),
                encoding="utf-8",
                newline="\n",
            )
            executable = root / "runtime_guard.exe"
            completed = subprocess.run(
                [
                    discover_clang(),
                    "-std=c++17",
                    str(RUNTIME / "expected.runtime.cpp"),
                    str(driver),
                    "-fuse-ld=lld",
                    f"-o{executable}",
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            ).returncode

    def test_frozen_runtime_and_demo_artifacts_match(self):
        bundle = self.affine_bundle()
        self.assertEqual(
            bundle.wrapper,
            (RUNTIME / "expected.runtime.cpp").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            bundle.manifest_json(),
            (RUNTIME / "expected.runtime.manifest.json").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            bundle.demo_manifest_json(),
            (RUNTIME / "expected.demo.manifest.json").read_text(
                encoding="utf-8"
            ),
        )

    def test_all_three_rungs_share_source_contract_and_target_identity(self):
        bundle = self.affine_bundle()
        property_target = bundle.property.manifest["property_targets"][0]
        runtime_target = bundle.manifest["runtime_targets"][0]
        demo_target = bundle.demo_manifest["contract_targets"][0]
        for key in ("contract_set_sha256", "target_id"):
            self.assertEqual(property_target[key], runtime_target[key])
            self.assertEqual(property_target[key], demo_target[key])
        self.assertEqual(
            bundle.property.manifest["source_sha256"],
            bundle.manifest["source_sha256"],
        )
        self.assertEqual(
            bundle.manifest["source_sha256"],
            bundle.demo_manifest["source_sha256"],
        )
        self.assertEqual(
            set(bundle.demo_manifest["rungs"]),
            {"static", "property", "runtime"},
        )

    def test_generated_runtime_wrapper_compiles_as_cpp17(self):
        completed = subprocess.run(
            [
                discover_clang(),
                "-x",
                "c++",
                "-std=c++17",
                "-fsyntax-only",
                str(RUNTIME / "expected.runtime.cpp"),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_satisfying_call_returns_normally(self):
        code = self.compile_driver(
            "int square_bounded(int value) { return value * value; }",
            f"return {self.wrapper_name()}(5) == 25 ? 0 : 1;",
        )
        self.assertEqual(code, 0)

    def test_failed_requirement_reaches_explicit_hook(self):
        code = self.compile_driver(
            "int square_bounded(int value) { return value * value; }",
            f"return {self.wrapper_name()}(-1);",
        )
        self.assertEqual(code, 86)

    def test_failed_postcondition_reaches_explicit_hook(self):
        code = self.compile_driver(
            "int square_bounded(int value) { return value; }",
            f"return {self.wrapper_name()}(5);",
        )
        self.assertEqual(code, 86)

    def test_wrapper_orders_checks_and_evaluates_function_once(self):
        wrapper = self.affine_bundle().wrapper
        call = "const int result = square_bounded(value);"
        self.assertEqual(wrapper.count(call), 1)
        self.assertLess(wrapper.index("if (!(value >= 0))"), wrapper.index(call))
        self.assertLess(wrapper.index("if (!(value <= 100))"), wrapper.index(call))
        self.assertGreater(
            wrapper.index("if (!(result == value * value))"),
            wrapper.index(call),
        )

    def test_runtime_routes_preserve_original_status_without_promotion(self):
        routes = self.affine_bundle().manifest["routes"]
        self.assertEqual(
            {route["original_status"] for route in routes},
            {"verified", "unsupported"},
        )
        guarded = [
            route for route in routes if route["runtime_state"] == "runtime_guarded"
        ]
        self.assertTrue(guarded)
        self.assertTrue(
            all(route["original_status"] == "unsupported" for route in guarded)
        )
        self.assertNotIn("verified", {route["runtime_state"] for route in guarded})
        self.assertTrue(
            all(route["state"] == "property_generated_unexecuted" for route in guarded)
        )

    def test_terminal_static_states_do_not_get_runtime_targets(self):
        cases = (
            (
                "// cs: ensures result == value\n"
                "int identity(int value) { return value; }\n",
                None,
            ),
            (
                "// cs: ensures result > value\n"
                "int identity(int value) { return value; }\n",
                None,
            ),
            (
                self.source_text(),
                StatusBackend(VerificationStatus.SOLVER_ERROR),
            ),
        )
        for index, (source, checker) in enumerate(cases):
            with self.subTest(index=index):
                shown = f"terminal_{index}.cpp"
                report = VerificationPipeline(checker=checker).verify_source(
                    source, shown
                )
                bundle = build_runtime_assertions(
                    source, report, display_path=shown
                )
                self.assertEqual(bundle.manifest["runtime_targets"], [])
                self.assertEqual(bundle.manifest["state"], "no_runtime_target")

    def test_relocation_preserves_all_runtime_and_demo_bytes(self):
        source = self.source_text()
        first_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(source, "a/runtime.cpp")
        second_report = VerificationPipeline(
            checker=create_backend("affine")
        ).verify_source(source, "b/runtime.cpp")
        first = build_runtime_assertions(
            source, first_report, display_path="a/runtime.cpp"
        )
        second = build_runtime_assertions(
            source, second_report, display_path="b/runtime.cpp"
        )
        self.assertEqual(first.wrapper, second.wrapper)
        self.assertEqual(first.manifest_json(), second.manifest_json())
        self.assertEqual(first.demo_manifest_json(), second.demo_manifest_json())

    def test_runtime_and_demo_clis_check_frozen_artifacts(self):
        runtime = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "generate_runtime_assertions.py"),
                str(SOURCE),
                "--backend",
                "affine",
                "--wrapper",
                str(RUNTIME / "expected.runtime.cpp"),
                "--manifest",
                str(RUNTIME / "expected.runtime.manifest.json"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(runtime.returncode, 0, runtime.stderr)
        self.assertIn("artifacts match", runtime.stdout)

        demo = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "enforcement_ladder_demo.py"),
                str(SOURCE),
                "--backend",
                "affine",
                "--property-skeleton",
                str(PROPERTY / "expected.property.cpp"),
                "--property-manifest",
                str(PROPERTY / "expected.manifest.json"),
                "--runtime-wrapper",
                str(RUNTIME / "expected.runtime.cpp"),
                "--runtime-manifest",
                str(RUNTIME / "expected.runtime.manifest.json"),
                "--demo-manifest",
                str(RUNTIME / "expected.demo.manifest.json"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(demo.returncode, 0, demo.stderr)
        self.assertIn("three-rung", demo.stdout)


if __name__ == "__main__":
    unittest.main()