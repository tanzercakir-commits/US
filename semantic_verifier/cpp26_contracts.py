"""Fail-closed lexical bridge for the controlled C++26 contracts subset."""

from __future__ import annotations

from dataclasses import dataclass
import re


class Cpp26ContractBridgeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Cpp26FunctionContract:
    kind: str
    expression: str
    result_name: str | None
    offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class Cpp26BridgeResult:
    compiler_source: str
    function_contracts: tuple[Cpp26FunctionContract, ...]
    assertion_count: int

    @property
    def changed(self) -> bool:
        return bool(self.function_contracts or self.assertion_count)


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _raw_string_end(source: str, offset: int) -> int | None:
    prefixes = ("u8R\"", "uR\"", "UR\"", "LR\"", "R\"")
    prefix = next((item for item in prefixes if source.startswith(item, offset)), None)
    if prefix is None:
        return None
    if offset > 0 and (source[offset - 1].isalnum() or source[offset - 1] == "_"):
        return None
    delimiter_start = offset + len(prefix)
    delimiter_end = source.find("(", delimiter_start, delimiter_start + 17)
    if delimiter_end < 0:
        return None
    delimiter = source[delimiter_start:delimiter_end]
    if any(char.isspace() or char in "()\\" for char in delimiter):
        return None
    terminator = ")" + delimiter + '"'
    close = source.find(terminator, delimiter_end + 1)
    return len(source) if close < 0 else close + len(terminator)


def _code_mask(source: str) -> tuple[bool, ...]:
    """Mark ordinary C++ source characters, excluding inert lexical regions."""

    mask = [True] * len(source)
    index = 0
    line_prefix = True
    directive = False
    while index < len(source):
        char = source[index]
        if directive:
            mask[index] = False
            if char == "\n":
                previous = index - 1
                if previous >= 0 and source[previous] == "\r":
                    previous -= 1
                directive = previous >= 0 and source[previous] == "\\"
                line_prefix = not directive
            index += 1
            continue

        raw_end = _raw_string_end(source, index)
        if raw_end is not None:
            for position in range(index, raw_end):
                mask[position] = False
                if source[position] == "\n":
                    line_prefix = True
            line_prefix = False
            index = raw_end
            continue

        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = len(source) if end < 0 else end
            for position in range(index, end):
                mask[position] = False
            index = end
            continue

        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = len(source) if end < 0 else end + 2
            for position in range(index, end):
                mask[position] = False
                if source[position] == "\n":
                    line_prefix = True
            index = end
            continue

        if char in {'"', "'"}:
            quote = char
            mask[index] = False
            index += 1
            while index < len(source):
                mask[index] = False
                if source[index] == "\\" and index + 1 < len(source):
                    mask[index + 1] = False
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            line_prefix = False
            continue

        if char == "\n":
            line_prefix = True
        elif line_prefix and char in " \t\r\f\v":
            pass
        elif line_prefix and char == "#":
            mask[index] = False
            directive = True
        else:
            line_prefix = False
        index += 1
    return tuple(mask)


def _next_code(source: str, mask: tuple[bool, ...], offset: int) -> int:
    while offset < len(source):
        if mask[offset] and not source[offset].isspace():
            return offset
        offset += 1
    return len(source)


def _balanced_close(
    source: str, mask: tuple[bool, ...], opening: int, label: str
) -> int:
    depth = 0
    for offset in range(opening, len(source)):
        if not mask[offset]:
            continue
        if source[offset] == "(":
            depth += 1
        elif source[offset] == ")":
            depth -= 1
            if depth == 0:
                return offset
    raise Cpp26ContractBridgeError(f"unterminated {label} predicate")


def _post_parts(
    source: str,
    mask: tuple[bool, ...],
    start: int,
    end: int,
) -> tuple[str | None, str]:
    depth = 0
    colon: int | None = None
    for offset in range(start, end):
        if not mask[offset]:
            continue
        char = source[offset]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif char == ":" and depth == 0:
            colon = offset
            break
    if colon is None:
        expression = source[start:end].strip()
        return None, expression
    result_name = source[start:colon].strip()
    if not _IDENTIFIER.fullmatch(result_name):
        raise Cpp26ContractBridgeError(
            "post result-name introducer must be one identifier"
        )
    expression = source[colon + 1:end].strip()
    return result_name, expression


def _blank_same_bytes(text: str) -> str:
    return "".join(
        char if char in "\r\n" else " " * len(char.encode("utf-8"))
        for char in text
    )


