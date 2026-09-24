import csv
import io

from .results import EmptyReport, ReadFailure


class ReportService:
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
        cache_key = None
        if self._cache_enabled:
            cache_key = (query, output_format)
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            rows = self._reader.read(query)
        except OSError as exc:
            return ReadFailure(exc)

        if not rows:
            return EmptyReport()

        if output_format == "default":
            result = self._renderer.render(rows)
        elif output_format == "csv":
            rows = list(rows)
            if not rows:
                return EmptyReport()

            columns = sorted({key for row in rows for key in row.keys()})
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            result = output.getvalue()
        else:
            raise ValueError(f"unsupported output format: {output_format}")

        if self._cache_enabled:
            self._cache[cache_key] = result
            snapshot = dict(self._cache)
            for key in self._eviction_policy(snapshot, cache_key):
                self._cache.pop(key, None)

        return result
