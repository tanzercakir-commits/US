class DataReader:
    """Source-reader interface used by ReportService."""

    def read(self, query):
        raise NotImplementedError
