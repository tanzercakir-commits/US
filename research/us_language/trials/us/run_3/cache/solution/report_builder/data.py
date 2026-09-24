"""Data-reading interface used by ReportService."""


class DataReader:
    """Interface for objects that read source records for a query."""

    def read(self, query):
        raise NotImplementedError
