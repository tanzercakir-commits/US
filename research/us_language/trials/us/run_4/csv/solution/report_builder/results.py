"""Non-rendered outcomes produced while building a report."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadFailure:
    """A source read failed with an operating-system level error."""

    error: OSError | None = None


@dataclass(frozen=True, slots=True)
class EmptyReport:
    """The source read succeeded but produced no rows."""
