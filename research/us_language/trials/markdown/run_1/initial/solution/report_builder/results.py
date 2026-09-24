"""Observable non-report outcomes."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """The source rows could not be read."""


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """The source read succeeded but produced no rows."""
