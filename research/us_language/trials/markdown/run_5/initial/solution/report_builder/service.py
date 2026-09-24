"""Report orchestration service."""

from copy import deepcopy

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating those rows."""

    def __init__(self, reader, renderer) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object):
        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        render_rows = [deepcopy(dict(row)) for row in rows]
        return self._renderer.render(render_rows)
