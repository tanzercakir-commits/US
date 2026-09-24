"""Reader boundary for report source records."""

from collections.abc import Mapping, Sequence
from typing import Any


class DataReader:
    """Base reader interface used by :class:`ReportService`."""

    def read(self, query: object) -> Sequence[Mapping[str, Any]]:
        raise NotImplementedError
