"""Reader interface for report source data."""


class DataReader:
    """Base reader interface used by ReportService."""

    def read(self, query):
        raise NotImplementedError
