from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class DataReader:
    """Base interface for report data sources."""

    def read(self, query: object) -> Sequence[Mapping[str, Any]]:
        raise NotImplementedError
