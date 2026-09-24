from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class Renderer:
    """Base interface for report renderers."""

    def render(self, rows: Sequence[Mapping[str, Any]]) -> object:
        raise NotImplementedError
