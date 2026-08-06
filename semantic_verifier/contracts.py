"""Strict parser for the prototype's CodeSkeptic-compatible cs: contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .integer_types import I32, I64, is_signed_integer_type
from .locations import LineMap
from .model import Contract, Expr, SourceLocation


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
    r"(?P<op>==|!=|<=|>=|&&|\|\||[()+\-*/%!<>])|"
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
        left = self._equality()
        while self._peek().text == "&&":
            self._take()
            right = self._equality()
            self._require(left, "bool", "&&")
            self._require(right, "bool", "&&")
            left = Expr.binary("&&", left, right, "bool")
        return left

    def _equality(self) -> Expr:
        left = self._relational()
        while self._peek().text in {"==", "!="}:
            op = self._take().text
            right = self._relational()
            if is_signed_integer_type(left.type) and is_signed_integer_type(right.type):
                left, right, _ = self._signed_pair(left, right, op)
            elif left.type != right.type:
                raise ContractSyntaxError(
                    f"{op} operands have different types: {left.type}, {right.type}"
                )
            left = Expr.binary(op, left, right, "bool")
        return left

    def _relational(self) -> Expr:
        left = self._additive()
        while self._peek().text in {"<", "<=", ">", ">="}:
            op = self._take().text
            right = self._additive()
            left, right, _ = self._signed_pair(left, right, op)
            left = Expr.binary(op, left, right, "bool")
        return left

    def _additive(self) -> Expr:
        left = self._multiplicative()
        while self._peek().text in {"+", "-"}:
            op = self._take().text
            right = self._multiplicative()
            left, right, type_name = self._signed_pair(left, right, op)
            left = Expr.binary(op, left, right, type_name)
        return left

    def _multiplicative(self) -> Expr:
        left = self._unary()
        while self._peek().text in {"*", "/", "%"}:
            op = self._take().text
            right = self._unary()
            left, right, type_name = self._signed_pair(left, right, op)
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
            if not is_signed_integer_type(value.type):
                raise ContractSyntaxError(
                    f"operator '-' requires a signed integer, got {value.type}"
                )
            if (
                value.kind == "constant"
                and value.type == "i64"
                and int(value.value) == 2**31
            ):
                return Expr.integer(I32.minimum, "i32")
            return Expr.unary("-", value, value.type)
        return self._primary()

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
            raise ContractSyntaxError("integer literal is outside i64")
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

    @staticmethod
    def _signed_pair(left: Expr, right: Expr, operator: str) -> tuple[Expr, Expr, str]:
        if not is_signed_integer_type(left.type) or not is_signed_integer_type(right.type):
            raise ContractSyntaxError(
                f"operator {operator!r} requires signed integers, "
                f"got {left.type}, {right.type}"
            )
        type_name = "i64" if "i64" in {left.type, right.type} else "i32"

        def convert(value: Expr) -> Expr:
            if value.type == type_name:
                return value
            if value.kind == "constant":
                return Expr.integer(int(value.value), type_name)
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


def contracts_before(
    source: str,
    function_offset: int,
    line_map: LineMap,
    parameter_types: Mapping[str, str],
    return_type: str,
) -> tuple[tuple[Contract, ...], tuple[ContractIssue, ...]]:
    """Attach the contiguous line-comment block before a declaration."""

    contracts: list[Contract] = []
    issues: list[ContractIssue] = []
    for line_index, text in _comment_block_before(function_offset, line_map):
        if "cs:" not in text:
            continue
        candidate = text.removeprefix("\ufeff") if line_index == 0 else text
        column = text.find("cs:") + 1
        location = SourceLocation(
            line_map.display_path, line_index + 1, max(1, column)
        )
        match = _CONTRACT_LINE.match(candidate)
        if not match:
            issues.append(
                ContractIssue(location, f"unsupported or malformed contract: {text.strip()}")
            )
            continue
        kind = match.group("kind")
        symbols = dict(parameter_types)
        if kind == "ensures":
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
