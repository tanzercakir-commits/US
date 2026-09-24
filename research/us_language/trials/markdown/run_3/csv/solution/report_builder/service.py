"""Report orchestration service."""

import csv
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query, *, output_format="default"):
        """Perform one report request without modifying source rows."""
        try:
            rows = self._reader.read(query)
        except OSError:
            return ReadFailure()

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            fieldnames = sorted({key for row in rows for key in row})
            output = StringIO(newline="")
            writer = csv.DictWriter(
                output,
                fieldnames=fieldnames,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()

        return self._renderer.render(rows)
