from dataclasses import dataclass


@dataclass(frozen=True)
class ReadFailure:
    error: OSError


@dataclass(frozen=True)
class EmptyReport:
    pass
