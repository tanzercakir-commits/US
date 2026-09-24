import unittest

from report_builder import EmptyReport, ReadFailure, ReportService, UI


class StubReader:
    def __init__(self, rows=None, error=None):
        self.rows = [] if rows is None else rows
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


class ReportBuilderTests(unittest.TestCase):
    def test_read_failure_is_distinct_and_renderer_is_not_called(self):
        error = OSError("unavailable")
        reader = StubReader(error=error)
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertIs(result.error, error)
        self.assertEqual(renderer.calls, [])

    def test_empty_success_returns_empty_report(self):
        reader = StubReader(rows=[])
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_success_returns_renderer_output(self):
        rows = [{"id": 1}, {"id": 2}]
        renderer = StubRenderer(result={"ok": True})

        result = ReportService(StubReader(rows=rows), renderer).build_report("q")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(renderer.calls[0], ({"id": 1}, {"id": 2}))

    def test_renderer_cannot_mutate_source_records_through_received_rows(self):
        rows = [{"id": 1, "tags": ["a"]}]

        class MutatingRenderer:
            def render(self, render_rows):
                render_rows[0]["id"] = 9
                render_rows[0]["tags"].append("b")
                return "done"

        result = ReportService(StubReader(rows=rows), MutatingRenderer()).build_report("q")

        self.assertEqual(result, "done")
        self.assertEqual(rows, [{"id": 1, "tags": ["a"]}])

    def test_ui_delegates_to_service(self):
        class StubService:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "report"

        service = StubService()
        self.assertEqual(UI(service).build_report("q"), "report")
        self.assertEqual(service.queries, ["q"])


if __name__ == "__main__":
    unittest.main()
