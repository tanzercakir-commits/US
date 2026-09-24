"""Report orchestration service."""

import csv
from copy import deepcopy
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating those rows."""

    def __init__(self, reader, renderer) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object, *, output_format="default"):
        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        report_rows = [deepcopy(dict(row)) for row in rows]
        if output_format == "csv":
            return self._build_csv(report_rows)

        return self._renderer.render(report_rows)

    @staticmethod
    def _build_csv(rows) -> str:
        columns = sorted({key for row in rows for key in row})
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
