"""Report orchestration service."""

import csv
from copy import deepcopy
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating those rows."""

    def __init__(
        self, reader, renderer, *, cache_enabled=False, eviction_policy=None
    ) -> None:
        if cache_enabled and eviction_policy is None:
            raise ValueError(
                "cache eviction policy is unresolved; supply eviction_policy"
            )
        if eviction_policy is not None and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query: object, *, output_format="default"):
        cache_key = (query, output_format)
        if self._cache_enabled:
            cached = self._get_cached(cache_key)
            if cached is not _CACHE_MISS:
                return cached

        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        report_rows = [deepcopy(dict(row)) for row in rows]
        if output_format == "csv":
            result = self._build_csv(report_rows)
        else:
            result = self._renderer.render(report_rows)

        if self._cache_enabled:
            self._store_cached(cache_key, result)
        return result

    def _get_cached(self, cache_key):
        try:
            return self._cache[cache_key]
        except (KeyError, TypeError):
            return _CACHE_MISS

    def _store_cached(self, cache_key, result) -> None:
        try:
            self._cache[cache_key] = result
        except TypeError:
            return

        cache_snapshot = dict(self._cache)
        keys_to_evict = self._eviction_policy(cache_snapshot, cache_key)
        for key in keys_to_evict:
            self._cache.pop(key, None)

    @staticmethod
    def _build_csv(rows) -> str:
        columns = sorted({key for row in rows for key in row})
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()


_CACHE_MISS = object()
