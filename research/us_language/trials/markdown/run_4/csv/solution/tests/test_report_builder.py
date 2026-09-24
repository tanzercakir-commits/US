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

    def test_csv_uses_sorted_union_columns_and_standard_quoting(self):
        rows = [
            {"z": "plain", "a": "x,y"},
            {"m": 'say "hi"', "a": "line\nbreak"},
        ]
        renderer = StubRenderer()

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'a,m,z\n"x,y",,plain\n"line\nbreak","say ""hi""",\n',
        )
        self.assertEqual(renderer.calls, [])
        self.assertEqual(
            rows,
            [
                {"z": "plain", "a": "x,y"},
                {"m": 'say "hi"', "a": "line\nbreak"},
            ],
        )

    def test_csv_preserves_read_failure_and_empty_outcomes(self):
        error = OSError("unavailable")
        failure = ReportService(StubReader(error=error), StubRenderer()).build_report(
            "q", output_format="csv"
        )
        empty = ReportService(StubReader(rows=[]), StubRenderer()).build_report(
            "q", output_format="csv"
        )

        self.assertIsInstance(failure, ReadFailure)
        self.assertIs(failure.error, error)
        self.assertIsInstance(empty, EmptyReport)

    def test_unknown_output_format_is_rejected(self):
        service = ReportService(StubReader(rows=[{"id": 1}]), StubRenderer())

        with self.assertRaises(ValueError):
            service.build_report("q", output_format="json")

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
