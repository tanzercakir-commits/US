"""Reader interface for ReportBuilder."""


class DataReader:
    """Base reader interface used by :class:`ReportService`."""

    def read(self, query):
        """Return source rows for *query* or raise ``OSError`` on read failure."""
        raise NotImplementedError
