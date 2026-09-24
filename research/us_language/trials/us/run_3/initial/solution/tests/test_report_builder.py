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


if __name__ == "__main__":
    unittest.main()
