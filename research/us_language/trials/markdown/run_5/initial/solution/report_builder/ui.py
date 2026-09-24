"""UI-facing report entry point."""


class UI:
    """Delegate report requests to the supplied service."""

    def __init__(self, service) -> None:
        self._service = service

    def build_report(self, query: object):
        return self._service.build_report(query)
