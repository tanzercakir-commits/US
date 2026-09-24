"""Report-building service."""

import csv
from copy import deepcopy
from io import StringIO

from .data import DataReader
from .render import Renderer
from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and produce the corresponding report outcome."""

    def __init__(
        self,
        reader: DataReader,
        renderer: Renderer,
        *,
        cache_enabled=False,
        eviction_policy=None,
    ):
        if cache_enabled and eviction_policy is None:
            raise ValueError(
                "cache_enabled=True requires an explicit eviction_policy"
            )
        if cache_enabled and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable when caching is enabled")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query, *, output_format="default"):
        cache_key = self._cache_key(query, output_format)
        if self._cache_enabled and cache_key is not None:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            fieldnames = sorted({key for row in rows for key in row.keys()})
            output = StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            result = output.getvalue()
        else:
            # Render an independent snapshot so renderer behavior cannot mutate
            # the source records returned by the reader.
            result = self._renderer.render(deepcopy(rows))

        if self._cache_enabled and cache_key is not None:
            self._cache[cache_key] = result
            cache_snapshot = self._cache.copy()
            for key in self._eviction_policy(cache_snapshot, cache_key):
                self._cache.pop(key, None)

        return result

    @staticmethod
    def _cache_key(query, output_format):
        key = (query, output_format)
        try:
            hash(key)
        except TypeError:
            return None
        return key
