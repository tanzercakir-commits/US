"""Report orchestration service."""

import csv
import io

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and render a report without mutating source records."""

    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query, *, output_format="default"):
        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(dict(row) for row in source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "csv":
            columns = sorted({key for row in rows for key in row})
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()

        return self._renderer.render(rows)
