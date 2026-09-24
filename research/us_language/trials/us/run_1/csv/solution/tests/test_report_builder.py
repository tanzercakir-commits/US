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
        self.rows = None

    def render(self, rows):
        self.rows = rows
        for row in rows:
            row["rendered"] = True
        return "report"


class ServiceTests(unittest.TestCase):
    def test_read_failure_is_distinct(self):
        renderer = Renderer()
        result = ReportService(Reader(error=OSError("boom")), renderer).build_report("q")
        self.assertIsInstance(result, ReadFailure)
        self.assertEqual(str(result.error), "boom")
        self.assertIsNone(renderer.rows)

    def test_empty_report_is_distinct(self):
        renderer = Renderer()
        result = ReportService(Reader(rows=[]), renderer).build_report("q")
        self.assertIsInstance(result, EmptyReport)
        self.assertIsNone(renderer.rows)

    def test_non_empty_rows_are_rendered_without_mutating_source(self):
        source_rows = [{"id": 1}, {"id": 2}]
        renderer = Renderer()
        result = ReportService(Reader(rows=source_rows), renderer).build_report("q")
        self.assertEqual(result, "report")
        self.assertEqual(source_rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(renderer.rows[0]["rendered"], True)

    def test_csv_uses_sorted_union_of_columns_without_mutating_source(self):
        source_rows = [
            {"name": "Ada", "id": 2},
            {"note": "a,b", "id": 1},
        ]
        renderer = Renderer()

        result = ReportService(Reader(rows=source_rows), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'id,name,note\n2,Ada,\n1,,"a,b"\n',
        )
        self.assertEqual(
            source_rows,
            [
                {"name": "Ada", "id": 2},
                {"note": "a,b", "id": 1},
            ],
        )
        self.assertIsNone(renderer.rows)

    def test_csv_preserves_read_failure_and_empty_report_outcomes(self):
        renderer = Renderer()
        failed = ReportService(Reader(error=OSError("boom")), renderer).build_report(
            "q", output_format="csv"
        )
        empty = ReportService(Reader(rows=[]), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertIsInstance(failed, ReadFailure)
        self.assertIsInstance(empty, EmptyReport)
        self.assertIsNone(renderer.rows)

    def test_ui_delegates_to_service(self):
        class Service:
            def __init__(self):
                self.query = None

            def build_report(self, query):
                self.query = query
                return "ok"

        service = Service()
        self.assertEqual(UI(service).build_report("q"), "ok")
        self.assertEqual(service.query, "q")


if __name__ == "__main__":
    unittest.main()
