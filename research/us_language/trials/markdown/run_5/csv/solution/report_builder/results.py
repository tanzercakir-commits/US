"""Observable non-rendered report outcomes."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """Outcome returned when the reader raises OSError."""

    error: OSError


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """Outcome returned after a successful read with no rows."""
