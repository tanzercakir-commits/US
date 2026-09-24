class DataReader:
    """Interface for report source readers."""

    def read(self, query):
        raise NotImplementedError
