"""UI facade for report requests."""


class UI:
    """Delegate report requests through a ReportService-like object."""

    def __init__(self, service: object) -> None:
        self._service = service

    def build_report(self, query: object) -> object:
        return self._service.build_report(query)  # type: ignore[attr-defined]
