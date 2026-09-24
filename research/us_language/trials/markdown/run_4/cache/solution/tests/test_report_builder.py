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

    def test_cache_disabled_preserves_repeated_read_and_render_behavior(self):
        reader = StubReader(rows=[{"id": 1}])
        renderer = StubRenderer(result=object())
        service = ReportService(reader, renderer)

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(first, second)
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 2)

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(StubReader(), StubRenderer(), cache_enabled=True)

    def test_cache_enabled_reuses_successful_non_empty_result(self):
        reader = StubReader(rows=[{"id": 1}])
        cached_result = {"ok": True}
        renderer = StubRenderer(result=cached_result)
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda snapshot, key: ()
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(first, cached_result)
        self.assertIs(second, cached_result)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_cache_does_not_store_failure_or_empty_result(self):
        reader = StubReader(error=OSError("unavailable"))
        renderer = StubRenderer(result="rendered")
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda snapshot, key: ()
        )

        self.assertIsInstance(service.build_report("q"), ReadFailure)
        reader.error = None
        reader.rows = []
        self.assertIsInstance(service.build_report("q"), EmptyReport)
        reader.rows = [{"id": 1}]
        self.assertEqual(service.build_report("q"), "rendered")

        self.assertEqual(reader.queries, ["q", "q", "q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_cache_keeps_output_formats_distinct(self):
        reader = StubReader(rows=[{"id": 1}])
        renderer = StubRenderer(result="default-report")
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=lambda snapshot, key: ()
        )

        csv_result = service.build_report("q", output_format="csv")
        default_result = service.build_report("q")
        cached_csv_result = service.build_report("q", output_format="csv")

        self.assertEqual(csv_result, "id\n1\n")
        self.assertEqual(default_result, "default-report")
        self.assertEqual(cached_csv_result, csv_result)
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(len(renderer.calls), 1)

    def test_eviction_policy_can_remove_existing_cache_entries(self):
        reader = StubReader(rows=[{"id": 1}])
        renderer = StubRenderer(result="rendered")

        def keep_only_new_key(snapshot, new_key):
            return [key for key in snapshot if key != new_key]

        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=keep_only_new_key
        )

        service.build_report("q1")
        service.build_report("q2")
        service.build_report("q1")

        self.assertEqual(reader.queries, ["q1", "q2", "q1"])
        self.assertEqual(len(renderer.calls), 3)

    def test_eviction_policy_receives_snapshot_copy(self):
        reader = StubReader(rows=[{"id": 1}])
        renderer = StubRenderer(result="rendered")
        calls = []

        def policy(snapshot, new_key):
            calls.append((dict(snapshot), new_key))
            snapshot.clear()
            return ()

        service = ReportService(reader, renderer, cache_enabled=True, eviction_policy=policy)

        service.build_report("q")
        service.build_report("q")

        self.assertEqual(len(calls), 1)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(len(renderer.calls), 1)


if __name__ == "__main__":
    unittest.main()
