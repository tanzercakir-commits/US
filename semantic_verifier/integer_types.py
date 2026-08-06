"""Owned fixed-width integer identities and pinned C++17 target profile."""

from __future__ import annotations

from dataclasses import dataclass
import re


TARGET_PROFILE_ID = (
    "codeskeptic.cxx17-fixed-integers/"
    "i32-u32-i64-u64-twos-complement-arshift/v0"
)


@dataclass(frozen=True, order=True, slots=True)
class IntegerType:
    """A schema-stable fixed-width integer type identity."""

    name: str
    signed: bool
    width: int

    @property
    def minimum(self) -> int:
        return -(2 ** (self.width - 1)) if self.signed else 0

    @property
    def maximum(self) -> int:
        return (
            2 ** (self.width - 1) - 1
            if self.signed
            else 2**self.width - 1
        )

    def contains(self, value: int) -> bool:
        return type(value) is int and self.minimum <= value <= self.maximum


@dataclass(frozen=True, slots=True)
class IntegerTargetProfile:
    """Implementation choices required by the fixed-width semantics."""

    id: str
    char_bits: int
    arithmetic_signed_right_shift: bool
    twos_complement_signed_narrowing: bool
    types: tuple[IntegerType, ...]


I32 = IntegerType("i32", True, 32)
U32 = IntegerType("u32", False, 32)
I64 = IntegerType("i64", True, 64)
U64 = IntegerType("u64", False, 64)
FIXED_INTEGER_TYPES = {item.name: item for item in (I32, U32, I64, U64)}
TARGET_PROFILE = IntegerTargetProfile(
    id=TARGET_PROFILE_ID,
    char_bits=8,
    arithmetic_signed_right_shift=True,
    twos_complement_signed_narrowing=True,
    types=(I32, U32, I64, U64),
)


TARGET_PROFILE_PROBE = r"""
static_assert(__CHAR_BIT__ == 8, "8-bit bytes required");
static_assert(sizeof(int) * __CHAR_BIT__ == 32, "32-bit int required");
static_assert(sizeof(unsigned int) * __CHAR_BIT__ == 32,
              "32-bit unsigned int required");
static_assert(sizeof(long long) * __CHAR_BIT__ == 64,
              "64-bit long long required");
static_assert(sizeof(unsigned long long) * __CHAR_BIT__ == 64,
              "64-bit unsigned long long required");
static_assert((~0) == -1, "two's-complement 32-bit representation required");
static_assert((~0ll) == -1ll, "two's-complement 64-bit representation required");
static_assert((-1 >> 1) == -1, "arithmetic signed right shift required");
static_assert(static_cast<int>(0xffffffffu) == -1,
              "two's-complement 32-bit signed narrowing required");
static_assert(static_cast<long long>(0xffffffffffffffffull) == -1,
              "two's-complement 64-bit signed narrowing required");
""".strip() + "\n"


_CANONICAL_DECIMAL = re.compile(r"0|-?[1-9][0-9]*\Z")


def is_fixed_integer_type(type_name: str) -> bool:
    return type_name in FIXED_INTEGER_TYPES


def canonical_decimal(value: int) -> str:
    if type(value) is not int:
        raise TypeError("fixed-width integer evidence must be a Python int")
    return str(value)


def parse_canonical_decimal(value: object) -> int:
    if not isinstance(value, str) or _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise ValueError("fixed-width integer evidence is not canonical decimal")
    return int(value)
