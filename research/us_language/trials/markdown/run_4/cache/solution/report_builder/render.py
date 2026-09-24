class Renderer:
    """Report-renderer interface used by ReportService."""

    def render(self, rows):
        raise NotImplementedError
