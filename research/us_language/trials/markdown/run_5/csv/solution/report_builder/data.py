"""Reader boundary for report source records."""


class DataReader:
    """Interface for objects that read source rows for a report query."""

    def read(self, query: object):
        raise NotImplementedError
