from copy import deepcopy

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query):
        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(source_rows)
        if not rows:
            return EmptyReport()

        render_rows = tuple(deepcopy(dict(row)) for row in rows)
        return self._renderer.render(render_rows)
