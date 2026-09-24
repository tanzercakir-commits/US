class ReadFailure:
    """Outcome returned when the data reader raises OSError."""

    def __init__(self, error=None):
        self.error = error


class EmptyReport:
    """Outcome returned when a successful read contains no rows."""
