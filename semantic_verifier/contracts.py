"""Strict parser for the prototype's CodeSkeptic-compatible cs: contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .array_types import is_array_type
from .cpp26_contracts import (
    Cpp26FunctionContract,
    expression_identifiers,
    normalize_result_binding,
)
from .record_types import is_record_type, record_type
from .integer_types import (
    I32,
    I64,
    U64,
    convert_integer,
    is_fixed_integer_type,
    usual_arithmetic_type,
)
from .locations import LineMap
from .model import (
    Contract,
    Expr,
    FrameContract,
    FrameLocation,
    ReferencePathStep,
    SourceLocation,
)


class ContractSyntaxError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContractIssue:
    location: SourceLocation
    reason: str


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    position: int


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<int>[0-9]+)|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<op>==|!=|<=|>=|<<|>>|&&|\|\||[.()[\]+\-*/%!<>&|^~])|"
    r"(?P<bad>.)"
    r")"
)


class ContractExpressionParser:
    def __init__(self, text: str, symbols: Mapping[str, str]) -> None:
        self.text = text
        self.symbols = dict(symbols)
        self.tokens: list[_Token] = []
        for match in _TOKEN.finditer(text):
            kind = match.lastgroup or "bad"
            token_text = match.group(kind)
            if kind == "bad":
                raise ContractSyntaxError(
                    f"unexpected token {token_text!r} at column {match.start() + 1}"
                )
            self.tokens.append(_Token(kind, token_text, match.start()))
        self.tokens.append(_Token("eof", "", len(text)))
        self.index = 0

    def parse(self) -> Expr:
        result = self._or()
        if self._peek().kind != "eof":
            token = self._peek()
            raise ContractSyntaxError(
                f"unexpected token {token.text!r} at column {token.position + 1}"
            )
        return result

    def _peek(self) -> _Token:
        return self.tokens[self.index]

    def _take(self, text: str | None = None) -> _Token:
        token = self._peek()
        if text is not None and token.text != text:
            raise ContractSyntaxError(
                f"expected {text!r} at column {token.position + 1}"
            )
        self.index += 1
        return token

    def _or(self) -> Expr:
        left = self._and()
        while self._peek().text == "||":
            self._take()
            right = self._and()
            self._require(left, "bool", "||")
            self._require(right, "bool", "||")
            left = Expr.binary("||", left, right, "bool")
        return left

    def _and(self) -> Expr:
        left = self._bitwise_or()
        while self._peek().text == "&&":
            self._take()
            right = self._bitwise_or()
            self._require(left, "bool", "&&")
            self._require(right, "bool", "&&")
            left = Expr.binary("&&", left, right, "bool")
        return left

    def _bitwise_or(self) -> Expr:
        left = self._bitwise_xor()
        while self._peek().text == "|":
            op = self._take().text
            right = self._bitwise_xor()
            left, right, type_name = self._bitwise_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _bitwise_xor(self) -> Expr:
        left = self._bitwise_and()
        while self._peek().text == "^":
            op = self._take().text
            right = self._bitwise_and()
            left, right, type_name = self._bitwise_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _bitwise_and(self) -> Expr:
        left = self._equality()
        while self._peek().text == "&":
            op = self._take().text
            right = self._equality()
            left, right, type_name = self._bitwise_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _equality(self) -> Expr:
        left = self._relational()
        while self._peek().text in {"==", "!="}:
            op = self._take().text
            right = self._relational()
            if (
                is_fixed_integer_type(left.type)
                and is_fixed_integer_type(right.type)
            ):
                left, right, _ = self._integer_pair(left, right, op)
            elif left.type != right.type:
                raise ContractSyntaxError(
                    f"{op} operands have different types: {left.type}, {right.type}"
                )
            left = Expr.binary(op, left, right, "bool")
        return left

    def _relational(self) -> Expr:
        left = self._shift()
        while self._peek().text in {"<", "<=", ">", ">="}:
            op = self._take().text
            right = self._shift()
            left, right, _ = self._integer_pair(left, right, op)
            left = Expr.binary(op, left, right, "bool")
        return left

    def _shift(self) -> Expr:
        left = self._additive()
        while self._peek().text in {"<<", ">>"}:
            op = self._take().text
            right = self._additive()
            left, right, type_name = self._shift_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _additive(self) -> Expr:
        left = self._multiplicative()
        while self._peek().text in {"+", "-"}:
            op = self._take().text
            right = self._multiplicative()
            left, right, type_name = self._integer_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _multiplicative(self) -> Expr:
        left = self._unary()
        while self._peek().text in {"*", "/", "%"}:
            op = self._take().text
            right = self._unary()
            left, right, type_name = self._integer_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _unary(self) -> Expr:
        if self._peek().text == "!":
            self._take()
            value = self._unary()
            self._require(value, "bool", "!")
            return Expr.unary("!", value, "bool")
        if self._peek().text == "-":
            self._take()
            value = self._unary()
            if not is_fixed_integer_type(value.type):
                raise ContractSyntaxError(
                    f"operator '-' requires a fixed-width integer, got {value.type}"
                )
            if (
                value.kind == "constant"
                and value.type == "i64"
                and int(value.value) == 2**31
            ):
                return Expr.integer(I32.minimum, "i32")
            return Expr.unary("-", value, value.type)
        if self._peek().text == "~":
            self._take()
            value = self._promote_integral(self._unary(), "~")
            return Expr.unary("~", value, value.type)
        return self._postfix()

    def _postfix(self) -> Expr:
        value = self._primary()
        while self._peek().text in {"[", "."}:
            if self._peek().text == ".":
                if not is_record_type(value.type):
                    raise ContractSyntaxError(
                        f"member access requires a value record, got {value.type}"
                    )
                self._take(".")
                field = self._peek()
                if field.kind != "ident":
                    raise ContractSyntaxError(
                        f"expected field name at column {field.position + 1}"
                    )
                self._take()
                try:
                    value = Expr.project(value, field.text)
                except ValueError as error:
                    raise ContractSyntaxError(str(error)) from error
                continue
            if not is_array_type(value.type):
                raise ContractSyntaxError(
                    f"subscript requires an owned array, got {value.type}"
                )
            self._take("[")
            index = self._or()
            self._take("]")
            try:
                value = Expr.select(value, index)
            except ValueError as error:
                raise ContractSyntaxError(str(error)) from error
        return value

    def _primary(self) -> Expr:
        token = self._peek()
        if token.text == "(":
            self._take()
            value = self._or()
            self._take(")")
            return value
        if token.kind == "int":
            self._take()
            value = int(token.text)
            if I32.contains(value):
                return Expr.integer(value, "i32")
            if I64.contains(value):
                return Expr.integer(value, "i64")
            if U64.contains(value):
                return Expr.integer(value, "u64")
            raise ContractSyntaxError("integer literal is outside u64")
        if token.kind == "ident":
            self._take()
            if token.text in {"true", "false"}:
                return Expr.boolean(token.text == "true")
            name = "result" if token.text == "return" else token.text
            if name not in self.symbols:
                raise ContractSyntaxError(f"unknown name {token.text!r}")
            return Expr.variable(name, self.symbols[name])
        raise ContractSyntaxError(
            f"expected expression at column {token.position + 1}"
        )

    @classmethod
    def _bitwise_pair(
        cls, left: Expr, right: Expr, operator: str
    ) -> tuple[Expr, Expr, str]:
        return cls._integer_pair(
            cls._promote_integral(left, operator),
            cls._promote_integral(right, operator),
            operator,
        )

    @classmethod
    def _shift_pair(
        cls, left: Expr, right: Expr, operator: str
    ) -> tuple[Expr, Expr, str]:
        promoted_left = cls._promote_integral(left, operator)
        promoted_right = cls._promote_integral(right, operator)
        return promoted_left, promoted_right, promoted_left.type

    @staticmethod
    def _promote_integral(value: Expr, operator: str) -> Expr:
        if value.type == "bool":
            return Expr.cast(value, "i32")
        if is_fixed_integer_type(value.type):
            return value
        raise ContractSyntaxError(
            f"operator {operator!r} requires an integral operand, got {value.type}"
        )

    @staticmethod
    def _integer_pair(
        left: Expr, right: Expr, operator: str
    ) -> tuple[Expr, Expr, str]:
        if (
            not is_fixed_integer_type(left.type)
            or not is_fixed_integer_type(right.type)
        ):
            raise ContractSyntaxError(
                f"operator {operator!r} requires fixed-width integers, "
                f"got {left.type}, {right.type}"
            )
        type_name = usual_arithmetic_type(left.type, right.type)

        def convert(value: Expr) -> Expr:
            if value.type == type_name:
                return value
            if value.kind == "constant":
                return Expr.integer(
                    convert_integer(int(value.value), type_name), type_name
                )
            return Expr.cast(value, type_name)

        return convert(left), convert(right), type_name

    @staticmethod
    def _require(expr: Expr, expected: str, operator: str) -> None:
        if expr.type != expected:
            raise ContractSyntaxError(
                f"operator {operator!r} requires {expected}, got {expr.type}"
            )


def parse_contract_expression(text: str, symbols: Mapping[str, str]) -> Expr:
    return ContractExpressionParser(text, symbols).parse()


_CONTRACT_LINE = re.compile(
    r"^\s*//\s*cs:\s*(?P<ai>ai\s+)?"
    r"(?P<kind>requires|ensures)\s+(?P<expr>.*?)\s*$"
)

_MODIFIES_LINE = re.compile(
    r"^\s*//\s*cs:\s*(?P<ai>ai\s+)?modifies(?:\s+(?P<targets>.*?))?\s*$"
)
_FRAME_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

_INVARIANT_LINE = re.compile(
    r"^\s*//\s*cs:\s*(?P<ai>ai\s+)?"
    r"invariant\s+(?P<expr>.*?)\s*$"
)


def _comment_block_before(
    statement_offset: int, line_map: LineMap
) -> list[tuple[int, str]]:
    """Return the contiguous line-comment block before a source offset."""

    line = line_map.line_index(statement_offset) - 1
    candidates: list[tuple[int, str]] = []
    while line >= 0:
        text = line_map.line_text(line)
        candidate = text.removeprefix("\ufeff") if line == 0 else text
        if not candidate.strip().startswith("//"):
            break
        candidates.append((line, text))
        line -= 1
    candidates.reverse()
    return candidates


def _parse_frame_target(
    text: str,
    parameter_types: Mapping[str, str],
    parameter_modes: Mapping[str, str],
) -> FrameLocation:
    pieces = [piece.strip() for piece in text.split(".")]
    if not pieces or any(_FRAME_IDENTIFIER.fullmatch(piece) is None for piece in pieces):
        raise ContractSyntaxError(f"invalid modifies target {text!r}")
    root = pieces[0]
    if root not in parameter_types:
        raise ContractSyntaxError(f"inaccessible modifies root {root!r}")
    if parameter_modes.get(root, "value") != "mutable_reference":
        raise ContractSyntaxError(
            f"modifies root {root!r} must be a mutable reference parameter"
        )
    current_type = parameter_types[root]
    path: list[ReferencePathStep] = []
    for field_name in pieces[1:]:
        if not is_record_type(current_type):
            raise ContractSyntaxError(
                f"modifies path {text!r} projects through non-record type {current_type!r}"
            )
        try:
            field = record_type(current_type).field(field_name)
        except ValueError as error:
            raise ContractSyntaxError(str(error)) from error
        path.append(ReferencePathStep("field", field_name))
        current_type = field.type
    return FrameLocation(root, tuple(path), current_type)


def contracts_before(
    source: str,
    function_offset: int,
    line_map: LineMap,
    parameter_types: Mapping[str, str],
    return_type: str,
    parameter_modes: Mapping[str, str] | None = None,
) -> tuple[tuple[Contract, ...], FrameContract | None, tuple[ContractIssue, ...]]:
    """Attach the contiguous line-comment contract block before a declaration."""

    del source  # Kept parallel with invariants_before for lowering callers.
    contracts: list[Contract] = []
    frame: FrameContract | None = None
    issues: list[ContractIssue] = []
    modes = parameter_modes or {}
    for line_index, text in _comment_block_before(function_offset, line_map):
        if "cs:" not in text:
            continue
        candidate = text.removeprefix("\ufeff") if line_index == 0 else text
        column = text.find("cs:") + 1
        location = SourceLocation(
            line_map.display_path, line_index + 1, max(1, column)
        )
        modifies_match = _MODIFIES_LINE.match(candidate)
        if modifies_match:
            if frame is not None:
                issues.append(ContractIssue(location, "duplicate cs: modifies contract"))
                continue
            raw_targets = (modifies_match.group("targets") or "").strip()
            target_texts = (
                [piece.strip() for piece in raw_targets.split(",")]
                if raw_targets
                else []
            )
            if any(not piece for piece in target_texts):
                issues.append(ContractIssue(location, "empty modifies target"))
                continue
            try:
                targets = tuple(
                    _parse_frame_target(piece, parameter_types, modes)
                    for piece in target_texts
                )
                for index, target in enumerate(targets):
                    for existing in targets[:index]:
                        if target.root != existing.root:
                            continue
                        target_path = tuple(step.value for step in target.path)
                        existing_path = tuple(step.value for step in existing.path)
                        common = min(len(target_path), len(existing_path))
                        if target_path[:common] == existing_path[:common]:
                            raise ContractSyntaxError(
                                "duplicate or overlapping modifies targets are unsupported"
                            )
            except ContractSyntaxError as error:
                issues.append(ContractIssue(location, str(error)))
                continue
            canonical = ", ".join(target_texts)
            frame = FrameContract(
                targets=targets,
                location=location,
                text=f"modifies {canonical}".rstrip(),
                machine_proposed=bool(modifies_match.group("ai")),
            )
            continue
        match = _CONTRACT_LINE.match(candidate)
        if not match:
            issues.append(
                ContractIssue(location, f"unsupported or malformed contract: {text.strip()}")
            )
            continue
        kind = match.group("kind")
        symbols = dict(parameter_types)
        if kind == "ensures" and return_type != "void":
            symbols["result"] = return_type
        expression_text = match.group("expr")
        try:
            expression = parse_contract_expression(expression_text, symbols)
            if expression.type != "bool":
                raise ContractSyntaxError("contract expression must be boolean")
        except ContractSyntaxError as error:
            issues.append(ContractIssue(location, str(error)))
            continue
        contracts.append(
            Contract(
                kind=kind,
                expression=expression,
                location=location,
                text=f"{kind} {expression_text}",
                machine_proposed=bool(match.group("ai")),
            )
        )
    return tuple(contracts), frame, tuple(issues)

def contracts_from_cpp26(
    specs: tuple[Cpp26FunctionContract, ...],
    line_map: LineMap,
    parameter_types: Mapping[str, str],
    return_type: str,
    parameter_modes: Mapping[str, str],
    const_value_parameters: frozenset[str],
) -> tuple[tuple[Contract, ...], tuple[ContractIssue, ...]]:
    """Lower extracted C++26 function contracts through the owned parser."""

    contracts: list[Contract] = []
    issues: list[ContractIssue] = []
    for spec in specs:
        location = line_map.location(spec.offset)
        expression_text = spec.expression
        symbols = dict(parameter_types)
        if spec.kind == "ensures" and spec.result_name is not None:
            if return_type == "void":
                issues.append(
                    ContractIssue(
                        location,
                        "a void function postcondition cannot bind a result",
                    )
                )
                continue
            if spec.result_name in parameter_types:
                issues.append(
                    ContractIssue(
                        location,
                        "post result binding conflicts with a parameter name",
                    )
                )
                continue
            expression_text = normalize_result_binding(
                expression_text, spec.result_name
            )
            symbols["result"] = return_type
        referenced = expression_identifiers(spec.expression)
        mutable_values = sorted(
            name
            for name, mode in parameter_modes.items()
            if mode == "value"
            and name not in const_value_parameters
            and name in referenced
            and spec.kind == "ensures"
        )
        if mutable_values:
            issues.append(
                ContractIssue(
                    location,
                    "C++26 postcondition odr-uses non-const value parameter(s): "
                    + ", ".join(mutable_values),
                )
            )
            continue
        try:
            expression = parse_contract_expression(expression_text, symbols)
            if expression.type != "bool":
                raise ContractSyntaxError("contract expression must be boolean")
        except ContractSyntaxError as error:
            issues.append(ContractIssue(location, str(error)))
            continue
        contracts.append(
            Contract(
                kind=spec.kind,
                expression=expression,
                location=location,
                text=f"{spec.kind} {expression_text}",
                machine_proposed=False,
            )
        )
    return tuple(contracts), tuple(issues)


def invariants_before(
    source: str,
    statement_offset: int,
    line_map: LineMap,
    symbol_types: Mapping[str, str],
    statement_kind: str,
) -> tuple[tuple[Contract, ...], tuple[ContractIssue, ...]]:
    """Parse a contiguous invariant block attached only to a WhileStmt."""

    del source  # Kept parallel with contracts_before for lowering callers.
    invariants: list[Contract] = []
    issues: list[ContractIssue] = []
    for line_index, text in _comment_block_before(statement_offset, line_map):
        if "cs:" not in text:
            continue
        candidate = text.removeprefix("\ufeff") if line_index == 0 else text
        column = text.find("cs:") + 1
        location = SourceLocation(
            line_map.display_path, line_index + 1, max(1, column)
        )
        match = _INVARIANT_LINE.match(candidate)
        if not match:
            issues.append(
                ContractIssue(
                    location,
                    f"unsupported or malformed loop invariant: {text.strip()}",
                )
            )
            continue
        if statement_kind != "WhileStmt":
            issues.append(
                ContractIssue(
                    location,
                    "cs: invariant may only be attached to a while statement",
                )
            )
            continue
        expression_text = match.group("expr")
        try:
            expression = parse_contract_expression(expression_text, symbol_types)
            if expression.type != "bool":
                raise ContractSyntaxError("invariant expression must be boolean")
        except ContractSyntaxError as error:
            issues.append(ContractIssue(location, str(error)))
            continue
        invariants.append(
            Contract(
                kind="invariant",
                expression=expression,
                location=location,
                text=f"invariant {expression_text}",
                machine_proposed=bool(match.group("ai")),
            )
        )
    return tuple(invariants), tuple(issues)
