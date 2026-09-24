from __future__ import annotations

from typing import Any


class UI:
    def __init__(self, service: Any) -> None:
        self._service = service

    def build_report(self, query: object) -> object:
        return self._service.build_report(query)
