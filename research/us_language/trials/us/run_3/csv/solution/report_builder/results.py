"""Non-rendered outcomes returned by ReportService."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadFailure:
    """A report request whose source read raised OSError."""

    error: OSError


@dataclass(frozen=True)
class EmptyReport:
    """A successful read that produced no rows."""
