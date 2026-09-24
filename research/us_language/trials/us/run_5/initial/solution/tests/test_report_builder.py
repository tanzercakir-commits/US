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


if __name__ == "__main__":
    unittest.main()
