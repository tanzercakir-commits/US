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


if __name__ == "__main__":
    unittest.main()
