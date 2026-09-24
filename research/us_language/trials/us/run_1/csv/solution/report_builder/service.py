"""Report orchestration service."""

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating source records."""

    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query):
        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(dict(row) for row in source_rows)
        if not rows:
            return EmptyReport()

        return self._renderer.render(rows)
