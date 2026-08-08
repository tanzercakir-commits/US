"""Fail-closed v6-to-v7 migration for value-only reports and modules."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import json
from typing import Any

from .memory_ir import MemoryModel, is_pointer_type
from .model import SCHEMA


V6_SCHEMA = "codeskeptic.semantic-verification/v6"
V7_SCHEMA = "codeskeptic.semantic-verification/v7"

_MEMORY_KINDS = frozenset(
    {
        "address_of",
        "memory_allocation",
        "memory_lifetime",
        "memory_load",
        "memory_store",
        "null_pointer",
        "pointer_equal",
        "pointer_value",
    }
)
_TYPE_FIELDS = frozenset({"result_type", "return_type", "type"})


class MemoryMigrationError(ValueError):
    """Raised when legacy input is not an exact value-only v6 artifact."""


def _assert_value_only(value: object, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            field = str(key)
            item_path = f"{path}.{field}"
            if field == "memory":
                raise MemoryMigrationError(
                    f"{item_path} is not valid in a value-only v6 artifact"
                )
            if (
                field in _TYPE_FIELDS
                and isinstance(item, str)
                and is_pointer_type(item)
            ):
                raise MemoryMigrationError(
                    f"{item_path} carries a pointer-like type"
                )
            if field == "kind" and item in _MEMORY_KINDS:
                raise MemoryMigrationError(
                    f"{item_path} carries a Memory IR node kind"
                )
            _assert_value_only(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_value_only(item, f"{path}[{index}]")


def migrate_v6_module_to_v7(
    module: Mapping[str, Any],
) -> dict[str, Any]:
    if module.get("schema") != V6_SCHEMA:
        raise MemoryMigrationError(
            f"module schema must be exactly {V6_SCHEMA!r}"
        )
    _assert_value_only(module)
    migrated = copy.deepcopy(dict(module))
    migrated["schema"] = V7_SCHEMA
    migrated["memory"] = MemoryModel.empty().to_dict()
    return migrated


def migrate_v6_report_to_v7(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    if SCHEMA != V7_SCHEMA:
        raise MemoryMigrationError("current producer is not the expected v7")
    if report.get("schema") != V6_SCHEMA:
        raise MemoryMigrationError(
            f"report schema must be exactly {V6_SCHEMA!r}"
        )
    _assert_value_only(report)
    migrated = copy.deepcopy(dict(report))
    migrated["schema"] = V7_SCHEMA
    semantic_ir = report.get("semantic_ir")
    if semantic_ir is not None:
        if not isinstance(semantic_ir, Mapping):
            raise MemoryMigrationError("semantic_ir must be an object")
        migrated["semantic_ir"] = migrate_v6_module_to_v7(semantic_ir)
    return migrated


def render_migrated_v6_report(report: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            migrate_v6_report_to_v7(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
