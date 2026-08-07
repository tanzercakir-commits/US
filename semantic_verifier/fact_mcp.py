"""Dependency-free MCP 2026-07-28 adapter for exact fact queries."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, BinaryIO, TextIO

from . import __version__
from .fact_queries import FactQueryError, FactWorld


MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_TOOL_NAME = "codeskeptic.query_facts"
SERVER_NAME = "codeskeptic-fact-query"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
CLIENT_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
CACHE_TTL_MS = 3_600_000

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

_MISSING = object()


class RpcFault(ValueError):
    """A deterministic JSON-RPC/MCP protocol fault."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = dict(data) if data is not None else None


def _server_meta() -> dict[str, Any]:
    return {
        SERVER_INFO_KEY: {
            "name": SERVER_NAME,
            "version": __version__,
        }
    }


def _canonical_line(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


def _error_response(
    request_id: object,
    code: int,
    message: str,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = dict(data)
    response: dict[str, Any] = {
        "error": error,
        "jsonrpc": "2.0",
    }
    if request_id is not _MISSING:
        response["id"] = request_id
    return response


def _result_response(
    request_id: object,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": request_id,
        "jsonrpc": "2.0",
        "result": dict(result),
    }


def _tool_definition() -> dict[str, Any]:
    return {
        "annotations": {
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "readOnlyHint": True,
        },
        "description": (
            "Query exact callers, mutators, or a bounded neighborhood from "
            "one validated CodeSkeptic fact index. Returned limitations are "
            "not proofs or inferred facts."
        ),
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "depth": {
                    "default": 2,
                    "maximum": 8,
                    "minimum": 0,
                    "type": "integer",
                },
                "kind": {
                    "enum": [
                        "neighborhood",
                        "who-calls",
                        "who-mutates",
                    ],
                    "type": "string",
                },
                "selector": {
                    "minLength": 1,
                    "type": "string",
                },
            },
            "required": ["kind", "selector"],
            "type": "object",
        },
        "name": MCP_TOOL_NAME,
        "outputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "object"},
                "index_id": {"type": "string"},
                "limitations": {
                    "items": {"type": "object"},
                    "type": "array",
                },
                "query": {"type": "object"},
                "schema": {
                    "const": "codeskeptic.fact-query-result/v1",
                },
                "target": {"type": "object"},
            },
            "required": [
                "answer",
                "index_id",
                "limitations",
                "query",
                "schema",
                "target",
            ],
            "type": "object",
        },
        "title": "CodeSkeptic Exact Fact Query",
    }


