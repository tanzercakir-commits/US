"""Minimal ReportBuilder trial implementation."""

from .data import DataReader
from .render import Renderer
from .results import EmptyReport, ReadFailure
from .service import ReportService
from .ui import UI

__all__ = [
    "DataReader",
    "EmptyReport",
    "ReadFailure",
    "Renderer",
    "ReportService",
    "UI",
]
