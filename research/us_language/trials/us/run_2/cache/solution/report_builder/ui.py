class UI:
    def __init__(self, service):
        self._service = service

    def build_report(self, query):
        return self._service.build_report(query)
