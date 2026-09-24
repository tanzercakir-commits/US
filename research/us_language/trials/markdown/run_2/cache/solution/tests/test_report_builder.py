from __future__ import annotations

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
    def __init__(self):
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return {"rendered": rows}


class MutatingRenderer:
    def render(self, rows):
        rows[0]["nested"]["value"] = 99
        return "ok"


class StubService:
    def __init__(self):
        self.queries = []

    def build_report(self, query):
        self.queries.append(query)
        return "delegated"


class ReportBuilderTests(unittest.TestCase):
    def test_read_failure_is_distinct(self):
        error = OSError("read failed")
        renderer = StubRenderer()
        result = ReportService(StubReader(error=error), renderer).build_report("q")
        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_report_is_distinct(self):
        renderer = StubRenderer()
        result = ReportService(StubReader(rows=[]), renderer).build_report("q")
        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_rows_are_rendered(self):
        rows = [{"value": 1}]
        renderer = StubRenderer()
        result = ReportService(StubReader(rows=rows), renderer).build_report("q")
        self.assertEqual(result, {"rendered": rows})
        self.assertEqual(renderer.calls[0], rows)

    def test_renderer_cannot_mutate_source_rows(self):
        rows = [{"nested": {"value": 1}}]
        result = ReportService(StubReader(rows=rows), MutatingRenderer()).build_report("q")
        self.assertEqual(result, "ok")
        self.assertEqual(rows, [{"nested": {"value": 1}}])

    def test_ui_delegates_to_service(self):
        service = StubService()
        self.assertEqual(UI(service).build_report("q"), "delegated")
        self.assertEqual(service.queries, ["q"])

    def test_csv_uses_sorted_union_of_columns_and_final_newline(self):
        rows = [
            {"b": "two", "a": "one"},
            {"c": "three", "a": "four"},
        ]
        renderer = StubRenderer()
        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )
        self.assertEqual(result, "a,b,c\none,two,\nfour,,three\n")
        self.assertEqual(renderer.calls, [])
        self.assertEqual(
            rows,
            [
                {"b": "two", "a": "one"},
                {"c": "three", "a": "four"},
            ],
        )

    def test_csv_uses_standard_library_quoting(self):
        rows = [{"text": 'a,b "quoted"'}]
        result = ReportService(StubReader(rows=rows), StubRenderer()).build_report(
            "q", output_format="csv"
        )
        self.assertEqual(result, 'text\n"a,b ""quoted"""\n')

    def test_csv_preserves_non_success_outcomes(self):
        error = OSError("read failed")
        failed = ReportService(StubReader(error=error), StubRenderer()).build_report(
            "q", output_format="csv"
        )
        empty = ReportService(StubReader(rows=[]), StubRenderer()).build_report(
            "q", output_format="csv"
        )
        self.assertIsInstance(failed, ReadFailure)
        self.assertIs(failed.error, error)
        self.assertIsInstance(empty, EmptyReport)

    def test_output_format_is_keyword_only(self):
        service = ReportService(StubReader(rows=[{"a": 1}]), StubRenderer())
        with self.assertRaises(TypeError):
            service.build_report("q", "csv")

    def test_cache_options_are_keyword_only(self):
        with self.assertRaises(TypeError):
            ReportService(StubReader(rows=[]), StubRenderer(), True, lambda *_: ())

    def test_disabled_cache_preserves_repeated_read_and_render_behavior(self):
        reader = StubReader(rows=[{"value": 1}])
        renderer = StubRenderer()
        service = ReportService(reader, renderer)

        service.build_report("q")
        service.build_report("q")

        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 2)

    def test_enabled_cache_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(StubReader(rows=[]), StubRenderer(), cache_enabled=True)

    def test_enabled_cache_requires_callable_eviction_policy(self):
        with self.assertRaises(TypeError):
            ReportService(
                StubReader(rows=[]),
                StubRenderer(),
                cache_enabled=True,
                eviction_policy="not callable",
            )

    def test_successful_non_empty_result_is_reused(self):
        reader = StubReader(rows=[{"value": 1}])
        renderer = StubRenderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda _snapshot, _new_key: (),
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(first, second)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_cache_distinguishes_output_formats(self):
        reader = StubReader(rows=[{"value": 1}])
        renderer = StubRenderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda _snapshot, _new_key: (),
        )

        rendered = service.build_report("q")
        csv_result = service.build_report("q", output_format="csv")
        rendered_again = service.build_report("q")
        csv_again = service.build_report("q", output_format="csv")

        self.assertEqual(rendered, {"rendered": [{"value": 1}]})
        self.assertEqual(csv_result, "value\n1\n")
        self.assertIs(rendered_again, rendered)
        self.assertIs(csv_again, csv_result)
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_failures_and_empty_reports_are_not_cached(self):
        error = OSError("read failed")
        failing_reader = StubReader(error=error)
        failing = ReportService(
            failing_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda _snapshot, _new_key: (),
        )
        failing.build_report("q")
        failing.build_report("q")
        self.assertEqual(failing_reader.queries, ["q", "q"])

        empty_reader = StubReader(rows=[])
        empty = ReportService(
            empty_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=lambda _snapshot, _new_key: (),
        )
        empty.build_report("q")
        empty.build_report("q")
        self.assertEqual(empty_reader.queries, ["q", "q"])

    def test_eviction_policy_receives_snapshot_and_can_evict(self):
        snapshots = []

        def evict_previous(snapshot, new_key):
            snapshots.append((snapshot, new_key))
            return [key for key in snapshot if key != new_key]

        reader = StubReader(rows=[{"value": 1}])
        service = ReportService(
            reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=evict_previous,
        )

        service.build_report("first")
        service.build_report("second")
        service.build_report("first")

        self.assertEqual(reader.queries, ["first", "second", "first"])
        self.assertEqual(len(snapshots), 3)
        for snapshot, new_key in snapshots:
            self.assertIn(new_key, snapshot)

    def test_policy_snapshot_mutation_does_not_mutate_internal_cache(self):
        def mutate_snapshot(snapshot, _new_key):
            snapshot.clear()
            return ()

        reader = StubReader(rows=[{"value": 1}])
        renderer = StubRenderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=mutate_snapshot,
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(first, second)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_unhashable_query_preserves_report_behavior(self):
        query = ["q"]
        reader = StubReader(rows=[{"value": 1}])
        renderer = StubRenderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda _snapshot, _new_key: (),
        )

        first = service.build_report(query)
        second = service.build_report(query)

        self.assertEqual(first, second)
        self.assertEqual(reader.queries, [query, query])
        self.assertEqual(len(renderer.calls), 2)


if __name__ == "__main__":
    unittest.main()
