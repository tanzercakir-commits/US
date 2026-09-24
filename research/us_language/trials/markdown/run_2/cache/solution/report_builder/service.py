"""Report orchestration service."""

from __future__ import annotations

import csv
from copy import deepcopy
from io import StringIO
from typing import Any

from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(
        self,
        reader: Any,
        renderer: Any,
        *,
        cache_enabled: bool = False,
        eviction_policy: Any = None,
    ) -> None:
        if cache_enabled and eviction_policy is None:
            raise ValueError(
                "cache eviction policy is unresolved; supply eviction_policy"
            )
        if cache_enabled and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable when caching is enabled")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache: dict[Any, Any] = {}

    @staticmethod
    def _cache_key(query: Any, output_format: str) -> Any | None:
        key = (query, output_format)
        try:
            hash(key)
        except TypeError:
            return None
        return key

    def _store_cached_result(self, key: Any, result: Any) -> None:
        self._cache[key] = result
        snapshot = dict(self._cache)
        keys_to_evict = self._eviction_policy(snapshot, key)
        for evicted_key in keys_to_evict:
            self._cache.pop(evicted_key, None)

    def build_report(self, query: Any, *, output_format: str = "default") -> Any:
        cache_key = None
        if self._cache_enabled:
            cache_key = self._cache_key(query, output_format)
            if cache_key is not None and cache_key in self._cache:
                return self._cache[cache_key]

        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            columns = sorted({key for row in rows for key in row.keys()})
            output = StringIO(newline="")
            writer = csv.DictWriter(
                output,
                fieldnames=columns,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            result = output.getvalue()
        else:
            # Render a defensive copy so renderer behavior cannot mutate source rows.
            result = self._renderer.render(deepcopy(rows))

        if cache_key is not None:
            self._store_cached_result(cache_key, result)

        return result
