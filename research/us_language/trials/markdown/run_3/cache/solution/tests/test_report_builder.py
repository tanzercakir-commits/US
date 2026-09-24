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

    def test_cache_disabled_preserves_repeat_behavior(self):
        rows = [{"name": "alpha"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result="rendered")
        service = ReportService(reader, renderer)

        self.assertEqual(service.build_report("q"), "rendered")
        self.assertEqual(service.build_report("q"), "rendered")
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, [rows, rows])

    def test_cache_enabled_requires_explicit_eviction_policy(self):
        with self.assertRaises(ValueError):
            ReportService(StubReader(rows=[{"name": "alpha"}]), StubRenderer(), cache_enabled=True)

    def test_cache_reuses_successful_non_empty_result(self):
        rows = [{"name": "alpha"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result={"report": 1})
        policy_calls = []

        def keep_all(cache_snapshot, new_key):
            policy_calls.append((cache_snapshot, new_key))
            return ()

        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=keep_all,
        )

        first = service.build_report("q")
        second = service.build_report("q")

        self.assertIs(first, second)
        self.assertEqual(reader.queries, ["q"])
        self.assertEqual(renderer.calls, [rows])
        self.assertEqual(len(policy_calls), 1)
        snapshot, new_key = policy_calls[0]
        self.assertEqual(new_key, ("default", "q"))
        self.assertEqual(snapshot[new_key], first)

    def test_cache_does_not_store_read_failure_or_empty_report(self):
        keep_all = lambda cache_snapshot, new_key: ()

        failing_reader = StubReader(error=OSError("read failed"))
        failing_service = ReportService(
            failing_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=keep_all,
        )
        self.assertIsInstance(failing_service.build_report("q"), ReadFailure)
        self.assertIsInstance(failing_service.build_report("q"), ReadFailure)
        self.assertEqual(failing_reader.queries, ["q", "q"])

        empty_reader = StubReader(rows=[])
        empty_service = ReportService(
            empty_reader,
            StubRenderer(),
            cache_enabled=True,
            eviction_policy=keep_all,
        )
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertIsInstance(empty_service.build_report("q"), EmptyReport)
        self.assertEqual(empty_reader.queries, ["q", "q"])

    def test_eviction_policy_receives_copy_and_can_evict_keys(self):
        reader = StubReader(rows=[{"name": "alpha"}])
        renderer = StubRenderer()
        seen_snapshots = []

        def evict_previous(cache_snapshot, new_key):
            seen_snapshots.append(cache_snapshot)
            cache_snapshot.clear()
            if new_key == ("default", "q2"):
                return [("default", "q1")]
            return ()

        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=evict_previous,
        )

        service.build_report("q1")
        service.build_report("q2")
        service.build_report("q1")

        self.assertEqual(reader.queries, ["q1", "q2", "q1"])
        self.assertEqual(len(seen_snapshots), 3)

    def test_cache_keeps_csv_and_default_results_separate(self):
        rows = [{"name": "alpha"}]
        reader = StubReader(rows=rows)
        renderer = StubRenderer(result="rendered")
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda cache_snapshot, new_key: (),
        )

        self.assertEqual(service.build_report("q"), "rendered")
        self.assertEqual(service.build_report("q", output_format="csv"), "name\nalpha\n")
        self.assertEqual(service.build_report("q"), "rendered")
        self.assertEqual(service.build_report("q", output_format="csv"), "name\nalpha\n")
        self.assertEqual(reader.queries, ["q", "q"])
        self.assertEqual(renderer.calls, [rows])


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
