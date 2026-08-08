"""Deterministic, fail-closed world-model fact index."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


FACT_SCHEMA = "codeskeptic.fact-index/v1"
FACT_ID_SCHEMA = "codeskeptic.fact-identity/v1"

SYMBOL_KINDS = frozenset({"field", "function", "parameter", "record", "variable"})
LINKAGES = frozenset({"external", "internal", "none"})
DEFINITION_KINDS = frozenset(
    {"assignment", "declaration", "definition", "initialization", "parameter"}
)
USE_KINDS = frozenset({"address", "read", "read_write", "write"})
CALL_KINDS = frozenset({"direct"})
MUTATION_KINDS = frozenset(
    {
        "assignment",
        "call_effect",
        "compound_assignment",
        "decrement",
        "increment",
        "initialization",
    }
)
PURITY_STATUSES = frozenset({"impure", "pure", "unknown"})
PURITY_REASONS = frozenset(
    {
        "direct_impure_call",
        "global_mutation",
        "indirect_call",
        "parameter_mutation",
        "unresolved_call",
        "unsupported_construct",
        "virtual_dispatch",
    }
)
LIMITATION_CODES = frozenset(
    {
        "indirect_call",
        "macro_location",
        "unsupported_ast",
        "unresolved_symbol",
        "virtual_dispatch",
    }
)

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class FactIndexError(ValueError):
    """Raised when fact-index data violates the v1 contract."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        + "\n"
    )


def _canonical_identity_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, payload: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": FACT_ID_SCHEMA,
        "value": payload,
    }
    digest = hashlib.sha256(_canonical_identity_bytes(envelope)).hexdigest()
    return f"sha256:{digest}"


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise FactIndexError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_PATTERN.fullmatch(text) is None:
        raise FactIndexError(f"{field} must be a lowercase sha256 identity")
    return text


def _require_choice(
    value: object,
    choices: frozenset[str],
    field: str,
) -> str:
    text = _require_text(value, field)
    if text not in choices:
        raise FactIndexError(f"{field} has unsupported value {text!r}")
    return text


def _normalize_file(value: object, field: str) -> str:
    text = _require_text(value, field).replace(chr(92), "/")
    if text.startswith("./"):
        text = text[2:]
    if not text or "//" in text:
        raise FactIndexError(f"{field} must be a normalized source path")
    return text


@dataclass(frozen=True, order=True, slots=True)
class FactLocation:
    file: str
    line: int
    column: int

    def __post_init__(self) -> None:
        normalized = _normalize_file(self.file, "location.file")
        if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1:
            raise FactIndexError("location.line must be a positive integer")
        if (
            isinstance(self.column, bool)
            or not isinstance(self.column, int)
            or self.column < 1
        ):
            raise FactIndexError("location.column must be a positive integer")
        object.__setattr__(self, "file", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "column": self.column,
            "file": self.file,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class FactSource:
    file: str
    language: str
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "file", _normalize_file(self.file, "source.file"))
        if self.language != "c++17":
            raise FactIndexError("source.language must be 'c++17'")
        _require_hash(self.content_sha256, "source.content_sha256")

    @classmethod
    def from_text(cls, file: str, source: str) -> "FactSource":
        if not isinstance(source, str):
            raise FactIndexError("source text must be text")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return cls(file, "c++17", f"sha256:{digest}")

    def to_dict(self) -> dict[str, str]:
        return {
            "content_sha256": self.content_sha256,
            "file": self.file,
            "language": self.language,
        }


