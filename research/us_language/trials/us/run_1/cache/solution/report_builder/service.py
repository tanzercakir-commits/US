"""Report orchestration service."""

import csv
import io
from types import MappingProxyType

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating source records."""

    def __init__(self, reader, renderer, *, cache_enabled=False, eviction_policy=None):
        if cache_enabled and eviction_policy is None:
            raise ValueError("cache_enabled requires an explicit eviction_policy")
        if cache_enabled and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query, *, output_format="default"):
        cache_key = self._cache_key(query, output_format)
        if cache_key is not None and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(dict(row) for row in source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "csv":
            columns = sorted({key for row in rows for key in row})
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            result = output.getvalue()
        else:
            result = self._renderer.render(rows)

        if cache_key is not None:
            self._cache[cache_key] = result
            snapshot = MappingProxyType(dict(self._cache))
            for key in self._eviction_policy(snapshot, cache_key):
                self._cache.pop(key, None)

        return result

    def _cache_key(self, query, output_format):
        if not self._cache_enabled:
            return None

        key = (query, output_format)
        try:
            hash(key)
        except TypeError:
            return None
        return key
