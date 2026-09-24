from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query):
        try:
            rows = self._reader.read(query)
        except OSError as exc:
            return ReadFailure(exc)

        if not rows:
            return EmptyReport()

        return self._renderer.render(rows)
