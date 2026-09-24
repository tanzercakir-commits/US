"""UI-facing entry point for ReportBuilder."""

from __future__ import annotations

from typing import Any


class UI:
    """Delegate report requests to a ReportService-like object."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def build_report(self, query: Any) -> Any:
        return self._service.build_report(query)
