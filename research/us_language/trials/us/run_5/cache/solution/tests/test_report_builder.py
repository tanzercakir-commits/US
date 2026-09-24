from __future__ import annotations

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
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return {"rendered": rows}


class ReportBuilderTests(unittest.TestCase):
    def test_read_failure_is_distinct_outcome(self):
        error = OSError("unavailable")
        renderer = Renderer()
        result = ReportService(Reader(error=error), renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_read_returns_empty_report_without_rendering(self):
        renderer = Renderer()
        result = ReportService(Reader(rows=[]), renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertNotIsInstance(result, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_rows_are_rendered(self):
        rows = [{"name": "Ada"}]
        renderer = Renderer()
        result = ReportService(Reader(rows=rows), renderer).build_report("q")

        self.assertEqual(result, {"rendered": rows})
        self.assertEqual(renderer.calls, [rows])

    def test_csv_uses_sorted_union_of_columns_and_standard_quoting(self):
        rows = [
            {"name": "Ada, Lovelace", "age": 36},
            {"name": 'Grace "Amazing" Hopper', "language": "COBOL"},
        ]
        renderer = Renderer()
        result = ReportService(Reader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'age,language,name\n36,,"Ada, Lovelace"\n,COBOL,"Grace ""Amazing"" Hopper"\n',
        )
        self.assertEqual(renderer.calls, [])

    def test_csv_does_not_mutate_source_rows(self):
        source = [{"items": [1, 2], "name": "Ada"}]

        ReportService(Reader(rows=source), Renderer()).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(source, [{"items": [1, 2], "name": "Ada"}])

    def test_renderer_cannot_mutate_source_rows(self):
        source = [{"items": [1, 2]}]

        class MutatingRenderer:
            def render(self, rows):
                rows[0]["items"].append(3)
                rows[0]["new"] = True
                return "ok"

        result = ReportService(Reader(rows=source), MutatingRenderer()).build_report("q")

        self.assertEqual(result, "ok")
        self.assertEqual(source, [{"items": [1, 2]}])

    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "report"

        service = Service()
        self.assertEqual(UI(service).build_report("query"), "report")
        self.assertEqual(service.queries, ["query"])

    def test_cache_disabled_preserves_repeated_work(self):
        reader = Reader(rows=[{"name": "Ada"}])
        renderer = Renderer()
        service = ReportService(reader, renderer)

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertEqual(first, second)
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 2)

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(Reader(rows=[{"name": "Ada"}]), Renderer(), cache_enabled=True)

    def test_cache_reuses_successful_non_empty_result_for_equal_query(self):
        reader = Reader(rows=[{"name": "Ada"}])
        renderer = Renderer()
        snapshots = []

        def keep_all(cache_snapshot, new_key):
            snapshots.append((cache_snapshot, new_key))
            return ()

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=keep_all
        )
        query = {"person": "Ada"}

        first = service.build_report(query)
        second = service.build_report({"person": "Ada"})

        self.assertIs(first, second)
        self.assertEqual(reader.queries, [query])
        self.assertEqual(len(renderer.calls), 1)
        self.assertEqual(len(snapshots), 1)
        snapshot, new_key = snapshots[0]
        self.assertEqual(list(snapshot), [new_key])
        with self.assertRaises(TypeError):
            snapshot[new_key] = "changed"

    def test_cache_keeps_default_and_csv_results_separate(self):
        reader = Reader(rows=[{"name": "Ada"}])
        renderer = Renderer()
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda snapshot, key: ()
        )

        default_result = service.build_report("q")
        csv_result = service.build_report("q", output_format="csv")
        self.assertEqual(service.build_report("q"), default_result)
        self.assertEqual(service.build_report("q", output_format="csv"), csv_result)

        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 1)
        self.assertEqual(csv_result, "name\nAda\n")

    def test_eviction_policy_removes_returned_key(self):
        reader = Reader(rows=[{"name": "Ada"}])
        renderer = Renderer()

        def evict_new(cache_snapshot, new_key):
            return (new_key,)

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=evict_new
        )
        service.build_report("q")
        service.build_report("q")

        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 2)

    def test_failures_and_empty_reports_are_not_cached(self):
        empty_reader = Reader(rows=[])
        service = ReportService(
            empty_reader,
            Renderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, key: (),
        )
        service.build_report("q")
        service.build_report("q")
        self.assertEqual(empty_reader.queries, ["q", "q"])

        error = OSError("unavailable")
        failing_reader = Reader(error=error)
        service = ReportService(
            failing_reader,
            Renderer(),
            cache_enabled=True,
            eviction_policy=lambda snapshot, key: (),
        )
        service.build_report("q")
        service.build_report("q")
        self.assertEqual(failing_reader.queries, ["q", "q"])


if __name__ == "__main__":
    unittest.main()
