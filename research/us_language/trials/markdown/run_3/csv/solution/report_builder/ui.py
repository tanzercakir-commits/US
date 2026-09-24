"""UI-facing ReportBuilder entry point."""


class UI:
    """Delegate report requests to an injected ReportService-like object."""

    def __init__(self, service):
        self._service = service

    def build_report(self, query):
        """Delegate a report request through the service."""
        return self._service.build_report(query)
