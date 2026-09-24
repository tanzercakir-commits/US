"""Renderer interface for ReportBuilder."""


class Renderer:
    """Base renderer interface used by :class:`ReportService`."""

    def render(self, rows):
        """Render non-empty source rows and return an opaque report value."""
        raise NotImplementedError
