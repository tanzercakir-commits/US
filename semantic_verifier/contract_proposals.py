"""Deterministic offline prompt packs for untrusted contract proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "codeskeptic.contract-proposal-request/v1"
PROMPT_SCHEMA = "codeskeptic.contract-proposal-prompt/v1"
RESPONSE_SCHEMA = "codeskeptic.contract-proposal-response/v1"
_MACHINE_MARKER = "cs: ai"
_PACK_PARTS = ("prompt_packs", "contract_proposal", "v1")
_ALLOWED_ROLES = frozenset({"global", "local", "parameter", "result"})


class ProposalInputError(ValueError):
    """Raised when an offline proposal request is malformed or ambiguous."""


def _expect_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProposalInputError(f"{label} must be an object")
    return value


def _expect_fields(
    value: Mapping[str, Any], required: set[str], label: str
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ProposalInputError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise ProposalInputError(f"{label} has unknown fields: {', '.join(unknown)}")


def _expect_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProposalInputError(f"{label} must be a non-empty string")
    return value


def _expect_text_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProposalInputError(f"{label} must be an array")
    items = tuple(_expect_text(item, f"{label} item") for item in value)
    if len(set(items)) != len(items):
        raise ProposalInputError(f"{label} contains duplicates")
    return tuple(sorted(items))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pack_resource(name: str) -> str:
    resource = files("semantic_verifier")
    for part in (*_PACK_PARTS, name):
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class ProposalSymbol:
    name: str
    type: str
    role: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "role": self.role, "type": self.type}


@dataclass(frozen=True, slots=True)
class ProposalTarget:
    language: str
    function: str
    signature: str
    body: str

    def to_dict(self) -> dict[str, str]:
        return {
            "body": self.body,
            "function": self.function,
            "language": self.language,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class ProposalContext:
    symbols: tuple[ProposalSymbol, ...]
    existing_contracts: tuple[str, ...]
    callee_contracts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "callee_contracts": list(self.callee_contracts),
            "existing_contracts": list(self.existing_contracts),
            "symbols": [symbol.to_dict() for symbol in self.symbols],
        }


@dataclass(frozen=True, slots=True)
class ProposalSource:
    file: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line}


@dataclass(frozen=True, slots=True)
class ContractProposalRequest:
    target: ProposalTarget
    context: ProposalContext
    source: ProposalSource

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "schema": REQUEST_SCHEMA,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
        }

    def identity_dict(self) -> dict[str, Any]:
        """Logical identity deliberately excludes checkout path and source line."""

        return {
            "context": self.context.to_dict(),
            "schema": REQUEST_SCHEMA,
            "target": self.target.to_dict(),
        }


def load_request(payload: Mapping[str, Any]) -> ContractProposalRequest:
    root = _expect_object(payload, "request")
    _expect_fields(root, {"schema", "target", "context", "source"}, "request")
    if root["schema"] != REQUEST_SCHEMA:
        raise ProposalInputError(
            f"unsupported request schema: expected {REQUEST_SCHEMA!r}, "
            f"got {root['schema']!r}"
        )

    target_payload = _expect_object(root["target"], "target")
    _expect_fields(
        target_payload, {"language", "function", "signature", "body"}, "target"
    )
    language = _expect_text(target_payload["language"], "target.language")
    if language != "c++17":
        raise ProposalInputError("target.language must be 'c++17'")
    target = ProposalTarget(
        language=language,
        function=_expect_text(target_payload["function"], "target.function"),
        signature=_expect_text(target_payload["signature"], "target.signature"),
        body=_expect_text(target_payload["body"], "target.body"),
    )

    context_payload = _expect_object(root["context"], "context")
    _expect_fields(
        context_payload,
        {"symbols", "existing_contracts", "callee_contracts"},
        "context",
    )
    raw_symbols = context_payload["symbols"]
    if not isinstance(raw_symbols, list):
        raise ProposalInputError("context.symbols must be an array")
    symbols: list[ProposalSymbol] = []
    for index, raw_symbol in enumerate(raw_symbols):
        symbol_payload = _expect_object(raw_symbol, f"context.symbols[{index}]")
        _expect_fields(
            symbol_payload, {"name", "type", "role"}, f"context.symbols[{index}]"
        )
        role = _expect_text(symbol_payload["role"], f"context.symbols[{index}].role")
        if role not in _ALLOWED_ROLES:
            raise ProposalInputError(
                f"context.symbols[{index}].role is unsupported: {role!r}"
            )
        symbols.append(
            ProposalSymbol(
                name=_expect_text(
                    symbol_payload["name"], f"context.symbols[{index}].name"
                ),
                type=_expect_text(
                    symbol_payload["type"], f"context.symbols[{index}].type"
                ),
                role=role,
            )
        )
    names = [symbol.name for symbol in symbols]
    if len(set(names)) != len(names):
        raise ProposalInputError("context.symbols contains duplicate names")
    context = ProposalContext(
        symbols=tuple(sorted(symbols, key=lambda item: (item.name, item.role, item.type))),
        existing_contracts=_expect_text_list(
            context_payload["existing_contracts"], "context.existing_contracts"
        ),
        callee_contracts=_expect_text_list(
            context_payload["callee_contracts"], "context.callee_contracts"
        ),
    )

    source_payload = _expect_object(root["source"], "source")
    _expect_fields(source_payload, {"file", "line"}, "source")
    line = source_payload["line"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise ProposalInputError("source.line must be a positive integer")
    source = ProposalSource(
        file=_expect_text(source_payload["file"], "source.file"), line=line
    )
    return ContractProposalRequest(target=target, context=context, source=source)


def load_request_json(text: str) -> ContractProposalRequest:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProposalInputError(f"request is not valid JSON: {error.msg}") from error
    return load_request(_expect_object(payload, "request"))


def read_request(path: Path) -> ContractProposalRequest:
    try:
        return load_request_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProposalInputError(f"cannot read request {path}: {error}") from error


def request_id(request: ContractProposalRequest) -> str:
    digest = hashlib.sha256(_canonical_json(request.identity_dict()).encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def response_schema() -> dict[str, Any]:
    try:
        payload = json.loads(_pack_resource("response.schema.json"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("bundled response schema is unavailable or malformed") from error
    if not isinstance(payload, dict) or payload.get("$id") != RESPONSE_SCHEMA:
        raise RuntimeError("bundled response schema has the wrong identity")
    return payload


def build_prompt_pack(request: ContractProposalRequest) -> dict[str, Any]:
    logical_id = request_id(request)
    system_prompt = _pack_resource("system.md").rstrip("\n")
    user_payload = {
        "request": request.to_dict(),
        "request_id": logical_id,
    }
    user_prompt = (
        "Propose candidate contracts for the request below. Echo request_id "
        "exactly and return one JSON object matching response_schema.\n"
        + _canonical_json(user_payload)
    )
    return {
        "messages": [
            {"content": system_prompt, "role": "system"},
            {"content": user_prompt, "role": "user"},
        ],
        "request_id": logical_id,
        "response_schema": response_schema(),
        "schema": PROMPT_SCHEMA,
        "trust_boundary": {
            "accepted_intent": False,
            "generator": "untrusted",
            "machine_marker": _MACHINE_MARKER,
            "referee_required": True,
        },
    }


def render_prompt_pack(request: ContractProposalRequest) -> str:
    return json.dumps(
        build_prompt_pack(request), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"