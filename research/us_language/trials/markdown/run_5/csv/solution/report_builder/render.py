"""Renderer boundary for report output."""


class Renderer:
    """Interface for objects that render mapping-like report rows."""

    def render(self, rows):
        raise NotImplementedError
