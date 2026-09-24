import unittest

from report_builder.results import EmptyReport, ReadFailure
from report_builder.service import ReportService
from report_builder.ui import UI


class StubReader:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.queries = []

    def read(self, query):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.rows


class RecordingRenderer:
    def __init__(self):
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return {"rendered": rows}


class MutatingRenderer:
    def render(self, rows):
        rows[0]["nested"]["value"] = "changed"
        rows[0]["added"] = True
        return "ok"


class SequenceReader:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.queries = []

    def read(self, query):
        self.queries.append(query)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, OSError):
            raise outcome
        return outcome


class ReportServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct_and_renderer_is_not_called(self):
        error = OSError("cannot read")
        reader = StubReader(error=error)
        renderer = RecordingRenderer()

        result = ReportService(reader, renderer).build_report("query")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_success_returns_empty_report_without_rendering(self):
        reader = StubReader(rows=[])
        renderer = RecordingRenderer()

        result = ReportService(reader, renderer).build_report("query")

        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_success_returns_renderer_output(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = RecordingRenderer()

        result = ReportService(reader, renderer).build_report("query")

        self.assertEqual(result, {"rendered": [{"name": "Ada"}]})
        self.assertEqual(reader.queries, ["query"])

    def test_explicit_default_preserves_renderer_output(self):
        rows = [{"name": "Ada"}]
        renderer = RecordingRenderer()

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "query", output_format="default"
        )

        self.assertEqual(result, {"rendered": [{"name": "Ada"}]})
        self.assertEqual(renderer.calls, [[{"name": "Ada"}]])

    def test_csv_uses_sorted_union_of_columns_and_standard_quoting(self):
        rows = [
            {"b": "x,y", "a": 1},
            {"c": 'say "hi"', "b": 2},
        ]
        renderer = RecordingRenderer()

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "query", output_format="csv"
        )

        self.assertEqual(result, 'a,b,c\n1,"x,y",\n,2,"say ""hi"""\n')
        self.assertEqual(renderer.calls, [])

    def test_csv_preserves_read_failure_and_empty_report_outcomes(self):
        error = OSError("cannot read")
        failed = ReportService(StubReader(error=error), RecordingRenderer()).build_report(
            "query", output_format="csv"
        )
        empty = ReportService(StubReader(rows=[]), RecordingRenderer()).build_report(
            "query", output_format="csv"
        )

        self.assertIsInstance(failed, ReadFailure)
        self.assertIs(failed.error, error)
        self.assertIsInstance(empty, EmptyReport)

    def test_csv_does_not_mutate_source_records(self):
        rows = [{"b": [1, 2], "a": "value"}]

        result = ReportService(StubReader(rows=rows), RecordingRenderer()).build_report(
            "query", output_format="csv"
        )

        self.assertEqual(result, 'a,b\nvalue,"[1, 2]"\n')
        self.assertEqual(rows, [{"b": [1, 2], "a": "value"}])

    def test_renderer_cannot_mutate_source_records(self):
        rows = [{"nested": {"value": "original"}}]

        result = ReportService(StubReader(rows=rows), MutatingRenderer()).build_report("q")

        self.assertEqual(result, "ok")
        self.assertEqual(rows, [{"nested": {"value": "original"}}])

    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "report"

        service = Service()
        result = UI(service).build_report("query")

        self.assertEqual(result, "report")
        self.assertEqual(service.queries, ["query"])

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaisesRegex(ValueError, "eviction policy is unresolved"):
            ReportService(StubReader(rows=[{"a": 1}]), RecordingRenderer(), cache_enabled=True)

    def test_cache_reuses_successful_non_empty_result(self):
        reader = StubReader(rows=[{"name": "Ada"}])
        renderer = RecordingRenderer()
        policy_calls = []

        def keep_all(cache_snapshot, new_key):
            policy_calls.append((cache_snapshot, new_key))
            return []

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=keep_all
        )
        first = service.build_report(("same", 1))
        second = service.build_report(("same", 1))

        self.assertIs(first, second)
        self.assertEqual(reader.queries, [("same", 1)])
        self.assertEqual(len(renderer.calls), 1)
        self.assertEqual(len(policy_calls), 1)
        snapshot, new_key = policy_calls[0]
        self.assertEqual(new_key, (("same", 1), "default"))
        self.assertEqual(list(snapshot), [new_key])

    def test_eviction_policy_can_remove_existing_keys(self):
        reader = StubReader(rows=[{"value": 1}])
        renderer = RecordingRenderer()

        def keep_only_newest(cache_snapshot, new_key):
            return [key for key in cache_snapshot if key != new_key]

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=keep_only_newest
        )
        service.build_report("q1")
        service.build_report("q2")
        service.build_report("q1")

        self.assertEqual(reader.queries, ["q1", "q2", "q1"])
        self.assertEqual(len(renderer.calls), 3)

    def test_cache_does_not_store_empty_or_read_failure(self):
        reader = SequenceReader(
            [
                OSError("temporary"),
                [{"value": 1}],
                [],
                [{"value": 2}],
            ]
        )
        renderer = RecordingRenderer()
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda cache, key: []
        )

        first = service.build_report("failure")
        second = service.build_report("failure")
        third = service.build_report("empty")
        fourth = service.build_report("empty")

        self.assertIsInstance(first, ReadFailure)
        self.assertEqual(second, {"rendered": [{"value": 1}]})
        self.assertIsInstance(third, EmptyReport)
        self.assertEqual(fourth, {"rendered": [{"value": 2}]})
        self.assertEqual(reader.queries, ["failure", "failure", "empty", "empty"])

    def test_cache_keeps_default_and_csv_results_separate(self):
        reader = StubReader(rows=[{"b": 2, "a": 1}])
        renderer = RecordingRenderer()
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda cache, key: []
        )

        rendered = service.build_report("query")
        csv_result = service.build_report("query", output_format="csv")
        rendered_again = service.build_report("query")
        csv_again = service.build_report("query", output_format="csv")

        self.assertEqual(rendered, {"rendered": [{"b": 2, "a": 1}]})
        self.assertEqual(csv_result, "a,b\n1,2\n")
        self.assertIs(rendered, rendered_again)
        self.assertIs(csv_result, csv_again)
        self.assertEqual(reader.queries, ["query", "query"])
        self.assertEqual(len(renderer.calls), 1)

    def test_unhashable_query_bypasses_cache(self):
        reader = StubReader(rows=[{"value": 1}])
        renderer = RecordingRenderer()
        policy_calls = []
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda cache, key: policy_calls.append(key) or [],
        )
        query = ["unhashable"]

        first = service.build_report(query)
        second = service.build_report(query)

        self.assertEqual(first, second)
        self.assertEqual(reader.queries, [query, query])
        self.assertEqual(len(renderer.calls), 2)
        self.assertEqual(policy_calls, [])


if __name__ == "__main__":
    unittest.main()
