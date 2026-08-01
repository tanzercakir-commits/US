"""Source-offset to stable file/line/column mapping."""

from __future__ import annotations

from bisect import bisect_right

from .model import SourceLocation


class LineMap:
    def __init__(self, source: str, display_path: str) -> None:
        self.source = source
        self.display_path = display_path.replace("\\", "/")
        self.starts = [0]
        self.byte_starts = [0]
        byte_offset = 0
        for index, char in enumerate(source):
            byte_offset += len(char.encode("utf-8"))
            self.byte_starts.append(byte_offset)
            if char == "\n":
                self.starts.append(index + 1)

    @property
    def byte_length(self) -> int:
        return self.byte_starts[-1]

    def char_offset_from_byte_offset(self, byte_offset: int) -> int:
        """Translate a Clang UTF-8 byte offset to a Python string offset."""

        clamped = max(0, min(byte_offset, self.byte_length))
        return bisect_right(self.byte_starts, clamped) - 1

    def location_from_byte_offset(self, byte_offset: int) -> SourceLocation:
        return self.location(self.char_offset_from_byte_offset(byte_offset))

    def location(self, offset: int) -> SourceLocation:
        offset = max(0, min(offset, len(self.source)))
        line_index = bisect_right(self.starts, offset) - 1
        return SourceLocation(
            self.display_path,
            line_index + 1,
            offset - self.starts[line_index] + 1,
        )

    def line_index(self, offset: int) -> int:
        return bisect_right(self.starts, max(0, offset)) - 1

    def line_text(self, zero_based_line: int) -> str:
        if zero_based_line < 0 or zero_based_line >= len(self.starts):
            return ""
        start = self.starts[zero_based_line]
        end = (
            self.starts[zero_based_line + 1]
            if zero_based_line + 1 < len(self.starts)
            else len(self.source)
        )
        return self.source[start:end].rstrip("\r\n")
