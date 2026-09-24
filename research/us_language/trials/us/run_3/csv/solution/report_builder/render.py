"""Rendering interfaces used by ReportService."""

import csv
from io import StringIO


class Renderer:
    """Interface for objects that render report rows."""

    def render(self, rows):
        raise NotImplementedError


class CsvRenderer:
    """Render mapping-like rows as CSV text."""

    def render(self, rows):
        columns = sorted({key for row in rows for key in row.keys()})
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