class FactMcpServer:
    """Stateless MCP request handler over one immutable FactWorld."""

    def __init__(self, world: FactWorld) -> None:
        self.world = world

    def handle_line(self, line: str) -> str | None:
        """Handle one newline-free JSON-RPC message."""

        try:
            payload = json.loads(
                line,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            return _canonical_line(
                _error_response(
                    _MISSING,
                    PARSE_ERROR,
                    "Parse error",
                )
            )
        response = self.handle_message(payload)
        return (
            None
            if response is None
            else _canonical_line(response)
        )

    def handle_message(
        self,
        payload: object,
    ) -> dict[str, Any] | None:
        """Handle one decoded message; notifications never receive replies."""

        if not isinstance(payload, Mapping):
            return _error_response(
                _MISSING,
                INVALID_REQUEST,
                "Invalid Request",
            )

        request_id = payload.get("id", _MISSING)
        notification = request_id is _MISSING
        valid_id = (
            isinstance(request_id, (str, int))
            and not isinstance(request_id, bool)
        )
        if not notification and not valid_id:
            request_id = _MISSING

        try:
            self._validate_envelope(payload, notification, valid_id)
            params = self._validate_params(payload)
            self._validate_metadata(params)
            result = self._dispatch(str(payload["method"]), params)
        except RpcFault as error:
            if notification:
                return None
            return _error_response(
                request_id,
                error.code,
                error.message,
                error.data,
            )
        except Exception:
            if notification:
                return None
            return _error_response(
                request_id,
                INTERNAL_ERROR,
                "Internal error",
            )

        if notification:
            return None
        return _result_response(request_id, result)

    @staticmethod
    def _validate_envelope(
        payload: Mapping[str, Any],
        notification: bool,
        valid_id: bool,
    ) -> None:
        if payload.get("jsonrpc") != "2.0":
            raise RpcFault(INVALID_REQUEST, "Invalid Request")
        method = payload.get("method")
        if not isinstance(method, str) or not method:
            raise RpcFault(INVALID_REQUEST, "Invalid Request")
        if "result" in payload or "error" in payload:
            raise RpcFault(INVALID_REQUEST, "Invalid Request")
        if not notification and not valid_id:
            raise RpcFault(INVALID_REQUEST, "Invalid Request")

    @staticmethod
    def _validate_params(
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        params = payload.get("params", _MISSING)
        if not isinstance(params, Mapping):
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {"reason": "params must be an object"},
            )
        return params

    @staticmethod
    def _validate_metadata(params: Mapping[str, Any]) -> None:
        metadata = params.get("_meta")
        if not isinstance(metadata, Mapping):
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {"reason": "params._meta must be an object"},
            )
        version = metadata.get(PROTOCOL_VERSION_KEY)
        if not isinstance(version, str):
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {
                    "reason": (
                        f"params._meta.{PROTOCOL_VERSION_KEY} "
                        "must be text"
                    )
                },
            )
        if version != MCP_PROTOCOL_VERSION:
            raise RpcFault(
                UNSUPPORTED_PROTOCOL_VERSION,
                "Unsupported protocol version",
                {
                    "requested": version,
                    "supported": [MCP_PROTOCOL_VERSION],
                },
            )
        capabilities = metadata.get(CLIENT_CAPABILITIES_KEY)
        if not isinstance(capabilities, Mapping):
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {
                    "reason": (
                        f"params._meta.{CLIENT_CAPABILITIES_KEY} "
                        "must be an object"
                    )
                },
            )
        client_info = metadata.get(CLIENT_INFO_KEY)
        if client_info is not None:
            if not isinstance(client_info, Mapping):
                raise RpcFault(
                    INVALID_PARAMS,
                    "Invalid params",
                    {
                        "reason": (
                            f"params._meta.{CLIENT_INFO_KEY} "
                            "must be an object"
                        )
                    },
                )
            for field in ("name", "version"):
                value = client_info.get(field)
                if not isinstance(value, str) or not value:
                    raise RpcFault(
                        INVALID_PARAMS,
                        "Invalid params",
                        {
                            "reason": (
                                f"params._meta.{CLIENT_INFO_KEY}."
                                f"{field} must be non-empty text"
                            )
                        },
                    )

    def _dispatch(
        self,
        method: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if method == "server/discover":
            self._allow_keys(params, {"_meta"})
            return self._discover()
        if method == "tools/list":
            self._allow_keys(params, {"_meta", "cursor"})
            if "cursor" in params:
                raise RpcFault(
                    INVALID_PARAMS,
                    "Invalid params",
                    {"reason": "this tool list does not paginate"},
                )
            return self._list_tools()
        if method == "tools/call":
            self._allow_keys(
                params,
                {
                    "_meta",
                    "arguments",
                    "inputResponses",
                    "name",
                    "requestState",
                },
            )
            if "inputResponses" in params or "requestState" in params:
                raise RpcFault(
                    INVALID_PARAMS,
                    "Invalid params",
                    {
                        "reason": (
                            "this server has no pending multi-round-trip "
                            "request"
                        )
                    },
                )
            return self._call_tool(params)
        raise RpcFault(METHOD_NOT_FOUND, "Method not found")

    @staticmethod
    def _allow_keys(
        values: Mapping[str, Any],
        allowed: set[str],
    ) -> None:
        unexpected = sorted(
            key
            for key in values
            if key not in allowed
        )
        if unexpected:
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {"unexpected": unexpected},
            )

    @staticmethod
    def _discover() -> dict[str, Any]:
        return {
            "_meta": _server_meta(),
            "cacheScope": "public",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                }
            },
            "instructions": (
                "Use codeskeptic.query_facts for exact, read-only facts. "
                "Limitations remain unproved and uninferred."
            ),
            "resultType": "complete",
            "supportedVersions": [MCP_PROTOCOL_VERSION],
            "ttlMs": CACHE_TTL_MS,
        }

    @staticmethod
    def _list_tools() -> dict[str, Any]:
        return {
            "_meta": _server_meta(),
            "cacheScope": "public",
            "resultType": "complete",
            "tools": [_tool_definition()],
            "ttlMs": CACHE_TTL_MS,
        }

    def _call_tool(
        self,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        name = params.get("name")
        if name != MCP_TOOL_NAME:
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {"reason": f"unknown tool {name!r}"},
            )
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise RpcFault(
                INVALID_PARAMS,
                "Invalid params",
                {"reason": "tool arguments must be an object"},
            )
        unexpected = sorted(
            key
            for key in arguments
            if key not in {"depth", "kind", "selector"}
        )
        if unexpected:
            return self._tool_error(
                f"unexpected tool arguments: {', '.join(unexpected)}"
            )

        kind = arguments.get("kind")
        selector = arguments.get("selector")
        depth = arguments.get("depth", 2)
        if not isinstance(kind, str):
            return self._tool_error("kind must be text")
        if not isinstance(selector, str) or not selector:
            return self._tool_error("selector must be non-empty text")
        if (
            "depth" in arguments
            and kind != "neighborhood"
        ):
            return self._tool_error(
                "depth is only valid for neighborhood queries"
            )

        try:
            query = self.world.query(
                kind,
                selector,
                depth=depth,
            )
        except FactQueryError as error:
            return self._tool_error(str(error))

        structured = query.to_dict()
        return {
            "_meta": _server_meta(),
            "content": [
                {
                    "text": query.to_json(),
                    "type": "text",
                }
            ],
            "isError": False,
            "resultType": "complete",
            "structuredContent": structured,
        }

    @staticmethod
    def _tool_error(message: str) -> dict[str, Any]:
        return {
            "_meta": _server_meta(),
            "content": [
                {
                    "text": message,
                    "type": "text",
                }
            ],
            "isError": True,
            "resultType": "complete",
        }

    def serve(
        self,
        input_stream: BinaryIO,
        output_stream: BinaryIO,
        error_stream: TextIO,
    ) -> int:
        """Serve newline-delimited UTF-8 messages until clean EOF."""

        del error_stream
        while True:
            raw = input_stream.readline()
            if raw == b"":
                return 0
            if raw.endswith(b"\n"):
                raw = raw[:-1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            try:
                line = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                response = _canonical_line(
                    _error_response(
                        _MISSING,
                        PARSE_ERROR,
                        "Parse error",
                    )
                )
            else:
                response = self.handle_line(line)
            if response is not None:
                output_stream.write(response.encode("utf-8"))
                output_stream.flush()
