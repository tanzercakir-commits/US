from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from copy import deepcopy
from io import StringIO
from typing import Any

from .results import EmptyReport, ReadFailure


class _CacheSnapshot(Mapping[object, object]):
    """Shallow, read-only view of cache entries for eviction policies."""

    def __init__(self, entries: Iterable[tuple[object, object]]) -> None:
        self._entries = tuple(entries)

    def __getitem__(self, key: object) -> object:
        for cached_key, value in self._entries:
            if cached_key == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        for key, _ in self._entries:
            yield key

    def __len__(self) -> int:
        return len(self._entries)


class ReportService:
    def __init__(
        self,
        reader: Any,
        renderer: Any,
        *,
        cache_enabled: bool = False,
        eviction_policy=None,
    ) -> None:
        if cache_enabled and eviction_policy is None:
            raise ValueError(
                "cache_enabled=True requires an explicit eviction_policy"
            )
        if eviction_policy is not None and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache: list[tuple[object, object]] = []

    def build_report(self, query: object, *, output_format: str = "default") -> object:
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

        rows_copy = deepcopy(rows)
        if output_format == "default":
            # Render an independent copy so renderer behavior cannot mutate source rows.
            result = self._renderer.render(rows_copy)
        elif output_format == "csv":
            columns = sorted({key for row in rows_copy for key in row})
            output = StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows_copy)
            result = output.getvalue()
        else:
            raise ValueError(f"unsupported output format: {output_format!r}")

        if self._cache_enabled:
            self._store_cached(cache_key, result)
        return result

    def _get_cached(self, key: object) -> object:
        for cached_key, value in self._cache:
            if cached_key == key:
                return value
        return _CACHE_MISS

    def _store_cached(self, key: object, value: object) -> None:
        for index, (cached_key, _) in enumerate(self._cache):
            if cached_key == key:
                self._cache[index] = (key, value)
                break
        else:
            self._cache.append((key, value))

        snapshot = _CacheSnapshot(self._cache)
        keys_to_evict = self._eviction_policy(snapshot, key)
        for key_to_evict in keys_to_evict:
            self._cache = [
                entry for entry in self._cache if entry[0] != key_to_evict
            ]


_CACHE_MISS = object()
