from __future__ import annotations

from copy import deepcopy
from typing import Any

from .results import EmptyReport, ReadFailure


class ReportService:
    def __init__(self, reader: Any, renderer: Any) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object) -> object:
        try:
            rows = self._reader.read(query)
        except OSError as error:
            return ReadFailure(error)

        if not rows:
            return EmptyReport()

        # Render an independent copy so renderer behavior cannot mutate source rows.
        return self._renderer.render(deepcopy(rows))