@dataclass(frozen=True, slots=True)
class FactSymbol:
    id: str
    kind: str
    name: str
    qualified_name: str
    type: str
    linkage: str
    owner: str | None
    declaration: FactLocation
    definition: FactLocation | None

    def __post_init__(self) -> None:
        _require_hash(self.id, "symbol.id")
        _require_choice(self.kind, SYMBOL_KINDS, "symbol.kind")
        _require_text(self.name, "symbol.name")
        _require_text(self.qualified_name, "symbol.qualified_name")
        _require_text(self.type, "symbol.type")
        _require_choice(self.linkage, LINKAGES, "symbol.linkage")
        if self.owner is not None:
            _require_hash(self.owner, "symbol.owner")
        expected = _content_id("symbol", self.identity_dict())
        if self.id != expected:
            raise FactIndexError("symbol.id does not match its canonical fields")

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        name: str,
        qualified_name: str,
        type: str,
        linkage: str,
        owner: str | None,
        declaration: FactLocation,
        definition: FactLocation | None = None,
    ) -> "FactSymbol":
        fields = {
            "declaration": declaration.to_dict(),
            "definition": definition.to_dict() if definition is not None else None,
            "kind": kind,
            "linkage": linkage,
            "name": name,
            "owner": owner,
            "qualified_name": qualified_name,
            "type": type,
        }
        return cls(
            _content_id("symbol", fields),
            kind,
            name,
            qualified_name,
            type,
            linkage,
            owner,
            declaration,
            definition,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "declaration": self.declaration.to_dict(),
            "definition": (
                self.definition.to_dict() if self.definition is not None else None
            ),
            "kind": self.kind,
            "linkage": self.linkage,
            "name": self.name,
            "owner": self.owner,
            "qualified_name": self.qualified_name,
            "type": self.type,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}

@dataclass(frozen=True, slots=True)
class DefinitionFact:
    id: str
    symbol: str
    context: str | None
    kind: str
    location: FactLocation

    def __post_init__(self) -> None:
        _require_hash(self.id, "definition.id")
        _require_hash(self.symbol, "definition.symbol")
        if self.context is not None:
            _require_hash(self.context, "definition.context")
        _require_choice(self.kind, DEFINITION_KINDS, "definition.kind")
        if self.id != _content_id("definition", self.identity_dict()):
            raise FactIndexError("definition.id does not match its canonical fields")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        context: str | None,
        kind: str,
        location: FactLocation,
    ) -> "DefinitionFact":
        fields = {
            "context": context,
            "kind": kind,
            "location": location.to_dict(),
            "symbol": symbol,
        }
        return cls(_content_id("definition", fields), symbol, context, kind, location)

    def identity_dict(self) -> dict[str, object]:
        return {
            "context": self.context,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "symbol": self.symbol,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, slots=True)
class UseFact:
    id: str
    symbol: str
    context: str
    kind: str
    location: FactLocation

    def __post_init__(self) -> None:
        _require_hash(self.id, "use.id")
        _require_hash(self.symbol, "use.symbol")
        _require_hash(self.context, "use.context")
        _require_choice(self.kind, USE_KINDS, "use.kind")
        if self.id != _content_id("use", self.identity_dict()):
            raise FactIndexError("use.id does not match its canonical fields")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        context: str,
        kind: str,
        location: FactLocation,
    ) -> "UseFact":
        fields = {
            "context": context,
            "kind": kind,
            "location": location.to_dict(),
            "symbol": symbol,
        }
        return cls(_content_id("use", fields), symbol, context, kind, location)

    def identity_dict(self) -> dict[str, object]:
        return {
            "context": self.context,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "symbol": self.symbol,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, slots=True)
class CallFact:
    id: str
    caller: str
    callee: str
    kind: str
    location: FactLocation

    def __post_init__(self) -> None:
        _require_hash(self.id, "call.id")
        _require_hash(self.caller, "call.caller")
        _require_hash(self.callee, "call.callee")
        _require_choice(self.kind, CALL_KINDS, "call.kind")
        if self.id != _content_id("call", self.identity_dict()):
            raise FactIndexError("call.id does not match its canonical fields")

    @classmethod
    def create(
        cls,
        *,
        caller: str,
        callee: str,
        kind: str,
        location: FactLocation,
    ) -> "CallFact":
        fields = {
            "callee": callee,
            "caller": caller,
            "kind": kind,
            "location": location.to_dict(),
        }
        return cls(_content_id("call", fields), caller, callee, kind, location)

    def identity_dict(self) -> dict[str, object]:
        return {
            "callee": self.callee,
            "caller": self.caller,
            "kind": self.kind,
            "location": self.location.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, slots=True)
class MutationFact:
    id: str
    context: str
    target: str
    kind: str
    location: FactLocation

    def __post_init__(self) -> None:
        _require_hash(self.id, "mutation.id")
        _require_hash(self.context, "mutation.context")
        _require_hash(self.target, "mutation.target")
        _require_choice(self.kind, MUTATION_KINDS, "mutation.kind")
        if self.id != _content_id("mutation", self.identity_dict()):
            raise FactIndexError("mutation.id does not match its canonical fields")

    @classmethod
    def create(
        cls,
        *,
        context: str,
        target: str,
        kind: str,
        location: FactLocation,
    ) -> "MutationFact":
        fields = {
            "context": context,
            "kind": kind,
            "location": location.to_dict(),
            "target": target,
        }
        return cls(_content_id("mutation", fields), context, target, kind, location)

    def identity_dict(self) -> dict[str, object]:
        return {
            "context": self.context,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "target": self.target,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, slots=True)
