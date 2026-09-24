"""Observable non-success report outcomes."""


class ReadFailure:
    """Outcome returned when the reader raises ``OSError``."""

    __slots__ = ()


class EmptyReport:
    """Outcome returned when a successful read contains no rows."""

    __slots__ = ()
