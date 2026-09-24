"""Source-reading interface for ReportBuilder."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class DataReader:
    """Base interface for objects that read source rows."""

    def read(self, query: Any) -> Sequence[Mapping[str, Any]]:
        raise NotImplementedError