def bridge_cpp26_contracts(source: str) -> Cpp26BridgeResult:
    mask = _code_mask(source)
    contracts: list[Cpp26FunctionContract] = []
    replacements: list[tuple[int, int, str]] = []
    assertion_count = 0
    index = 0
    while index < len(source):
        if not mask[index] or not (source[index].isalpha() or source[index] == "_"):
            index += 1
            continue
        end = index + 1
        while (
            end < len(source)
            and mask[end]
            and (source[end].isalnum() or source[end] == "_")
        ):
            end += 1
        word = source[index:end]
        if word not in {"pre", "post", "contract_assert"}:
            index = end
            continue

        opening = _next_code(source, mask, end)
        if source.startswith("[[", opening):
            raise Cpp26ContractBridgeError(
                f"attributes on {word} are unsupported by the C3.1 bridge"
            )
        if opening >= len(source) or source[opening] != "(":
            index = end
            continue
        closing = _balanced_close(source, mask, opening, word)
        expression_start = opening + 1
        if word == "post":
            result_name, expression = _post_parts(
                source, mask, expression_start, closing
            )
        else:
            result_name = None
            expression = source[expression_start:closing].strip()
        if not expression:
            raise Cpp26ContractBridgeError(f"{word} predicate must not be empty")

        if word == "contract_assert":
            semicolon = _next_code(source, mask, closing + 1)
            if semicolon >= len(source) or source[semicolon] != ";":
                raise Cpp26ContractBridgeError(
                    "contract_assert must end with a semicolon"
                )
            replacement = "assert" + " " * (len(word) - len("assert"))
            replacements.append((index, end, replacement))
            assertion_count += 1
        else:
            contracts.append(
                Cpp26FunctionContract(
                    kind="requires" if word == "pre" else "ensures",
                    expression=expression,
                    result_name=result_name,
                    offset=index,
                    end_offset=closing + 1,
                )
            )
            replacements.append(
                (
                    index,
                    closing + 1,
                    _blank_same_bytes(source[index:closing + 1]),
                )
            )
        index = closing + 1

    if not replacements:
        return Cpp26BridgeResult(source, (), 0)
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(replacements):
        if start < cursor:
            raise Cpp26ContractBridgeError("overlapping C++26 contract syntax")
        pieces.append(source[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(source[cursor:])
    compiler_source = "".join(pieces)
    if len(compiler_source.encode("utf-8")) != len(source.encode("utf-8")):
        raise AssertionError("C++26 bridge changed compiler-source byte length")
    if compiler_source.count("\n") != source.count("\n"):
        raise AssertionError("C++26 bridge changed compiler-source newlines")
    return Cpp26BridgeResult(
        compiler_source,
        tuple(contracts),
        assertion_count,
    )


def expression_identifiers(expression: str) -> frozenset[str]:
    mask = _code_mask(expression)
    names: set[str] = set()
    index = 0
    while index < len(expression):
        if not mask[index] or not (
            expression[index].isalpha() or expression[index] == "_"
        ):
            index += 1
            continue
        end = index + 1
        while (
            end < len(expression)
            and mask[end]
            and (expression[end].isalnum() or expression[end] == "_")
        ):
            end += 1
        previous = index - 1
        while previous >= 0 and expression[previous].isspace():
            previous -= 1
        if previous < 0 or expression[previous] != ".":
            names.add(expression[index:end])
        index = end
    return frozenset(names)


def normalize_result_binding(expression: str, result_name: str) -> str:
    """Rename result-binding identifier tokens without capturing member names."""

    if not _IDENTIFIER.fullmatch(result_name):
        raise Cpp26ContractBridgeError("invalid post result binding")
    mask = _code_mask(expression)
    pieces: list[str] = []
    cursor = 0
    index = 0
    while index < len(expression):
        if not mask[index] or not (
            expression[index].isalpha() or expression[index] == "_"
        ):
            index += 1
            continue
        end = index + 1
        while (
            end < len(expression)
            and mask[end]
            and (expression[end].isalnum() or expression[end] == "_")
        ):
            end += 1
        previous = index - 1
        while previous >= 0 and expression[previous].isspace():
            previous -= 1
        if expression[index:end] == result_name and (
            previous < 0 or expression[previous] != "."
        ):
            pieces.append(expression[cursor:index])
            pieces.append("result")
            cursor = end
        index = end
    pieces.append(expression[cursor:])
    return "".join(pieces)