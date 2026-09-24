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
    def __init__(self, result="rendered"):
        self.result = result
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return self.result


class ReportServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct_and_does_not_render(self):
        error = OSError("read failed")
        renderer = StubRenderer()
        result = ReportService(StubReader(error=error), renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_read_returns_empty_report_without_rendering(self):
        renderer = StubRenderer()
        result = ReportService(StubReader(rows=[]), renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertNotIsInstance(result, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_rows_are_rendered_without_source_mutation(self):
        rows = [{"name": "Ada"}, {"name": "Grace"}]
        before = [dict(row) for row in rows]
        renderer = StubRenderer(result={"report": 2})

        result = ReportService(StubReader(rows=rows), renderer).build_report("q")

        self.assertEqual(result, {"report": 2})
        self.assertIs(renderer.calls[0], rows)
        self.assertEqual(rows, before)

    def test_explicit_default_preserves_renderer_behavior(self):
        rows = [{"name": "Ada"}]
        renderer = StubRenderer(result="default report")

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="default"
        )

        self.assertEqual(result, "default report")
        self.assertIs(renderer.calls[0], rows)

    def test_csv_uses_sorted_union_of_columns_and_does_not_render(self):
        rows = [{"name": "Ada", "age": 36}, {"city": "Arlington", "name": "Grace"}]
        before = [dict(row) for row in rows]
        renderer = StubRenderer()

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            "age,city,name\n36,,Ada\n,Arlington,Grace\n",
        )
        self.assertEqual(renderer.calls, [])
        self.assertEqual(rows, before)

    def test_csv_uses_standard_library_quoting_and_lf_line_endings(self):
        rows = [{"note": 'a,"b"', "name": "Ada"}]
        result = ReportService(StubReader(rows=rows), StubRenderer()).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(result, 'name,note\nAda,"a,""b"""\n')
        self.assertTrue(result.endswith("\n"))
        self.assertNotIn("\r\n", result)

    def test_csv_empty_read_stays_empty_report(self):
        renderer = StubRenderer()
        result = ReportService(StubReader(rows=[]), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_unsupported_output_format_raises_value_error_after_successful_read(self):
        service = ReportService(StubReader(rows=[{"name": "Ada"}]), StubRenderer())

        with self.assertRaises(ValueError):
            service.build_report("q", output_format="json")

    def test_cache_disabled_preserves_repeated_read_and_render_behavior(self):
        reader = StubReader(rows=[{"name": "Ada"}])
        renderer = StubRenderer(result="report")
        service = ReportService(reader, renderer)

        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 2)

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(StubReader(rows=[]), StubRenderer(), cache_enabled=True)

    def test_cache_reuses_successful_non_empty_result_for_same_query_and_format(self):
        reader = StubReader(rows=[{"name": "Ada"}])
        renderer = StubRenderer(result="report")
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )

        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(len(renderer.calls), 1)

        csv_result = service.build_report("q", output_format="csv")
        self.assertEqual(csv_result, "name\nAda\n")
        self.assertEqual(reader.queries, ["q", "q"])

    def test_empty_and_failed_reads_are_not_cached(self):
        empty_reader = StubReader(rows=[])
        empty_service = ReportService(
            empty_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertEqual(empty_reader.queries, ["q", "q"])

        failed_reader = StubReader(error=OSError("read failed"))
        failed_service = ReportService(
            failed_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )
        self.assertIsInstance(failed_service.build_report("q"), ReadFailure)
        self.assertIsInstance(failed_service.build_report("q"), ReadFailure)
        self.assertEqual(failed_reader.queries, ["q", "q"])

    def test_eviction_policy_receives_snapshot_and_can_evict_returned_keys(self):
        reader = StubReader(rows=[{"name": "Ada"}])
        renderer = StubRenderer(result="report")
        calls = []

        def evict_previous(snapshot, new_key):
            calls.append((snapshot, new_key))
            return [key for key in snapshot if key != new_key]

        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=evict_previous,
        )
        service.build_report("first")
        service.build_report("second")
        service.build_report("first")

        self.assertEqual(reader.queries, ["first", "second", "first"])
        self.assertEqual(calls[0][1], ("first", "default"))
        self.assertEqual(calls[1][1], ("second", "default"))
        self.assertIn(("first", "default"), calls[1][0])

    def test_ui_delegates_to_service(self):
        class StubService:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "result"

        service = StubService()
        self.assertEqual(UI(service).build_report("query"), "result")
        self.assertEqual(service.queries, ["query"])


if __name__ == "__main__":
    unittest.main()
