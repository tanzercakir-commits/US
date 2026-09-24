"""Report-building orchestration."""

import csv
from copy import deepcopy
from io import StringIO

from .results import EmptyReport, ReadFailure


class ReportService:
    """Read source rows and build a report without mutating source data."""

    def __init__(self, reader: object, renderer: object) -> None:
        self._reader = reader
        self._renderer = renderer

    def build_report(self, query: object, *, output_format: str = "default") -> object:
        try:
            source_rows = self._reader.read(query)  # type: ignore[attr-defined]
        except OSError as exc:
            return ReadFailure(exc)

        rows = tuple(deepcopy(dict(row)) for row in source_rows)
        if not rows:
            return EmptyReport()

        if output_format == "default":
            return self._renderer.render(rows)  # type: ignore[attr-defined]
        if output_format == "csv":
            return _build_csv(rows)
        raise ValueError(f"unsupported output_format: {output_format!r}")


def _build_csv(rows: tuple[dict[object, object], ...]) -> str:
    columns = sorted({key for row in rows for key in row})
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
