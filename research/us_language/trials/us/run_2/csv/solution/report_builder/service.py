import csv
import io

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader, renderer):
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query, *, output_format="default"):
        try:
            rows = self._reader.read(query)
        except OSError as exc:
            return ReadFailure(exc)

        if not rows:
            return EmptyReport()

        if output_format == "default":
            return self._renderer.render(rows)

        if output_format == "csv":
            rows = list(rows)
            if not rows:
                return EmptyReport()

            columns = sorted({key for row in rows for key in row.keys()})
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()

        raise ValueError(f"unsupported output format: {output_format}")
