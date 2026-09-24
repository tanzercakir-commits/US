import unittest

from report_builder.results import EmptyReport, ReadFailure
from report_builder.service import ReportService
from report_builder.ui import UI


class Reader:
    def __init__(self, rows=None, error=None):
        self.rows = [] if rows is None else rows
        self.error = error
        self.queries = []

    def read(self, query):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.rows


class Renderer:
    def __init__(self):
        self.rows = None
        self.calls = 0

    def render(self, rows):
        self.calls += 1
        self.rows = rows
        for row in rows:
            row["rendered"] = True
        return "report"


class ServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct(self):
        renderer = Renderer()
        result = ReportService(Reader(error=OSError("boom")), renderer).build_report("q")
        self.assertIsInstance(result, ReadFailure)
        self.assertEqual(str(result.error), "boom")
        self.assertIsNone(renderer.rows)

    def test_empty_report_is_distinct(self):
        renderer = Renderer()
        result = ReportService(Reader(rows=[]), renderer).build_report("q")
        self.assertIsInstance(result, EmptyReport)
        self.assertIsNone(renderer.rows)

    def test_non_empty_rows_are_rendered_without_mutating_source(self):
        source_rows = [{"id": 1}, {"id": 2}]
        renderer = Renderer()
        result = ReportService(Reader(rows=source_rows), renderer).build_report("q")
        self.assertEqual(result, "report")
        self.assertEqual(source_rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(renderer.rows[0]["rendered"], True)

    def test_csv_uses_sorted_union_of_columns_without_mutating_source(self):
        source_rows = [
            {"name": "Ada", "id": 2},
            {"note": "a,b", "id": 1},
        ]
        renderer = Renderer()

        result = ReportService(Reader(rows=source_rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'id,name,note\n2,Ada,\n1,,"a,b"\n',
        )
        self.assertEqual(
            source_rows,
            [
                {"name": "Ada", "id": 2},
                {"note": "a,b", "id": 1},
            ],
        )
        self.assertIsNone(renderer.rows)

    def test_csv_preserves_read_failure_and_empty_report_outcomes(self):
        renderer = Renderer()
        failed = ReportService(Reader(error=OSError("boom")), renderer).build_report(
            "q", output_format="csv"
        )
        empty = ReportService(Reader(rows=[]), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertIsInstance(failed, ReadFailure)
        self.assertIsInstance(empty, EmptyReport)
        self.assertIsNone(renderer.rows)

    def test_cache_disabled_preserves_repeated_read_and_render(self):
        reader = Reader(rows=[{"id": 1}])
        renderer = Renderer()
        service = ReportService(reader, renderer)

        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q"), "report")

        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, 2)

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(Reader(rows=[{"id": 1}]), Renderer(), cache_enabled=True)

    def test_cache_enabled_reuses_successful_non_empty_result(self):
        reader = Reader(rows=[{"id": 1}])
        renderer = Renderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertEqual(first, "report")
        self.assertEqual(second, "report")
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(renderer.calls, 1)

    def test_cache_key_keeps_output_formats_distinct(self):
        reader = Reader(rows=[{"id": 1}])
        renderer = Renderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )

        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q", output_format="csv"), "id\n1\n")
        self.assertEqual(service.build_report("q"), "report")
        self.assertEqual(service.build_report("q", output_format="csv"), "id\n1\n")
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, 1)

    def test_failures_and_empty_reports_are_not_cached(self):
        failed_reader = Reader(error=OSError("boom"))
        failed_service = ReportService(
            failed_reader,
            Renderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )
        self.assertIsInstance(failed_service.build_report("q"), ReadFailure)
        self.assertIsInstance(failed_service.build_report("q"), ReadFailure)
        self.assertEqual(failed_reader.queries, ["q", "q"])

        empty_reader = Reader(rows=[])
        empty_service = ReportService(
            empty_reader,
            Renderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertEqual(empty_reader.queries, ["q", "q"])

    def test_eviction_policy_receives_snapshot_and_can_remove_keys(self):
        seen = []

        def evict_previous(snapshot, new_key):
            seen.append((snapshot, new_key))
            return [key for key in snapshot if key != new_key]

        reader = Reader(rows=[{"id": 1}])
        renderer = Renderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=evict_previous,
        )

        service.build_report("a")
        service.build_report("b")
        service.build_report("a")

        self.assertEqual(reader.queries, ["a", "b", "a"])
        self.assertEqual(renderer.calls, 3)
        self.assertEqual(seen[0][1], ("a", "default"))
        with self.assertRaises(TypeError):
            seen[0][0][("x", "default")] = "report"

    def test_unhashable_query_bypasses_cache_without_changing_behavior(self):
        query = ["q"]
        reader = Reader(rows=[{"id": 1}])
        renderer = Renderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )

        self.assertEqual(service.build_report(query), "report")
        self.assertEqual(service.build_report(query), "report")
        self.assertEqual(reader.queries, [query, query])
        self.assertEqual(renderer.calls, 2)

    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.query = None

            def build_report(self, query):
                self.query = query
                return "ok"

        service = Service()
        self.assertEqual(UI(service).build_report("q"), "ok")
        self.assertEqual(service.query, "q")


if __name__ == "__main__":
    unittest.main()
