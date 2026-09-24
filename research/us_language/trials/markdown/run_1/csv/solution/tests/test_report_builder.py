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
    def test_read_failure_is_distinct_outcome_and_does_not_render(self):
        reader = StubReader(error=OSError("read failed"))
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_empty_read_returns_empty_report_and_does_not_render(self):
        reader = StubReader(rows=[])
        renderer = StubRenderer()

        result = ReportService(reader, renderer).build_report("q")

        self.assertIsInstance(result, EmptyReport)
        self.assertNotIsInstance(result, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_non_empty_read_returns_renderer_output(self):
        rows = [{"name": "Ada"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result={"report": 1})

        result = ReportService(reader, renderer).build_report("q")

        self.assertEqual(result, {"report": 1})
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(renderer.calls[0], rows)

    def test_explicit_default_preserves_renderer_output(self):
        rows = [{"name": "Ada"}]
        renderer = StubRenderer(result="default-result")

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="default"
        )

        self.assertEqual(result, "default-result")
        self.assertEqual(renderer.calls, [rows])

    def test_csv_uses_sorted_union_of_columns_and_standard_quoting(self):
        rows = [
            {"z": "last", "a": "x,y"},
            {"m": 'he said "hi"', "a": "plain"},
        ]
        renderer = StubRenderer()

        result = ReportService(StubReader(rows=rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'a,m,z\n"x,y",,last\nplain,"he said ""hi""",\n',
        )
        self.assertEqual(renderer.calls, [])
        self.assertEqual(rows, [
            {"z": "last", "a": "x,y"},
            {"m": 'he said "hi"', "a": "plain"},
        ])

    def test_csv_preserves_read_failure_and_empty_report_outcomes(self):
        renderer = StubRenderer()

        failed = ReportService(StubReader(error=OSError("read failed")), renderer)
        empty = ReportService(StubReader(rows=[]), renderer)

        self.assertIsInstance(failed.build_report("q", output_format="csv"), ReadFailure)
        self.assertIsInstance(empty.build_report("q", output_format="csv"), EmptyReport)
        self.assertEqual(renderer.calls, [])

    def test_renderer_cannot_mutate_source_records(self):
        source_rows = [{"nested": {"value": 1}}]

        class MutatingRenderer:
            def render(self, rows):
                rows[0]["nested"]["value"] = 99
                rows[0]["extra"] = True
                return "ok"

        result = ReportService(StubReader(rows=source_rows), MutatingRenderer()).build_report("q")

        self.assertEqual(result, "ok")
        self.assertEqual(source_rows, [{"nested": {"value": 1}}])


class UITests(unittest.TestCase):
    def test_ui_delegates_to_service(self):
        class StubService:
            def __init__(self):
                self.queries = []

            def build_report(self, query):
                self.queries.append(query)
                return "service-result"

        service = StubService()

        result = UI(service).build_report("q")

        self.assertEqual(result, "service-result")
        self.assertEqual(service.queries, ["q"])


if __name__ == "__main__":
    unittest.main()
