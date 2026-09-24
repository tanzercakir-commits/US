"""Report orchestration service."""

from __future__ import annotations

import csv
from copy import deepcopy
from io import StringIO
from typing import Any

from .results import EmptyReport, ReadFailure


class ReportService:
    """Build reports from an injected reader and renderer."""

    def __init__(self, reader: Any, renderer: Any) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: Any, *, output_format: str = "default") -> Any:
        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if len(rows) == 0:
            return EmptyReport()

        if output_format == "csv":
            columns = sorted({key for row in rows for key in row.keys()})
            output = StringIO(newline="")
            writer = csv.DictWriter(
                output,
                fieldnames=columns,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()

        # Render a defensive copy so renderer behavior cannot mutate source rows.
        return self._renderer.render(deepcopy(rows))
