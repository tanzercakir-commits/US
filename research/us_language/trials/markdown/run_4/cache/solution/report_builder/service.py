import csv
from copy import deepcopy
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader, renderer, *, cache_enabled=False, eviction_policy=None):
        if cache_enabled and eviction_policy is None:
            raise ValueError("cache eviction policy is unresolved; supply eviction_policy")
        if cache_enabled and not callable(eviction_policy):
            raise TypeError("eviction_policy must be callable when caching is enabled")

        self._reader = reader
        self._renderer = renderer
        self._cache_enabled = cache_enabled
        self._eviction_policy = eviction_policy
        self._cache = {}

    def build_report(self, query, *, output_format="default"):
        cache_key = None
        if self._cache_enabled:
            cache_key = (query, output_format)
            try:
                return self._cache[cache_key]
            except KeyError:
                pass
            except TypeError:
                cache_key = None

        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "csv":
            result = self._render_csv(rows)
        elif output_format == "default":
            render_rows = tuple(deepcopy(dict(row)) for row in rows)
            result = self._renderer.render(render_rows)
        else:
            raise ValueError(f"unsupported output format: {output_format}")

        if cache_key is not None:
            self._cache[cache_key] = result
            cache_snapshot = dict(self._cache)
            for key in self._eviction_policy(cache_snapshot, cache_key):
                self._cache.pop(key, None)

        return result

    @staticmethod
    def _render_csv(rows):
        csv_rows = tuple(dict(row) for row in rows)
        fieldnames = sorted({key for row in csv_rows for key in row})
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
        return output.getvalue()
