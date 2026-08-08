"""Fail-closed compatibility gate for serialized verification reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import SCHEMA


class SchemaCompatibilityError(ValueError):
    """Raised when a report cannot be interpreted under the current schema."""


def require_current_schema(payload: Mapping[str, Any]) -> None:
    """Reject unknown or mixed report/Semantic IR schema identities."""

    schema = payload.get("schema")
    if schema != SCHEMA:
        raise SchemaCompatibilityError(
            f"unsupported report schema: expected {SCHEMA!r}, got {schema!r}"
        )

    semantic_ir = payload.get("semantic_ir")
    if semantic_ir is None:
        return
    if not isinstance(semantic_ir, Mapping):
        raise SchemaCompatibilityError("semantic_ir must be an object when present")
    nested_schema = semantic_ir.get("schema")
    if nested_schema != schema:
        raise SchemaCompatibilityError(
            "mixed report/Semantic IR schemas: "
            f"report={schema!r}, semantic_ir={nested_schema!r}"
        )
