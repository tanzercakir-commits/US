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


if __name__ == "__main__":
    unittest.main()