class PurityFact:
    function: str
    status: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_hash(self.function, "purity.function")
        _require_choice(self.status, PURITY_STATUSES, "purity.status")
        normalized = tuple(sorted(self.reasons))
        if len(normalized) != len(set(normalized)):
            raise FactIndexError("purity.reasons must not contain duplicates")
        for reason in normalized:
            _require_choice(reason, PURITY_REASONS, "purity.reason")
        if self.status == "pure" and normalized:
            raise FactIndexError("pure functions cannot carry impurity reasons")
        if self.status != "pure" and not normalized:
            raise FactIndexError("impure/unknown functions require a reason")
        object.__setattr__(self, "reasons", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "reasons": list(self.reasons),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class FactLimitation:
    code: str
    message: str
    context: str | None = None
    location: FactLocation | None = None

    def __post_init__(self) -> None:
        _require_choice(self.code, LIMITATION_CODES, "limitation.code")
        _require_text(self.message, "limitation.message")
        if self.context is not None:
            _require_hash(self.context, "limitation.context")

    def sort_key(self) -> tuple[object, ...]:
        location = self.location
        return (
            self.code,
            self.context or "",
            location.file if location is not None else "",
            location.line if location is not None else 0,
            location.column if location is not None else 0,
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "context": self.context,
            "location": self.location.to_dict() if self.location is not None else None,
            "message": self.message,
        }

@dataclass(frozen=True, slots=True)
class FactIndex:
    id: str
    source: FactSource
    symbols: tuple[FactSymbol, ...]
    definitions: tuple[DefinitionFact, ...]
    uses: tuple[UseFact, ...]
    calls: tuple[CallFact, ...]
    mutations: tuple[MutationFact, ...]
    purity: tuple[PurityFact, ...]
    limitations: tuple[FactLimitation, ...]

    def __post_init__(self) -> None:
        _require_hash(self.id, "index.id")
        object.__setattr__(
            self, "symbols", tuple(sorted(self.symbols, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "definitions",
            tuple(sorted(self.definitions, key=lambda item: item.id)),
        )
        object.__setattr__(
            self, "uses", tuple(sorted(self.uses, key=lambda item: item.id))
        )
        object.__setattr__(
            self, "calls", tuple(sorted(self.calls, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "mutations",
            tuple(sorted(self.mutations, key=lambda item: item.id)),
        )
        object.__setattr__(
            self,
            "purity",
            tuple(sorted(self.purity, key=lambda item: item.function)),
        )
        object.__setattr__(
            self,
            "limitations",
            tuple(sorted(self.limitations, key=lambda item: item.sort_key())),
        )
        self._validate_graph()
        expected = _content_id("fact-index", self.content_dict())
        if self.id != expected:
            raise FactIndexError("index.id does not match canonical index content")

    @classmethod
    def create(
        cls,
        *,
        source: FactSource,
        symbols: Sequence[FactSymbol] = (),
        definitions: Sequence[DefinitionFact] = (),
        uses: Sequence[UseFact] = (),
        calls: Sequence[CallFact] = (),
        mutations: Sequence[MutationFact] = (),
        purity: Sequence[PurityFact] = (),
        limitations: Sequence[FactLimitation] = (),
    ) -> "FactIndex":
        ordered_symbols = tuple(sorted(symbols, key=lambda item: item.id))
        ordered_definitions = tuple(sorted(definitions, key=lambda item: item.id))
        ordered_uses = tuple(sorted(uses, key=lambda item: item.id))
        ordered_calls = tuple(sorted(calls, key=lambda item: item.id))
        ordered_mutations = tuple(sorted(mutations, key=lambda item: item.id))
        ordered_purity = tuple(sorted(purity, key=lambda item: item.function))
        ordered_limitations = tuple(
            sorted(limitations, key=lambda item: item.sort_key())
        )
        content = {
            "calls": [fact.to_dict() for fact in ordered_calls],
            "definitions": [fact.to_dict() for fact in ordered_definitions],
            "limitations": [fact.to_dict() for fact in ordered_limitations],
            "mutations": [fact.to_dict() for fact in ordered_mutations],
            "purity": [fact.to_dict() for fact in ordered_purity],
            "schema": FACT_SCHEMA,
            "source": source.to_dict(),
            "symbols": [fact.to_dict() for fact in ordered_symbols],
            "uses": [fact.to_dict() for fact in ordered_uses],
        }
        return cls(
            _content_id("fact-index", content),
            source,
            ordered_symbols,
            ordered_definitions,
            ordered_uses,
            ordered_calls,
            ordered_mutations,
            ordered_purity,
            ordered_limitations,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "calls": [fact.to_dict() for fact in self.calls],
            "definitions": [fact.to_dict() for fact in self.definitions],
            "limitations": [fact.to_dict() for fact in self.limitations],
            "mutations": [fact.to_dict() for fact in self.mutations],
            "purity": [fact.to_dict() for fact in self.purity],
            "schema": FACT_SCHEMA,
            "source": self.source.to_dict(),
            "symbols": [fact.to_dict() for fact in self.symbols],
            "uses": [fact.to_dict() for fact in self.uses],
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def _validate_graph(self) -> None:
        symbol_ids = [symbol.id for symbol in self.symbols]
        _reject_duplicates(symbol_ids, "symbols")
        _reject_duplicates([fact.id for fact in self.definitions], "definitions")
        _reject_duplicates([fact.id for fact in self.uses], "uses")
        _reject_duplicates([fact.id for fact in self.calls], "calls")
        _reject_duplicates([fact.id for fact in self.mutations], "mutations")
        _reject_duplicates(
            [fact.sort_key() for fact in self.limitations], "limitations"
        )

        symbols = {symbol.id: symbol for symbol in self.symbols}
        function_ids = {
            symbol.id for symbol in self.symbols if symbol.kind == "function"
        }
        record_ids = {
            symbol.id for symbol in self.symbols if symbol.kind == "record"
        }

        for symbol in self.symbols:
            if symbol.declaration.file != self.source.file:
                raise FactIndexError(
                    "symbol declaration must belong to source.file"
                )
            if (
                symbol.definition is not None
                and symbol.definition.file != self.source.file
            ):
                raise FactIndexError(
                    "symbol definition must belong to source.file"
                )
            if symbol.owner is not None and symbol.owner not in symbols:
                raise FactIndexError("symbol.owner is dangling")
            if symbol.kind == "parameter":
                if symbol.owner not in function_ids:
                    raise FactIndexError("parameter owner must be a function")
                if symbol.linkage != "none":
                    raise FactIndexError("parameter linkage must be none")
            elif symbol.kind == "field":
                if symbol.owner not in record_ids:
                    raise FactIndexError("field owner must be a record")
                if symbol.linkage != "none":
                    raise FactIndexError("field linkage must be none")
            elif symbol.kind == "variable" and symbol.owner is not None:
                if symbol.owner not in function_ids:
                    raise FactIndexError(
                        "local variable owner must be a function"
                    )
                if symbol.linkage != "none":
                    raise FactIndexError(
                        "local variable linkage must be none"
                    )
            elif (
                symbol.kind in {"function", "record"}
                and symbol.owner is not None
            ):
                raise FactIndexError(
                    f"{symbol.kind} owner is unsupported in v1"
                )

        for fact in self.definitions:
            self._require_location(fact.location)
            self._require_symbol(fact.symbol, symbols, "definition.symbol")
            if fact.context is not None:
                self._require_symbol(
                    fact.context, symbols, "definition.context"
                )
                if fact.context not in function_ids:
                    raise FactIndexError(
                        "definition.context must be a function"
                    )
            owner = symbols[fact.symbol].owner
            if owner in function_ids and fact.context != owner:
                raise FactIndexError(
                    "local definition context must match symbol owner"
                )

        for fact in self.uses:
            self._require_location(fact.location)
            self._require_symbol(fact.symbol, symbols, "use.symbol")
            if fact.context not in function_ids:
                raise FactIndexError("use.context must be a function")

        for fact in self.calls:
            self._require_location(fact.location)
            if (
                fact.caller not in function_ids
                or fact.callee not in function_ids
            ):
                raise FactIndexError("call endpoints must be functions")

        mutable_kinds = {"field", "parameter", "variable"}
        for fact in self.mutations:
            self._require_location(fact.location)
            if fact.context not in function_ids:
                raise FactIndexError(
                    "mutation.context must be a function"
                )
            self._require_symbol(fact.target, symbols, "mutation.target")
            if symbols[fact.target].kind not in mutable_kinds:
                raise FactIndexError(
                    "mutation.target must be mutable storage"
                )

        purity_functions = [fact.function for fact in self.purity]
        _reject_duplicates(purity_functions, "purity")
        if set(purity_functions) != function_ids:
            raise FactIndexError(
                "purity must contain exactly one row per function"
            )

        for fact in self.limitations:
            if fact.context is not None and fact.context not in symbols:
                raise FactIndexError("limitation.context is dangling")
            if fact.location is not None:
                self._require_location(fact.location)

    def _require_location(self, location: FactLocation) -> None:
        if location.file != self.source.file:
            raise FactIndexError(
                "fact location must belong to source.file"
            )

    @staticmethod
    def _require_symbol(
        identity: str,
        symbols: Mapping[str, FactSymbol],
        field: str,
    ) -> None:
        if identity not in symbols:
            raise FactIndexError(f"{field} is dangling")


def _reject_duplicates(values: Sequence[object], field: str) -> None:
    if len(values) != len(set(values)):
        raise FactIndexError(f"{field} must not contain duplicates")

def _expect_object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FactIndexError(f"{field} must be an object")
    return value


def _expect_array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise FactIndexError(f"{field} must be an array")
    return value


def _expect_keys(
    value: object,
    *,
    field: str,
    required: set[str],
) -> Mapping[str, Any]:
    payload = _expect_object(value, field)
    actual = set(payload)
    missing = sorted(required - actual)
    unknown = sorted(actual - required)
    if missing:
        raise FactIndexError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise FactIndexError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )
    return payload


def _location(value: object, field: str) -> FactLocation:
    payload = _expect_keys(
        value,
        field=field,
        required={"column", "file", "line"},
    )
    line = payload["line"]
    column = payload["column"]
    if isinstance(line, bool) or not isinstance(line, int):
        raise FactIndexError(f"{field}.line must be an integer")
    if isinstance(column, bool) or not isinstance(column, int):
        raise FactIndexError(f"{field}.column must be an integer")
    return FactLocation(
        _require_text(payload["file"], f"{field}.file"),
        line,
        column,
    )


def _optional_location(
    value: object,
    field: str,
) -> FactLocation | None:
    return None if value is None else _location(value, field)


def _optional_hash(value: object, field: str) -> str | None:
    return None if value is None else _require_hash(value, field)


def _text_array(value: object, field: str) -> tuple[str, ...]:
    values = _expect_array(value, field)
    return tuple(
        _require_text(item, f"{field}[{index}]")
        for index, item in enumerate(values)
    )


def load_fact_index(payload: Mapping[str, Any]) -> FactIndex:
    """Load and validate a strict fact-index payload."""

    root = _expect_keys(
        payload,
        field="fact_index",
        required={
            "calls",
            "definitions",
            "id",
            "limitations",
            "mutations",
            "purity",
            "schema",
            "source",
            "symbols",
            "uses",
        },
    )
    if root["schema"] != FACT_SCHEMA:
        raise FactIndexError(
            f"unsupported fact schema: expected {FACT_SCHEMA!r}, "
            f"got {root['schema']!r}"
        )

    source_payload = _expect_keys(
        root["source"],
        field="source",
        required={"content_sha256", "file", "language"},
    )
    source = FactSource(
        _require_text(source_payload["file"], "source.file"),
        _require_text(source_payload["language"], "source.language"),
        _require_hash(
            source_payload["content_sha256"],
            "source.content_sha256",
        ),
    )

    symbols: list[FactSymbol] = []
    for index, value in enumerate(
        _expect_array(root["symbols"], "symbols")
    ):
        field = f"symbols[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "declaration",
                "definition",
                "id",
                "kind",
                "linkage",
                "name",
                "owner",
                "qualified_name",
                "type",
            },
        )
        symbols.append(
            FactSymbol(
                _require_hash(item["id"], f"{field}.id"),
                _require_text(item["kind"], f"{field}.kind"),
                _require_text(item["name"], f"{field}.name"),
                _require_text(
                    item["qualified_name"],
                    f"{field}.qualified_name",
                ),
                _require_text(item["type"], f"{field}.type"),
                _require_text(item["linkage"], f"{field}.linkage"),
                _optional_hash(item["owner"], f"{field}.owner"),
                _location(
                    item["declaration"],
                    f"{field}.declaration",
                ),
                _optional_location(
                    item["definition"],
                    f"{field}.definition",
                ),
            )
        )

    definitions: list[DefinitionFact] = []
    for index, value in enumerate(
        _expect_array(root["definitions"], "definitions")
    ):
        field = f"definitions[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "context",
                "id",
                "kind",
                "location",
                "symbol",
            },
        )
        definitions.append(
            DefinitionFact(
                _require_hash(item["id"], f"{field}.id"),
                _require_hash(item["symbol"], f"{field}.symbol"),
                _optional_hash(
                    item["context"],
                    f"{field}.context",
                ),
                _require_text(item["kind"], f"{field}.kind"),
                _location(item["location"], f"{field}.location"),
            )
        )

    uses: list[UseFact] = []
    for index, value in enumerate(_expect_array(root["uses"], "uses")):
        field = f"uses[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "context",
                "id",
                "kind",
                "location",
                "symbol",
            },
        )
        uses.append(
            UseFact(
                _require_hash(item["id"], f"{field}.id"),
                _require_hash(item["symbol"], f"{field}.symbol"),
                _require_hash(
                    item["context"],
                    f"{field}.context",
                ),
                _require_text(item["kind"], f"{field}.kind"),
                _location(item["location"], f"{field}.location"),
            )
        )
    calls: list[CallFact] = []
    for index, value in enumerate(_expect_array(root["calls"], "calls")):
        field = f"calls[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "callee",
                "caller",
                "id",
                "kind",
                "location",
            },
        )
        calls.append(
            CallFact(
                _require_hash(item["id"], f"{field}.id"),
                _require_hash(item["caller"], f"{field}.caller"),
                _require_hash(item["callee"], f"{field}.callee"),
                _require_text(item["kind"], f"{field}.kind"),
                _location(item["location"], f"{field}.location"),
            )
        )

    mutations: list[MutationFact] = []
    for index, value in enumerate(
        _expect_array(root["mutations"], "mutations")
    ):
        field = f"mutations[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "context",
                "id",
                "kind",
                "location",
                "target",
            },
        )
        mutations.append(
            MutationFact(
                _require_hash(item["id"], f"{field}.id"),
                _require_hash(
                    item["context"],
                    f"{field}.context",
                ),
                _require_hash(item["target"], f"{field}.target"),
                _require_text(item["kind"], f"{field}.kind"),
                _location(item["location"], f"{field}.location"),
            )
        )

    purity: list[PurityFact] = []
    for index, value in enumerate(
        _expect_array(root["purity"], "purity")
    ):
        field = f"purity[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={"function", "reasons", "status"},
        )
        purity.append(
            PurityFact(
                _require_hash(
                    item["function"],
                    f"{field}.function",
                ),
                _require_text(item["status"], f"{field}.status"),
                _text_array(item["reasons"], f"{field}.reasons"),
            )
        )

    limitations: list[FactLimitation] = []
    for index, value in enumerate(
        _expect_array(root["limitations"], "limitations")
    ):
        field = f"limitations[{index}]"
        item = _expect_keys(
            value,
            field=field,
            required={
                "code",
                "context",
                "location",
                "message",
            },
        )
        limitations.append(
            FactLimitation(
                _require_text(item["code"], f"{field}.code"),
                _require_text(
                    item["message"],
                    f"{field}.message",
                ),
                _optional_hash(
                    item["context"],
                    f"{field}.context",
                ),
                _optional_location(
                    item["location"],
                    f"{field}.location",
                ),
            )
        )

    return FactIndex(
        _require_hash(root["id"], "index.id"),
        source,
        tuple(symbols),
        tuple(definitions),
        tuple(uses),
        tuple(calls),
        tuple(mutations),
        tuple(purity),
        tuple(limitations),
    )


def load_fact_index_json(text: str) -> FactIndex:
    """Parse strict JSON and return a validated fact index."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise FactIndexError(
            f"invalid fact-index JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise FactIndexError("fact index must be a JSON object")
    return load_fact_index(payload)
