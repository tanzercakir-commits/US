"""Rendering interface used by ReportService."""


class Renderer:
    """Interface for objects that render report rows."""

    def render(self, rows):
        raise NotImplementedError
