"""Report-building orchestration."""

from copy import deepcopy

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating source data."""

    def __init__(self, reader: object, renderer: object) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object) -> object:
        try:
            source_rows = self._reader.read(query)  # type: ignore[attr-defined]
        except OSError as exc:
            return ReadFailure(exc)

        rows = tuple(deepcopy(dict(row)) for row in source_rows)
        if not rows:
            return EmptyReport()

        return self._renderer.render(rows)  # type: ignore[attr-defined]
