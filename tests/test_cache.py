import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from semantic_verifier.backend import CheckerBackend
from semantic_verifier.cache import (
    CACHE_SCHEMA,
    CachedCheckerBackend,
    obligation_semantic_key,
)
from semantic_verifier.cli import build_parser
from semantic_verifier.model import (
    Expr,
    Obligation,
    SourceLocation,
    TraceStep,
    TraceTemplate,
    VerificationResult,
    VerificationStatus,
)
from semantic_verifier.pipeline import VerificationPipeline


LOCATION = SourceLocation("cache.cpp", 4, 2)


def obligation(
    identifier="ob00001",
    *,
    conclusion=None,
    location=LOCATION,
    trace_templates=(),
):
    return Obligation(
        id=identifier,
        function="cached",
        kind="assertion",
        assumptions=(
            Expr.binary(
                ">=", Expr.variable("x", "int"), Expr.integer(0), "bool"
            ),
        ),
        conclusion=conclusion
        or Expr.binary(
            ">=", Expr.variable("x", "int"), Expr.integer(0), "bool"
        ),
        location=location,
        description="cache test",
        trace_templates=trace_templates,
    )


class CountingBackend(CheckerBackend):
    name = "counting"

    def __init__(self, *, configuration="v0", status=VerificationStatus.VERIFIED):
        self.configuration = configuration
        self.status = status
        self.calls = 0

    def cache_identity(self):
        return {"configuration": self.configuration, "name": self.name}

    def check(self, item):
        self.calls += 1
        return VerificationResult(
            obligation_id=item.id,
            function=item.function,
            kind=item.kind,
            status=self.status,
            location=item.location,
            message=f"{self.status.value}: counted",
        )


class PersistentCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "results.json"

    def cached(self, backend):
        return CachedCheckerBackend(backend, self.path)

    def test_identical_runs_are_byte_identical_and_second_makes_zero_calls(self):
        source = """\
void assert(bool);
int cached_run(int x) {
    assert(x >= 0);
    return x;
}
"""
        first_backend = CountingBackend()
        first = VerificationPipeline(
            checker=first_backend,
            cache_path=self.path,
        ).verify_source(source, "stable/cache.cpp")
        first_cache_bytes = self.path.read_bytes()

        second_backend = CountingBackend()
        second = VerificationPipeline(
            checker=second_backend,
            cache_path=self.path,
        ).verify_source(source, "stable/cache.cpp")

        self.assertEqual(first_backend.calls, 1)
        self.assertEqual(second_backend.calls, 0)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first_cache_bytes, self.path.read_bytes())
        self.assertEqual(json.loads(first_cache_bytes)["schema"], CACHE_SCHEMA)

    def test_changing_one_obligation_invalidates_only_that_entry(self):
        original_second = obligation(
            "ob2",
            conclusion=Expr.binary(
                ">=", Expr.variable("x", "int"), Expr.integer(1), "bool"
            ),
        )
        self.cached(CountingBackend()).check_all(
            (obligation("ob1"), original_second)
        )
        changed = obligation(
            "ob2-new",
            conclusion=Expr.binary(
                ">", Expr.variable("x", "int"), Expr.integer(1), "bool"
            ),
        )
        backend = CountingBackend()

        self.cached(backend).check_all((obligation("current-id"), changed))

        self.assertEqual(backend.calls, 1)

    def test_schema_backend_and_configuration_changes_miss(self):
        item = obligation()
        baseline = CountingBackend()
        self.cached(baseline).check(item)
        baseline_key = obligation_semantic_key(item, baseline)

        configured = CountingBackend(configuration="v1")
        self.cached(configured).check(item)
        renamed = CountingBackend()
        renamed.name = "other-counting"
        self.cached(renamed).check(item)

        self.assertNotEqual(baseline_key, obligation_semantic_key(item, configured))
        self.assertEqual(configured.calls, 1)
        self.assertEqual(renamed.calls, 1)

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["schema"] = "codeskeptic.obligation-result-cache/v99"
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        stale = CountingBackend()
        self.cached(stale).check(item)
        self.assertEqual(stale.calls, 1)

        with patch(
            "semantic_verifier.cache.SCHEMA",
            "codeskeptic.semantic-verification/v99",
        ):
            new_schema = CountingBackend()
            self.cached(new_schema).check(item)
        self.assertEqual(new_schema.calls, 1)

    def test_malformed_file_and_entry_recompute_safely(self):
        self.path.write_bytes(b"{not-json")
        backend = CountingBackend()
        self.cached(backend).check(obligation())
        self.assertEqual(backend.calls, 1)

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        entry = next(iter(payload["entries"].values()))
        entry["result"]["status"] = "invented-proof"
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        malformed = CountingBackend()
        self.cached(malformed).check(obligation())
        self.assertEqual(malformed.calls, 1)

    def test_hit_reconstructs_current_result_and_trace_metadata(self):
        condition = Expr.variable("branch", "bool")
        old_location = SourceLocation("old.cpp", 2, 3)
        old_template = TraceTemplate("branch", condition, (), old_location)
        item = obligation(location=old_location, trace_templates=(old_template,))

        class TraceBackend(CountingBackend):
            def check(self, checked):
                self.calls += 1
                return VerificationResult(
                    obligation_id=checked.id,
                    function=checked.function,
                    kind=checked.kind,
                    status=VerificationStatus.VIOLATED,
                    location=checked.location,
                    message="violated: traced",
                    counterexample={"x": -1},
                    trace=(TraceStep("branch", condition, False, old_location),),
                )

        self.cached(TraceBackend()).check(item)
        new_location = SourceLocation("new.cpp", 20, 7)
        current = obligation(
            "current-id",
            location=new_location,
            trace_templates=(TraceTemplate("branch", condition, (), new_location),),
        )
        backend = TraceBackend()

        result = self.cached(backend).check(current)

        self.assertEqual(backend.calls, 0)
        self.assertEqual(result.obligation_id, "current-id")
        self.assertEqual(result.location, new_location)
        self.assertEqual(result.trace[0].location, new_location)

    def test_solver_errors_are_never_persisted_as_reusable_results(self):
        first = CountingBackend(status=VerificationStatus.SOLVER_ERROR)
        second = CountingBackend(status=VerificationStatus.SOLVER_ERROR)
        self.cached(first).check(obligation())
        self.cached(second).check(obligation())
        self.assertEqual((first.calls, second.calls), (1, 1))

    def test_pipeline_and_cli_accept_cache_configuration(self):
        backend = CountingBackend()
        pipeline = VerificationPipeline(checker=backend, cache_path=self.path)
        arguments = build_parser().parse_args(
            ["input.cpp", "--cache", str(self.path)]
        )

        self.assertIsInstance(pipeline.checker, CachedCheckerBackend)
        self.assertEqual(arguments.cache, str(self.path))


if __name__ == "__main__":
    unittest.main()
