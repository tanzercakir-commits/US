"""Data-reader interface for report requests."""


class DataReader:
    """Interface for objects that read source rows for a query."""

    def read(self, query):
        raise NotImplementedError
