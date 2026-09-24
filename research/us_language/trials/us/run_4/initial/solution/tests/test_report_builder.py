import unittest

from report_builder.results import EmptyReport, ReadFailure
from report_builder.service import ReportService
from report_builder.ui import UI


class RecordingRenderer:
    def __init__(self):
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return {"rendered": rows}


class ReportBuilderTests(unittest.TestCase):
    def test_read_failure_is_distinct(self):
        error = OSError("unavailable")

        class FailingReader:
            def read(self, query):
                raise error

        renderer = RecordingRenderer()
        result = ReportService(FailingReader(), renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_read_returns_empty_report(self):
        class EmptyReader:
            def read(self, query):
                return []

        renderer = RecordingRenderer()
        result = ReportService(EmptyReader(), renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_nonempty_rows_are_rendered_without_mutating_sources(self):
        source = [{"name": "original", "nested": {"count": 1}}]

        class Reader:
            def read(self, query):
                return source

        class MutatingRenderer:
            def render(self, rows):
                rows[0]["name"] = "changed"
                rows[0]["nested"]["count"] = 2
                return "report"

        result = ReportService(Reader(), MutatingRenderer()).build_report("q")

        self.assertEqual(result, "report")
        self.assertEqual(source, [{"name": "original", "nested": {"count": 1}}])

    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "delegated"

        service = Service()
        result = UI(service).build_report("query")

        self.assertEqual(result, "delegated")
        self.assertEqual(service.queries, ["query"])


if __name__ == "__main__":
    unittest.main()
