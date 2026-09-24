class Renderer:
    """Interface for rendering non-empty report rows."""

    def render(self, rows):
        raise NotImplementedError
