from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """Outcome returned when the reader cannot complete a report request."""

    error: OSError


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """Outcome returned when a successful read contains no rows."""
