"""Owned value-record type identities and concrete replay values."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Iterable

from .array_types import array_type, is_array_type
from .integer_types import integer_type, is_fixed_integer_type


MAX_RECORD_FIELDS = 16
MAX_RECORD_DEPTH = 8
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True, order=True, slots=True)
class RecordField:
    name: str
    type: str

    def __post_init__(self) -> None:
        if _IDENTIFIER.fullmatch(self.name) is None:
            raise ValueError(f"invalid record field name {self.name!r}")
        if not _supported_field_type(self.type):
            raise ValueError(f"unsupported record field type {self.type!r}")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type}


@dataclass(frozen=True, order=True, slots=True)
class RecordType:
    source_name: str
    fields: tuple[RecordField, ...]

    def __post_init__(self) -> None:
        if _IDENTIFIER.fullmatch(self.source_name) is None:
            raise ValueError(f"invalid record name {self.source_name!r}")
        if not 1 <= len(self.fields) <= MAX_RECORD_FIELDS:
            raise ValueError(
                f"record field count must be in [1, {MAX_RECORD_FIELDS}]"
            )
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("record field names must be unique")
        if self.depth > MAX_RECORD_DEPTH:
            raise ValueError(
                f"record nesting depth must not exceed {MAX_RECORD_DEPTH}"
            )

    @property
    def name(self) -> str:
        fields = ",".join(
            f"{field.name}:{field.type}" for field in self.fields
        )
        return f"record<{self.source_name}>{{{fields}}}"

    @property
    def depth(self) -> int:
        nested = [
            record_type(field.type).depth
            for field in self.fields
            if is_record_type(field.type)
        ]
        return 1 + max(nested, default=0)

    def field(self, name: str) -> RecordField:
        for field in self.fields:
            if field.name == name:
                return field
        raise ValueError(
            f"record {self.source_name!r} has no field {name!r}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": [field.to_dict() for field in self.fields],
            "name": self.source_name,
            "type": self.name,
        }


@dataclass(frozen=True, slots=True)
class RecordValue:
    type: str
    fields: tuple[Any, ...]

    def __post_init__(self) -> None:
        profile = record_type(self.type)
        if len(self.fields) != len(profile.fields):
            raise ValueError("record value has the wrong field count")
        if any(
            not _value_matches_type(value, field.type)
            for value, field in zip(self.fields, profile.fields)
        ):
            raise ValueError("record value has a field with the wrong type")


def make_record_type(
    source_name: str, fields: Iterable[tuple[str, str] | RecordField]
) -> str:
    normalized = tuple(
        field if isinstance(field, RecordField) else RecordField(*field)
        for field in fields
    )
    return RecordType(source_name, normalized).name


def is_record_type(type_name: str) -> bool:
    try:
        record_type(type_name)
    except (TypeError, ValueError):
        return False
    return True


def record_type(type_name: str) -> RecordType:
    if not isinstance(type_name, str):
        raise ValueError("record type identity must be text")
    if not type_name.startswith("record<"):
        raise ValueError(f"unsupported record type {type_name!r}")
    name_end = type_name.find(">{", len("record<"))
    if name_end < 0 or not type_name.endswith("}"):
        raise ValueError(f"unsupported record type {type_name!r}")
    source_name = type_name[len("record<") : name_end]
    payload = type_name[name_end + 2 : -1]
    pieces = _split_top_level(payload, ",")
    fields: list[RecordField] = []
    for piece in pieces:
        field_name, separator, field_type = piece.partition(":")
        if not separator or not field_name or not field_type:
            raise ValueError(f"malformed record field {piece!r}")
        fields.append(RecordField(field_name, field_type))
    profile = RecordType(source_name, tuple(fields))
    if profile.name != type_name:
        raise ValueError(f"non-canonical record type {type_name!r}")
    return profile


def record_sort_symbol(type_name: str) -> str:
    record_type(type_name)
    digest = hashlib.sha256(type_name.encode("utf-8")).hexdigest()
    return f"Record_{digest}"


def record_constructor_symbol(type_name: str) -> str:
    return "mk_" + record_sort_symbol(type_name)


def record_selector_symbol(type_name: str, field_name: str) -> str:
    profile = record_type(type_name)
    profile.field(field_name)
    return f"get_{record_sort_symbol(type_name)}_{field_name}"


def _value_matches_type(value: Any, type_name: str) -> bool:
    if type_name == "bool":
        return type(value) is bool
    if is_fixed_integer_type(type_name):
        return type(value) is int and integer_type(type_name).contains(value)
    if is_array_type(type_name):
        profile = array_type(type_name)
        element = integer_type(profile.element_type)
        return (
            isinstance(value, tuple)
            and len(value) == profile.length
            and all(type(item) is int and element.contains(item) for item in value)
        )
    if is_record_type(type_name):
        return isinstance(value, RecordValue) and value.type == type_name
    return False

def _supported_field_type(type_name: str) -> bool:
    return (
        type_name == "bool"
        or is_fixed_integer_type(type_name)
        or is_array_type(type_name)
        or is_record_type(type_name)
    )


def _split_top_level(text: str, separator: str) -> list[str]:
    if not text:
        return []
    result: list[str] = []
    start = 0
    angle_depth = 0
    brace_depth = 0
    for index, character in enumerate(text):
        if character == "<":
            angle_depth += 1
        elif character == ">":
            angle_depth -= 1
        elif character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth -= 1
        elif (
            character == separator
            and angle_depth == 0
            and brace_depth == 0
        ):
            result.append(text[start:index])
            start = index + 1
        if angle_depth < 0 or brace_depth < 0:
            raise ValueError("unbalanced record type identity")
    if angle_depth or brace_depth:
        raise ValueError("unbalanced record type identity")
    result.append(text[start:])
    return result
