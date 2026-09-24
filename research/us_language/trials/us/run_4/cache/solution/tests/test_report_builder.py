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

    def test_explicit_default_preserves_renderer_behavior(self):
        source = [{"b": 2, "a": 1}]

        class Reader:
            def read(self, query):
                return source

        renderer = RecordingRenderer()
        result = ReportService(Reader(), renderer).build_report(
            "q", output_format="default"
        )

        self.assertEqual(result, {"rendered": ({"b": 2, "a": 1},)})
        self.assertEqual(renderer.calls, [({"b": 2, "a": 1},)])
        self.assertEqual(source, [{"b": 2, "a": 1}])

    def test_csv_uses_sorted_union_and_standard_escaping(self):
        source = [
            {"b": "comma,value", "a": "first"},
            {"c": 'say "hi"', "a": "second"},
        ]

        class Reader:
            def read(self, query):
                return source

        renderer = RecordingRenderer()
        result = ReportService(Reader(), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertEqual(
            result,
            'a,b,c\nfirst,"comma,value",\nsecond,,"say ""hi"""\n',
        )
        self.assertEqual(renderer.calls, [])
        self.assertEqual(
            source,
            [
                {"b": "comma,value", "a": "first"},
                {"c": 'say "hi"', "a": "second"},
            ],
        )

    def test_csv_empty_and_read_failure_keep_existing_results(self):
        class EmptyReader:
            def read(self, query):
                return []

        class FailingReader:
            def read(self, query):
                raise OSError("unavailable")

        renderer = RecordingRenderer()
        empty = ReportService(EmptyReader(), renderer).build_report(
            "q", output_format="csv"
        )
        failure = ReportService(FailingReader(), renderer).build_report(
            "q", output_format="csv"
        )

        self.assertIsInstance(empty, EmptyReport)
        self.assertIsInstance(failure, ReadFailure)
        self.assertEqual(renderer.calls, [])

    def test_unknown_output_format_is_rejected(self):
        class Reader:
            def read(self, query):
                return [{"a": 1}]

        with self.assertRaisesRegex(ValueError, "unsupported output_format"):
            ReportService(Reader(), RecordingRenderer()).build_report(
                "q", output_format="json"
            )

    def test_cache_requires_explicit_eviction_policy(self):
        with self.assertRaisesRegex(ValueError, "eviction policy is unresolved"):
            ReportService(object(), object(), cache_enabled=True)

    def test_cache_reuses_equal_query_and_policy_gets_snapshot_copy(self):
        class Reader:
            def __init__(self):
                self.calls = []

            def read(self, query):
                self.calls.append(query)
                return [{"value": 1}]

        policy_calls = []

        def policy(snapshot, new_key):
            policy_calls.append((dict(snapshot), new_key))
            snapshot.clear()
            return ()

        reader = Reader()
        renderer = RecordingRenderer()
        service = ReportService(
            reader, renderer, cache_enabled=True, eviction_policy=policy
        )

        first = service.build_report({"q": [1, 2]})
        second = service.build_report({"q": [1, 2]})

        self.assertIs(first, second)
        self.assertEqual(len(reader.calls), 1)
        self.assertEqual(len(renderer.calls), 1)
        self.assertEqual(len(policy_calls), 1)
        snapshot, new_key = policy_calls[0]
        self.assertIn(new_key, snapshot)

    def test_eviction_policy_can_remove_just_stored_key(self):
        class Reader:
            def __init__(self):
                self.calls = 0

            def read(self, query):
                self.calls += 1
                return [{"value": self.calls}]

        def policy(snapshot, new_key):
            return (new_key,)

        reader = Reader()
        service = ReportService(
            reader, RecordingRenderer(), cache_enabled=True, eviction_policy=policy
        )

        service.build_report("q")
        service.build_report("q")

        self.assertEqual(reader.calls, 2)

    def test_cache_key_keeps_default_and_csv_results_separate(self):
        class Reader:
            def __init__(self):
                self.calls = 0

            def read(self, query):
                self.calls += 1
                return [{"a": 1}]

        reader = Reader()
        renderer = RecordingRenderer()
        service = ReportService(
            reader,
            renderer,
            cache_enabled=True,
            eviction_policy=lambda snapshot, new_key: (),
        )

        default_result = service.build_report("q")
        csv_result = service.build_report("q", output_format="csv")
        cached_csv_result = service.build_report("q", output_format="csv")

        self.assertEqual(default_result, {"rendered": ({"a": 1},)})
        self.assertEqual(csv_result, "a\n1\n")
        self.assertIs(csv_result, cached_csv_result)
        self.assertEqual(reader.calls, 2)
        self.assertEqual(len(renderer.calls), 1)


if __name__ == "__main__":
    unittest.main()
