"""Report orchestration service."""

from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query):
        """Perform one report request without modifying source rows."""
        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        return self._renderer.render(rows)
