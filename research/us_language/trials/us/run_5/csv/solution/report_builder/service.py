from __future__ import annotations

import csv
from copy import deepcopy
from io import StringIO
from typing import Any

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader: Any, renderer: Any) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object, *, output_format: str = "default") -> object:
        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        rows_copy = deepcopy(rows)
        if output_format == "default":
            # Render an independent copy so renderer behavior cannot mutate source rows.
            return self._renderer.render(rows_copy)
        if output_format == "csv":
            columns = sorted({key for row in rows_copy for key in row})
            output = StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows_copy)
            return output.getvalue()

        raise ValueError(f"unsupported output format: {output_format!r}")
