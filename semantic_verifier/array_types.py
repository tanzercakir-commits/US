"""Owned fixed-size array type identities for the reviewed A6.2 subset."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .integer_types import is_fixed_integer_type


MAX_ARRAY_ELEMENTS = 64
_ARRAY_TYPE = re.compile(r"array<(?P<element>[a-z0-9]+),(?P<length>[1-9][0-9]*)>\Z")
_SOURCE_ARRAY = re.compile(
    r"(?P<element>bool|int|unsigned int|long long|unsigned long long)"
    r"\s*\[(?P<length>[0-9]+)\]\Z"
)


@dataclass(frozen=True, order=True, slots=True)
class ArrayType:
    element_type: str
    length: int

    def __post_init__(self) -> None:
        if not is_fixed_integer_type(self.element_type):
            raise ValueError(
                f"unsupported array element type {self.element_type!r}"
            )
        if not 1 <= self.length <= MAX_ARRAY_ELEMENTS:
            raise ValueError(
                f"array length must be in [1, {MAX_ARRAY_ELEMENTS}]"
            )

    @property
    def name(self) -> str:
        return f"array<{self.element_type},{self.length}>"


def make_array_type(element_type: str, length: int) -> str:
    return ArrayType(element_type, length).name


def is_array_type(type_name: str) -> bool:
    try:
        array_type(type_name)
    except ValueError:
        return False
    return True


def array_type(type_name: str) -> ArrayType:
    if not isinstance(type_name, str):
        raise ValueError("array type identity must be text")
    match = _ARRAY_TYPE.fullmatch(type_name)
    if match is None:
        raise ValueError(f"unsupported array type {type_name!r}")
    return ArrayType(match.group("element"), int(match.group("length")))


def parse_source_array_type(
    source_type: str, source_element_types: dict[str, str]
) -> ArrayType | None:
    match = _SOURCE_ARRAY.fullmatch(source_type)
    if match is None:
        if "[" not in source_type and "]" not in source_type:
            return None
        raise ValueError(f"unsupported source array type {source_type!r}")
    element = source_element_types.get(match.group("element"))
    if element is None or not is_fixed_integer_type(element):
        raise ValueError(
            f"unsupported array element type {match.group('element')!r}"
        )
    return ArrayType(element, int(match.group("length")))
