"""Report-building orchestration."""

import csv
from copy import deepcopy
from dataclasses import dataclass
from io import StringIO

from .results import EmptyReport, ReadFailure


@dataclass(frozen=True, slots=True)
class _CacheKey:
    query: object
    output_format: str

    def __hash__(self) -> int:
        try:
            query_hash = hash(self.query)
        except TypeError:
            query_hash = 0
        return hash((self.output_format, query_hash))


class ReportService:
    """Read source rows and build a report without mutating source data."""

    def __init__(
        self,
        reader: object,
        renderer: object,
        *,
        cache_enabled: bool = False,
        eviction_policy: object = None,
    ) -> None:
        if cache_enabled and eviction_policy is None:
            raise ValueError("cache eviction policy is unresolved; provide eviction_policy")
        if cache_enabled and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable when caching is enabled")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache: dict[_CacheKey, object] = {}

    def build_report(self, query: object, *, output_format: str = "default") -> object:
        cache_key = _CacheKey(query, output_format)
        if self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            source_rows = self._reader.read(query)  # type: ignore[attr-defined]
        except OSError as exc:
            return ReadFailure(exc)

        rows = tuple(deepcopy(dict(row)) for row in source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "default":
            result = self._renderer.render(rows)  # type: ignore[attr-defined]
        elif output_format == "csv":
            result = _build_csv(rows)
        else:
            raise ValueError(f"unsupported output_format: {output_format!r}")

        if self._cache_enabled:
            self._cache[cache_key] = result
            snapshot = dict(self._cache)
            policy = self._eviction_policy
            assert callable(policy)
            for key in policy(snapshot, cache_key):
                self._cache.pop(key, None)

        return result


def _build_csv(rows: tuple[dict[object, object], ...]) -> str:
    columns = sorted({key for row in rows for key in row})
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
