import csv
from copy import deepcopy
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query, *, output_format="default"):
        try:
            source_rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        rows = tuple(source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "csv":
            return self._render_csv(rows)
        if output_format != "default":
            raise ValueError(f"unsupported output format: {output_format}")

        render_rows = tuple(deepcopy(dict(row)) for row in rows)
        return self._renderer.render(render_rows)

    @staticmethod
    def _render_csv(rows):
        csv_rows = tuple(dict(row) for row in rows)
        fieldnames = sorted({key for row in csv_rows for key in row})
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
        return output.getvalue()
