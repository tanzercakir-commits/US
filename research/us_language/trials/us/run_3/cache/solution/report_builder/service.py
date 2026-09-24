"""Report-building orchestration."""

from .render import CsvRenderer
from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(self, reader, renderer, *, cache_enabled=False, eviction_policy=None):
        if cache_enabled and eviction_policy is None:
            raise ValueError("cache_enabled requires an explicit eviction_policy")
        if eviction_policy is not None and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query, *, output_format="default"):
        cache_key = (query, output_format)
        if self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        if output_format == "csv":
            result = CsvRenderer().render(rows)
        else:
            result = self._renderer.render(rows)

        if self._cache_enabled:
            self._cache[cache_key] = result
            snapshot = self._cache.copy()
            for key in self._eviction_policy(snapshot, cache_key):
                self._cache.pop(key, None)

        return result
