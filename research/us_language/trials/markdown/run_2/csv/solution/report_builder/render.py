"""Rendering interface for ReportBuilder."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class Renderer:
    """Base interface for objects that render source rows."""

    def render(self, rows: Sequence[Mapping[str, Any]]) -> Any:
        raise NotImplementedError
