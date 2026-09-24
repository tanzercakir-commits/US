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
