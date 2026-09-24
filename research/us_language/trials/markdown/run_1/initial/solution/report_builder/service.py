"""Report-building service."""

from copy import deepcopy

from .data import DataReader
from .render import Renderer
from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and produce the corresponding report outcome."""

    def __init__(self, reader: DataReader, renderer: Renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query):
        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        # Render an independent snapshot so renderer behavior cannot mutate
        # the source records returned by the reader.
        return self._renderer.render(deepcopy(rows))
