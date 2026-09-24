"""Non-rendered report outcomes."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """Result returned when the data reader raises OSError."""

    error: OSError | None = None


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """Result returned when a successful read contains no rows."""
