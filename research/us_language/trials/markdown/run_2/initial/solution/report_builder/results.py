"""Observable outcomes for report construction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """Outcome returned when the source reader raises ``OSError``."""

    error: OSError


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """Outcome returned when a successful read contains no rows."""
