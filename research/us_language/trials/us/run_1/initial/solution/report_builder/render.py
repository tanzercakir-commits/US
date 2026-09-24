"""Renderer interface for non-empty report rows."""


class Renderer:
    """Base renderer interface used by ReportService."""

    def render(self, rows):
        raise NotImplementedError
