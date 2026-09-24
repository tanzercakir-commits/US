import unittest

from report_builder.data import DataReader
from report_builder.render import Renderer
from report_builder.results import EmptyReport, ReadFailure
from report_builder.service import ReportService
from report_builder.ui import UI


class StubReader(DataReader):
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.queries = []

    def read(self, query):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.rows


class StubRenderer(Renderer):
    def __init__(self, result="rendered"):
        self.result = result
        self.calls = []

    def render(self, rows):
        self.calls.append(rows)
        return self.result


class ReportServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct_and_renderer_is_not_called(self):
        renderer = StubRenderer()
        service = ReportService(StubReader(error=OSError("read failed")), renderer)

        result = service.build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertNotIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_empty_success_returns_empty_report(self):
        renderer = StubRenderer()
        service = ReportService(StubReader(rows=[]), renderer)

        result = service.build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertNotIsInstance(result, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_success_returns_renderer_output_without_modifying_rows(self):
        rows = [{"name": "alpha"}, {"name": "beta"}]
        before = [row.copy() for row in rows]
        renderer = StubRenderer(result={"report": 2})
        service = ReportService(StubReader(rows=rows), renderer)

        result = service.build_report("q")

        self.assertEqual(result, {"report": 2})
        self.assertEqual(renderer.calls, [rows])
        self.assertEqual(rows, before)

    def test_only_oserror_is_converted_to_read_failure(self):
        service = ReportService(StubReader(error=ValueError("bad input")), StubRenderer())

        with self.assertRaises(ValueError):
            service.build_report("q")


class UITests(unittest.TestCase):
    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "ok"

        service = Service()
        ui = UI(service)

        self.assertEqual(ui.build_report("q"), "ok")
        self.assertEqual(service.queries, ["q"])


if __name__ == "__main__":
    unittest.main()
