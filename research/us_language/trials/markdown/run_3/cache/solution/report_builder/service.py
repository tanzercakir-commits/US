"""Report orchestration service."""

import csv
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(self, reader, renderer, *, cache_enabled=False, eviction_policy=None):
        if cache_enabled and eviction_policy is None:
            raise ValueError(
                "cache eviction policy is unresolved; provide eviction_policy "
                "when caching is enabled"
            )

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query, *, output_format="default"):
        """Perform one report request without modifying source rows."""
        cache_key = (output_format, query)
        if self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            fieldnames = sorted({key for row in rows for key in row})
            output = StringIO(newline="")
            writer = csv.DictWriter(
                output,
                fieldnames=fieldnames,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            result = output.getvalue()
        else:
            result = self._renderer.render(rows)

        if self._cache_enabled:
            self._cache[cache_key] = result
            cache_snapshot = self._cache.copy()
            keys_to_evict = self._eviction_policy(cache_snapshot, cache_key)
            for key in keys_to_evict:
                self._cache.pop(key, None)

        return result
