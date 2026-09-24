"""Report-building service."""

import csv
from copy import deepcopy
from io import StringIO

from .data import DataReader
from .render import Renderer
from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and produce the corresponding report outcome."""

    def __init__(self, reader: DataReader, renderer: Renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query, *, output_format="default"):
        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            fieldnames = sorted({key for row in rows for key in row.keys()})
            output = StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()

        # Render an independent snapshot so renderer behavior cannot mutate
        # the source records returned by the reader.
        return self._renderer.render(deepcopy(rows))
