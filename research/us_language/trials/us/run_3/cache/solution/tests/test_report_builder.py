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


class StubRenderer:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return self.result


class ReportServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct_and_renderer_is_not_called(self):
        error = OSError("unreadable")
        reader = StubReader(error=error)
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_zero_rows_returns_empty_report(self):
        reader = StubReader(rows=[])
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_rows_are_rendered_without_service_mutation(self):
        rows = [{"name": "Ada"}, {"name": "Linus"}]
        original = [dict(row) for row in rows]
        renderer = StubRenderer(result={"report": 2})

        result = ReportService(StubReader(rows=rows), renderer).build_report("q")

        self.assertEqual(result, {"report": 2})
        self.assertEqual(renderer.calls, [rows])
        self.assertEqual(rows, original)

    def test_csv_uses_sorted_union_of_columns_and_standard_quoting(self):
        rows = [
            {"b": "two", "a": "1,2"},
            {"c": "x", "a": 'quote"'},
        ]
        original = [dict(row) for row in rows]
        renderer = StubRenderer(result="default")

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(result, 'a,b,c\n"1,2",two,\n"quote""",,x\n')
        self.assertEqual(renderer.calls, [])
        self.assertEqual(rows, original)

    def test_csv_preserves_empty_and_read_failure_outcomes(self):
        empty_renderer = StubRenderer()
        empty = ReportService(StubReader(rows=[]), empty_renderer).build_report(
            "q", output_format="csv"
        )

        error = OSError("unreadable")
        failure_renderer = StubRenderer()
        failure = ReportService(
            StubReader(error=error), failure_renderer
        ).build_report("q", output_format="csv")

        self.assertIsInstance(empty, EmptyReport)
        self.assertEqual(empty_renderer.calls, [])
        self.assertIsInstance(failure, ReadFailure)
        self.assertIs(failure.error, error)
        self.assertEqual(failure_renderer.calls, [])

    def test_ui_delegates_to_service(self):
        class StubService:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "report"

        service = StubService()

        result = UI(service).build_report("q")

        self.assertEqual(result, "report")
        self.assertEqual(service.queries, ["q"])

    def test_cache_disabled_preserves_repeat_behavior(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result="report")
        service = ReportService(reader, renderer)

        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, [rows, rows])

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(StubReader(rows=[]), StubRenderer(), cache_enabled=True)

    def test_cache_reuses_successful_non_empty_result(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result={"report": 1})
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda cache, key: ()
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(second, first)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(renderer.calls, [rows])

    def test_cache_keeps_output_formats_distinct(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result="default-report")
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda cache, key: ()
        )

        default = service.build_report("q")
        csv = service.build_report("q", output_format="csv")
        default_again = service.build_report("q")
        csv_again = service.build_report("q", output_format="csv")

        self.assertEqual(default, "default-report")
        self.assertEqual(csv, "name\nAda\n")
        self.assertIs(default_again, default)
        self.assertIs(csv_again, csv)
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, [rows])

    def test_empty_and_read_failure_results_are_not_cached(self):
        empty_reader = StubReader(rows=[])
        empty_service = ReportService(
            empty_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda cache, key: (),
        )
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertEqual(empty_reader.queries, ["q", "q"])

        error = OSError("unreadable")
        failure_reader = StubReader(error=error)
        failure_service = ReportService(
            failure_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda cache, key: (),
        )
        self.assertIsInstance(failure_service.build_report("q"), ReadFailure)
        self.assertIsInstance(failure_service.build_report("q"), ReadFailure)
        self.assertEqual(failure_reader.queries, ["q", "q"])

    def test_eviction_policy_receives_copy_and_can_evict(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result="report")
        snapshots = []

        def evict(cache_snapshot, new_key):
            snapshots.append((cache_snapshot, new_key))
            if new_key == ("second", "default"):
                return [("first", "default")]
            return ()

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=evict
        )
        service.build_report("first")
        self.assertIn(("first", "default"), snapshots[0][0])
        snapshots[0][0].clear()
        service.build_report("first")
        service.build_report("second")
        service.build_report("first")

        self.assertEqual(reader.queries, ["first", "second", "first"])
        self.assertEqual(snapshots[0][1], ("first", "default"))


if __name__ == "__main__":
    unittest.main()
