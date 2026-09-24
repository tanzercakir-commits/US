"""Renderer interface for report output."""


class Renderer:
    """Interface for objects that render source rows into a report value."""

    def render(self, rows):
        raise NotImplementedError
