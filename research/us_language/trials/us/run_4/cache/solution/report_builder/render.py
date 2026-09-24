"""Renderer boundary for report output."""

from collections.abc import Mapping, Sequence
from typing import Any


class Renderer:
    """Base renderer interface used by :class:`ReportService`."""

    def render(self, rows: Sequence[Mapping[str, Any]]) -> object:
        raise NotImplementedError
