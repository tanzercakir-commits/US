"""Deterministic project-wide C++ declaration and direct-call index."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .frontend import ClangJsonFrontend, FrontendError, FrontendUnit
from .integer_types import TARGET_PROFILE_ID
from .project_manifest import (
    ProjectManifest,
    ProjectTranslationUnit,
    build_project_manifest,
)


PROJECT_INDEX_SCHEMA = "codeskeptic.project-index/v1"
PROJECT_INDEX_ID_SCHEMA = "codeskeptic.project-index-identity/v1"
PROJECT_FRONTEND_POLICY = "clang-json-ast/c++17-project-read-only/v1"

FUNCTION_STATES = frozenset(
    {"declaration_only", "defined", "odr_conflict"}
)
CALL_STATES = frozenset(
    {"conflicting", "external", "linked", "unresolved", "unsupported"}
)
UNIT_STATES = frozenset({"frontend_error", "parsed"})
ISSUE_CODES = frozenset(
    {
        "compiler_argument_unsupported",
        "frontend_error",
        "macro_function_unsupported",
        "malformed_function",
        "manifest_invalid",
        "missing_definition",
        "odr_conflict",
        "source_unreadable",
        "stale_source",
        "unsupported_call",
        "unsupported_function",
        "unresolved_call",
    }
)

_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FUNCTION_DECL_KINDS = frozenset(
    {
        "CXXConstructorDecl",
        "CXXConversionDecl",
        "CXXDestructorDecl",
        "CXXMethodDecl",
        "FunctionDecl",
    }
)
_CALL_KINDS = frozenset(
    {
        "CUDAKernelCallExpr",
        "CXXConstructExpr",
        "CXXMemberCallExpr",
        "CXXOperatorCallExpr",
        "CallExpr",
    }
)
_FORBIDDEN_DRIVER_EXACT = frozenset(
    {
        "--",
        "-E",
        "-M",
        "-MM",
        "-S",
        "-Xclang",
        "-arch",
        "-c",
        "-cc1",
        "-emit-ast",
        "-fmodules",
        "-fcxx-modules",
        "-load",
        "-o",
        "-save-temps",
        "-serialize-diagnostics",
        "-target",
        "-x",
        "/c",
    }
)
_FORBIDDEN_DRIVER_PREFIXES = (
    "--target=",
    "-MJ",
    "-Xclang=",
    "-fmodule-file",
    "-fmodules-cache-path",
    "-fpass-plugin",
    "-fplugin",
    "-m32",
    "-m64",
    "-march",
    "-mcpu",
    "-mtune",
    "/arch:",
)
_VALUE_OPTIONS = frozenset(
    {
        "-D",
        "-I",
        "-U",
        "-idirafter",
        "-imacros",
        "-include",
        "-isystem",
        "-iquote",
        "/D",
        "/FI",
        "/I",
        "/U",
    }
)
_DROP_CONTEXT_KEYS = frozenset(
    {
        "id",
        "isReferenced",
        "isUsed",
        "loc",
        "parentDeclContextId",
        "previousDecl",
        "range",
    }
)


class ProjectIndexError(ValueError):
    """Raised when a project index request or artifact is invalid."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def _identity_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": PROJECT_INDEX_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProjectIndexError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_RE.fullmatch(text) is None:
        raise ProjectIndexError(f"{field} must be a lowercase sha256 identity")
    return text


def _logical_path(value: object, field: str) -> str:
    text = _require_text(value, field).replace("\\", "/")
    if (
        text.startswith("/")
        or re.match(r"^[A-Za-z]:/", text) is not None
        or text.startswith("../")
        or "/../" in text
        or text == ".."
        or "//" in text
    ):
        raise ProjectIndexError(f"{field} must be project-relative")
    return text.removeprefix("./") or "."


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    if set(value) != expected:
        raise ProjectIndexError(
            f"{field} fields must be exactly {sorted(expected)!r}"
        )


@dataclass(frozen=True, order=True, slots=True)
class ProjectLocation:
    file: str
    line: int
    column: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "file", _logical_path(self.file, "location.file"))
        for value, field in (
            (self.line, "location.line"),
            (self.column, "location.column"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProjectIndexError(f"{field} must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "column": self.column,
            "file": self.file,
            "line": self.line,
        }


@dataclass(frozen=True, order=True, slots=True)
class ProjectSource:
    file: str
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "file", _logical_path(self.file, "source.file"))
        _require_hash(self.content_sha256, "source.content_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "content_sha256": self.content_sha256,
            "file": self.file,
        }


@dataclass(frozen=True, order=True, slots=True)
class ProjectUnitResult:
    file: str
    unit: str
    status: str
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "file", _logical_path(self.file, "unit.file"))
        _require_hash(self.unit, "unit.unit")
        if self.status not in UNIT_STATES:
            raise ProjectIndexError("unit.status is unsupported")
        if self.status == "parsed" and self.diagnostic is not None:
            raise ProjectIndexError("parsed unit cannot carry a diagnostic")
        if self.status == "frontend_error":
            _require_text(self.diagnostic, "unit.diagnostic")

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnostic": self.diagnostic,
            "file": self.file,
            "status": self.status,
            "unit": self.unit,
        }


@dataclass(frozen=True, order=True, slots=True)
class ProjectDefinition:
    location: ProjectLocation
    ast_sha256: str

    def __post_init__(self) -> None:
        _require_hash(self.ast_sha256, "definition.ast_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "ast_sha256": self.ast_sha256,
            "location": self.location.to_dict(),
        }


@dataclass(frozen=True, order=True, slots=True)
class ProjectFunction:
    id: str
    name: str
    qualified_name: str
    type: str
    language_linkage: str
    linkage: str
    owner_translation_unit: str | None
    declarations: tuple[ProjectLocation, ...]
    definitions: tuple[ProjectDefinition, ...]
    status: str

    def __post_init__(self) -> None:
        _require_hash(self.id, "function.id")
        _require_text(self.name, "function.name")
        _require_text(self.qualified_name, "function.qualified_name")
        _require_text(self.type, "function.type")
        if self.language_linkage not in {"c", "c++"}:
            raise ProjectIndexError("function.language_linkage is unsupported")
        if self.linkage not in {"external", "internal"}:
            raise ProjectIndexError("function.linkage is unsupported")
        if self.linkage == "internal":
            object.__setattr__(
                self,
                "owner_translation_unit",
                _logical_path(
                    self.owner_translation_unit,
                    "function.owner_translation_unit",
                ),
            )
        elif self.owner_translation_unit is not None:
            raise ProjectIndexError(
                "external function cannot have an owner translation unit"
            )
        if not self.declarations:
            raise ProjectIndexError("function requires a declaration")
        if self.declarations != tuple(sorted(set(self.declarations))):
            raise ProjectIndexError(
                "function.declarations must be sorted and unique"
            )
        if self.definitions != tuple(sorted(set(self.definitions))):
            raise ProjectIndexError(
                "function.definitions must be sorted and unique"
            )
        if self.status not in FUNCTION_STATES:
            raise ProjectIndexError("function.status is unsupported")
        if self.status == "declaration_only" and self.definitions:
            raise ProjectIndexError(
                "declaration-only function cannot have definitions"
            )
        if self.status == "defined" and len(self.definitions) != 1:
            raise ProjectIndexError(
                "defined function requires one canonical definition"
            )
        if self.status == "odr_conflict" and len(self.definitions) < 2:
            raise ProjectIndexError(
                "ODR conflict requires at least two definitions"
            )
        if self.id != _content_id("function", self.key_dict()):
            raise ProjectIndexError("function.id does not match canonical key")

    def key_dict(self) -> dict[str, object]:
        return {
            "language_linkage": self.language_linkage,
            "linkage": self.linkage,
            "owner_translation_unit": self.owner_translation_unit,
            "qualified_name": self.qualified_name,
            "type": self.type,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "declarations": [
                location.to_dict() for location in self.declarations
            ],
            "definitions": [
                definition.to_dict() for definition in self.definitions
            ],
            "id": self.id,
            "language_linkage": self.language_linkage,
            "linkage": self.linkage,
            "name": self.name,
            "owner_translation_unit": self.owner_translation_unit,
            "qualified_name": self.qualified_name,
            "status": self.status,
            "type": self.type,
        }


@dataclass(frozen=True, slots=True)
class ProjectCall:
    id: str
    caller: str | None
    target: str | None
    target_name: str
    target_type: str
    state: str
    location: ProjectLocation

    def __post_init__(self) -> None:
        _require_hash(self.id, "call.id")
        if self.caller is not None:
            _require_hash(self.caller, "call.caller")
        if self.target is not None:
            _require_hash(self.target, "call.target")
        _require_text(self.target_name, "call.target_name")
        _require_text(self.target_type, "call.target_type")
        if self.state not in CALL_STATES:
            raise ProjectIndexError("call.state is unsupported")
        if self.state in {"conflicting", "linked"} and self.target is None:
            raise ProjectIndexError(
                "linked/conflicting call requires a project target"
            )
        if self.state == "external" and self.target is not None:
            raise ProjectIndexError("external call cannot have a project target")
        if self.caller is None and self.state != "unsupported":
            raise ProjectIndexError(
                "only an unsupported call may omit its caller identity"
            )
        if self.id != _content_id("call", self.identity_dict()):
            raise ProjectIndexError("call.id does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        caller: str | None,
        target: str | None,
        target_name: str,
        target_type: str,
        state: str,
        location: ProjectLocation,
    ) -> "ProjectCall":
        fields: dict[str, object] = {
            "caller": caller,
            "location": location.to_dict(),
            "state": state,
            "target": target,
            "target_name": target_name,
            "target_type": target_type,
        }
        return cls(
            _content_id("call", fields),
            caller,
            target,
            target_name,
            target_type,
            state,
            location,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "caller": self.caller,
            "location": self.location.to_dict(),
            "state": self.state,
            "target": self.target,
            "target_name": self.target_name,
            "target_type": self.target_type,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


def _call_sort_key(call: ProjectCall) -> tuple[object, ...]:
    return (call.location, call.caller or "", call.target or "", call.id)


@dataclass(frozen=True, slots=True)
class ProjectIssue:
    code: str
    message: str
    unit: str | None = None
    function: str | None = None
    location: ProjectLocation | None = None

    def __post_init__(self) -> None:
        if self.code not in ISSUE_CODES:
            raise ProjectIndexError(f"unsupported issue code {self.code!r}")
        _require_text(self.message, "issue.message")
        if self.unit is not None:
            object.__setattr__(
                self,
                "unit",
                _logical_path(self.unit, "issue.unit"),
            )
        if self.function is not None:
            _require_hash(self.function, "issue.function")

    def sort_key(self) -> tuple[object, ...]:
        location = self.location
        return (
            self.code,
            self.unit or "",
            self.function or "",
            location.file if location is not None else "",
            location.line if location is not None else 0,
            location.column if location is not None else 0,
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "function": self.function,
            "location": (
                self.location.to_dict() if self.location is not None else None
            ),
            "message": self.message,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ProjectAccounting:
    units_selected: int
    units_parsed: int
    units_frontend_error: int
    functions_discovered: int
    functions_defined: int
    functions_declaration_only: int
    functions_unsupported: int
    functions_conflicting: int
    calls_discovered: int
    calls_linked: int
    calls_external: int
    calls_unresolved: int
    calls_unsupported: int
    calls_conflicting: int

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProjectIndexError(
                    f"accounting.{field_name} must be a non-negative integer"
                )
        if self.units_selected != (
            self.units_parsed + self.units_frontend_error
        ):
            raise ProjectIndexError("translation-unit accounting does not reconcile")
        if self.functions_discovered != (
            self.functions_defined
            + self.functions_declaration_only
            + self.functions_unsupported
            + self.functions_conflicting
        ):
            raise ProjectIndexError("function accounting does not reconcile")
        if self.calls_discovered != (
            self.calls_linked
            + self.calls_external
            + self.calls_unresolved
            + self.calls_unsupported
            + self.calls_conflicting
        ):
            raise ProjectIndexError("call accounting does not reconcile")

    def to_dict(self) -> dict[str, object]:
        return {
            "calls": {
                "conflicting": self.calls_conflicting,
                "discovered": self.calls_discovered,
                "external": self.calls_external,
                "linked": self.calls_linked,
                "unresolved": self.calls_unresolved,
                "unsupported": self.calls_unsupported,
            },
            "functions": {
                "conflicting": self.functions_conflicting,
                "declaration_only": self.functions_declaration_only,
                "defined": self.functions_defined,
                "discovered": self.functions_discovered,
                "unsupported": self.functions_unsupported,
            },
            "translation_units": {
                "frontend_error": self.units_frontend_error,
                "parsed": self.units_parsed,
                "selected": self.units_selected,
            },
        }


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    manifest: str
    target_profile: str
    frontend_policy: str
    sources: tuple[ProjectSource, ...]
    translation_units: tuple[ProjectUnitResult, ...]
    functions: tuple[ProjectFunction, ...]
    calls: tuple[ProjectCall, ...]
    limitations: tuple[ProjectIssue, ...]
    rejections: tuple[ProjectIssue, ...]
    accounting: ProjectAccounting
    status: str
    id: str
    schema: str = PROJECT_INDEX_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROJECT_INDEX_SCHEMA:
            raise ProjectIndexError("unsupported project index schema")
        _require_hash(self.manifest, "index.manifest")
        _require_text(self.target_profile, "index.target_profile")
        if self.frontend_policy != PROJECT_FRONTEND_POLICY:
            raise ProjectIndexError("unsupported project frontend policy")
        if self.sources != tuple(sorted(set(self.sources))):
            raise ProjectIndexError("index.sources must be sorted and unique")
        if self.translation_units != tuple(sorted(set(self.translation_units))):
            raise ProjectIndexError(
                "index.translation_units must be sorted and unique"
            )
        if self.functions != tuple(sorted(self.functions, key=lambda item: item.id)):
            raise ProjectIndexError("index.functions must be sorted by identity")
        if self.calls != tuple(sorted(self.calls, key=_call_sort_key)):
            raise ProjectIndexError("index.calls must be canonically sorted")
        if self.limitations != tuple(
            sorted(self.limitations, key=ProjectIssue.sort_key)
        ):
            raise ProjectIndexError("index.limitations must be sorted")
        if self.rejections != tuple(
            sorted(self.rejections, key=ProjectIssue.sort_key)
        ):
            raise ProjectIndexError("index.rejections must be sorted")
        for values, field in (
            ([item.id for item in self.functions], "function"),
            ([item.id for item in self.calls], "call"),
        ):
            if len(values) != len(set(values)):
                raise ProjectIndexError(f"duplicate {field} identity")
        function_ids = {item.id for item in self.functions}
        for call in self.calls:
            if call.caller is not None and call.caller not in function_ids:
                raise ProjectIndexError("call.caller is dangling")
            if call.target is not None and call.target not in function_ids:
                raise ProjectIndexError("call.target is dangling")
        expected_status = "invalid" if self.rejections else "valid"
        if self.status != expected_status:
            raise ProjectIndexError("index.status does not match rejections")
        self._validate_accounting()
        _require_hash(self.id, "index.id")
        if self.id != _content_id("project-index", self.identity_dict()):
            raise ProjectIndexError("index.id does not match canonical content")

    def _validate_accounting(self) -> None:
        unit_states = [unit.status for unit in self.translation_units]
        function_states = [function.status for function in self.functions]
        call_states = [call.state for call in self.calls]
        unsupported_functions = sum(
            issue.code
            in {
                "macro_function_unsupported",
                "malformed_function",
                "unsupported_function",
            }
            for issue in self.limitations
        )
        expected = ProjectAccounting(
            len(self.translation_units),
            unit_states.count("parsed"),
            unit_states.count("frontend_error"),
            len(self.functions) + unsupported_functions,
            function_states.count("defined"),
            function_states.count("declaration_only"),
            unsupported_functions,
            function_states.count("odr_conflict"),
            len(self.calls),
            call_states.count("linked"),
            call_states.count("external"),
            call_states.count("unresolved"),
            call_states.count("unsupported"),
            call_states.count("conflicting"),
        )
        if self.accounting != expected:
            raise ProjectIndexError("index.accounting does not match contents")

    @classmethod
    def create(
        cls,
        *,
        manifest: str,
        sources: Sequence[ProjectSource],
        translation_units: Sequence[ProjectUnitResult],
        functions: Sequence[ProjectFunction],
        calls: Sequence[ProjectCall],
        limitations: Sequence[ProjectIssue],
        rejections: Sequence[ProjectIssue],
    ) -> "ProjectIndex":
        source_items = tuple(sorted(set(sources)))
        unit_items = tuple(sorted(set(translation_units)))
        function_items = tuple(sorted(functions, key=lambda item: item.id))
        call_items = tuple(sorted(calls, key=_call_sort_key))
        limitation_items = tuple(
            sorted(set(limitations), key=ProjectIssue.sort_key)
        )
        rejection_items = tuple(
            sorted(set(rejections), key=ProjectIssue.sort_key)
        )
        function_states = [item.status for item in function_items]
        call_states = [item.state for item in call_items]
        unsupported_functions = sum(
            item.code
            in {
                "macro_function_unsupported",
                "malformed_function",
                "unsupported_function",
            }
            for item in limitation_items
        )
        accounting = ProjectAccounting(
            len(unit_items),
            sum(item.status == "parsed" for item in unit_items),
            sum(item.status == "frontend_error" for item in unit_items),
            len(function_items) + unsupported_functions,
            function_states.count("defined"),
            function_states.count("declaration_only"),
            unsupported_functions,
            function_states.count("odr_conflict"),
            len(call_items),
            call_states.count("linked"),
            call_states.count("external"),
            call_states.count("unresolved"),
            call_states.count("unsupported"),
            call_states.count("conflicting"),
        )
        status = "invalid" if rejection_items else "valid"
        fields: dict[str, object] = {
            "accounting": accounting.to_dict(),
            "calls": [item.to_dict() for item in call_items],
            "frontend_policy": PROJECT_FRONTEND_POLICY,
            "functions": [item.to_dict() for item in function_items],
            "limitations": [item.to_dict() for item in limitation_items],
            "manifest": manifest,
            "rejections": [item.to_dict() for item in rejection_items],
            "schema": PROJECT_INDEX_SCHEMA,
            "sources": [item.to_dict() for item in source_items],
            "status": status,
            "target_profile": TARGET_PROFILE_ID,
            "translation_units": [item.to_dict() for item in unit_items],
        }
        return cls(
            manifest,
            TARGET_PROFILE_ID,
            PROJECT_FRONTEND_POLICY,
            source_items,
            unit_items,
            function_items,
            call_items,
            limitation_items,
            rejection_items,
            accounting,
            status,
            _content_id("project-index", fields),
        )

    @property
    def valid(self) -> bool:
        return self.status == "valid"

    def identity_dict(self) -> dict[str, object]:
        return {
            "accounting": self.accounting.to_dict(),
            "calls": [item.to_dict() for item in self.calls],
            "frontend_policy": self.frontend_policy,
            "functions": [item.to_dict() for item in self.functions],
            "limitations": [item.to_dict() for item in self.limitations],
            "manifest": self.manifest,
            "rejections": [item.to_dict() for item in self.rejections],
            "schema": self.schema,
            "sources": [item.to_dict() for item in self.sources],
            "status": self.status,
            "target_profile": self.target_profile,
            "translation_units": [
                item.to_dict() for item in self.translation_units
            ],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.identity_dict(), "id": self.id}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _children(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inner = node.get("inner")
    if not isinstance(inner, list):
        return []
    return [child for child in inner if isinstance(child, Mapping)]


def _walk(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def _qual_type(node: Mapping[str, Any]) -> str:
    value = node.get("type")
    if not isinstance(value, Mapping):
        return ""
    type_name = value.get("qualType")
    return str(type_name) if type_name else ""


def _node_id(node: Mapping[str, Any]) -> str:
    identity = node.get("id")
    return str(identity) if identity else ""


def _node_body(node: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next(
        (
            child
            for child in _children(node)
            if child.get("kind") == "CompoundStmt"
        ),
        None,
    )


def _location_mapping(node: Mapping[str, Any]) -> Mapping[str, Any] | None:
    location = node.get("loc")
    if isinstance(location, Mapping):
        expansion = location.get("expansionLoc")
        if isinstance(expansion, Mapping):
            return expansion
        return location
    source_range = node.get("range")
    if isinstance(source_range, Mapping):
        begin = source_range.get("begin")
        if isinstance(begin, Mapping):
            expansion = begin.get("expansionLoc")
            if isinstance(expansion, Mapping):
                return expansion
            return begin
    return None


def _explicit_file(node: Mapping[str, Any]) -> str | None:
    location = _location_mapping(node)
    if location is None:
        return None
    value = location.get("file")
    return str(value) if value else None


def _uses_macro_location(node: Mapping[str, Any]) -> bool:
    for key in ("loc", "range"):
        value = node.get(key)
        if isinstance(value, Mapping) and (
            "spellingLoc" in value or "expansionLoc" in value
        ):
            return True
        if key == "range" and isinstance(value, Mapping):
            for endpoint in ("begin", "end"):
                nested = value.get(endpoint)
                if isinstance(nested, Mapping) and (
                    "spellingLoc" in nested or "expansionLoc" in nested
                ):
                    return True
    return False


def _normalized_ast(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_ast(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if key not in _DROP_CONTEXT_KEYS
            and key not in {"referencedMemberDecl"}
        }
    if isinstance(value, list):
        return [_normalized_ast(item) for item in value]
    return value


def _definition_hash(node: Mapping[str, Any]) -> str:
    return _bytes_hash(_identity_bytes(_normalized_ast(node)))


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path))


class _SourceRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.aliases: dict[str, str] = {}
        self.sources: dict[str, ProjectSource] = {}
        self.contents: dict[str, bytes] = {}

    def add_alias(self, physical: str | os.PathLike[str], logical: str) -> None:
        self.aliases[_path_key(Path(physical).resolve())] = _logical_path(
            logical,
            "source alias",
        )

    def logical_file(
        self,
        raw: str | None,
        working_directory: Path,
    ) -> str | None:
        if raw is None or raw.startswith("<"):
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = working_directory / path
        try:
            resolved = path.resolve()
        except OSError:
            return None
        alias = self.aliases.get(_path_key(resolved))
        if alias is not None:
            self.observe(alias)
            return alias
        if not _inside(self.root, resolved):
            return None
        logical = resolved.relative_to(self.root).as_posix()
        self.observe(logical)
        return logical

    def observe(self, logical: str) -> None:
        normalized = _logical_path(logical, "source.file")
        if normalized in self.sources:
            return
        path = self.root / normalized
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ProjectIndexError(
                f"cannot read observed project source {normalized}: {error}"
            ) from error
        self.contents[normalized] = content
        self.sources[normalized] = ProjectSource(
            normalized,
            _bytes_hash(content),
        )

    def location(
        self,
        node: Mapping[str, Any],
        logical_file: str | None,
    ) -> ProjectLocation | None:
        if logical_file is None:
            return None
        self.observe(logical_file)
        value = _location_mapping(node)
        if value is None:
            return None
        line = value.get("line")
        column = value.get("col")
        if (
            isinstance(line, int)
            and not isinstance(line, bool)
            and line > 0
            and isinstance(column, int)
            and not isinstance(column, bool)
            and column > 0
        ):
            return ProjectLocation(logical_file, line, column)
        offset = value.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            return None
        content = self.contents[logical_file]
        if offset > len(content):
            return None
        before = content[:offset]
        return ProjectLocation(
            logical_file,
            before.count(b"\n") + 1,
            offset - before.rfind(b"\n"),
        )

    def observe_ast_files(
        self,
        ast: Mapping[str, Any],
        working_directory: Path,
    ) -> None:
        def visit(value: object, in_location: bool = False) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    location_context = in_location or key in {
                        "includedFrom",
                        "loc",
                        "range",
                        "spellingLoc",
                        "expansionLoc",
                        "begin",
                        "end",
                    }
                    if key == "file" and in_location and isinstance(item, str):
                        self.logical_file(item, working_directory)
                    else:
                        visit(item, location_context)
            elif isinstance(value, list):
                for item in value:
                    visit(item, in_location)

        visit(ast)


@dataclass(frozen=True, slots=True)
class _FunctionDescriptor:
    name: str
    qualified_name: str
    type: str
    language_linkage: str
    linkage: str
    owner_translation_unit: str | None
    project_file: str | None
    supported: bool

    @property
    def identity(self) -> str | None:
        if not self.supported or self.project_file is None:
            return None
        return _content_id("function", self.key_dict())

    def key_dict(self) -> dict[str, object]:
        return {
            "language_linkage": self.language_linkage,
            "linkage": self.linkage,
            "owner_translation_unit": self.owner_translation_unit,
            "qualified_name": self.qualified_name,
            "type": self.type,
        }


@dataclass(frozen=True, slots=True)
class _FunctionOccurrence:
    descriptor: _FunctionDescriptor
    declaration: ProjectLocation
    definition: ProjectDefinition | None


@dataclass(frozen=True, slots=True)
class _RawCall:
    caller: str | None
    target: str | None
    target_name: str
    target_type: str
    classification: str
    location: ProjectLocation


@dataclass(frozen=True, slots=True)
class _BodyTask:
    body: Mapping[str, Any]
    caller: str | None
    logical_file: str
    supported: bool


def _join_scope(scope: tuple[str, ...], name: str) -> str:
    return "::".join((*scope, name)) if scope else name


def _resolved_compiler_arguments(
    unit: ProjectTranslationUnit,
    root: Path,
) -> tuple[str, ...]:
    if not unit.arguments:
        raise ProjectIndexError("translation unit has no compiler arguments")
    resolved: list[str] = []
    source_count = 0
    expect_value = False
    for raw in unit.arguments[1:]:
        argument = raw.replace("$ROOT", root.as_posix())
        if argument == "$SOURCE":
            source_count += 1
            continue
        if "$SOURCE" in argument or "$ROOT" in argument:
            raise ProjectIndexError(
                f"unsupported compiler placeholder in {raw!r}"
            )
        lowered = argument.lower()
        if expect_value:
            resolved.append(argument)
            expect_value = False
            continue
        if argument in _VALUE_OPTIONS:
            resolved.append(argument)
            expect_value = True
            continue
        if (
            argument in _FORBIDDEN_DRIVER_EXACT
            or lowered in {item.lower() for item in _FORBIDDEN_DRIVER_EXACT}
            or any(
                lowered.startswith(prefix.lower())
                for prefix in _FORBIDDEN_DRIVER_PREFIXES
            )
            or lowered.startswith(("/fe", "/fd", "/fo", "/link"))
            or lowered in {"--help", "--version", "-###", "-mllvm"}
        ):
            raise ProjectIndexError(
                f"compiler argument {raw!r} is outside the read-only AST policy"
            )
        if lowered.startswith("-std="):
            if lowered not in {"-std=c++17", "-std=gnu++17"}:
                raise ProjectIndexError(
                    f"compiler standard {raw!r} is outside C++17"
                )
        if lowered.startswith("/std:") and lowered != "/std:c++17":
            raise ProjectIndexError(
                f"compiler standard {raw!r} is outside C++17"
            )
        if (
            not argument.startswith(("-", "/"))
            and not re.match(r"^[A-Za-z]:[/\\]", argument)
        ):
            raise ProjectIndexError(
                f"bare compiler input {raw!r} is unsupported"
            )
        if re.match(r"^[A-Za-z]:[/\\]", argument):
            raise ProjectIndexError(
                f"bare compiler input {raw!r} is unsupported"
            )
        resolved.append(argument)
    if expect_value:
        raise ProjectIndexError("compiler path option is missing its value")
    if source_count != 1:
        raise ProjectIndexError(
            "translation unit must contain one canonical source placeholder"
        )
    return tuple(resolved)


class _UnitExtraction:
    def __init__(
        self,
        *,
        root: Path,
        unit: ProjectTranslationUnit,
        frontend_unit: FrontendUnit,
        working_directory: Path,
        sources: _SourceRegistry,
    ) -> None:
        self.root = root
        self.unit = unit
        self.frontend_unit = frontend_unit
        self.working_directory = working_directory
        self.sources = sources
        self.descriptors: dict[str, _FunctionDescriptor] = {}
        self.occurrences: list[_FunctionOccurrence] = []
        self.calls: list[_RawCall] = []
        self.limitations: list[ProjectIssue] = []
        self.body_tasks: list[_BodyTask] = []

    def run(
        self,
    ) -> tuple[
        tuple[_FunctionOccurrence, ...],
        tuple[_RawCall, ...],
        tuple[ProjectIssue, ...],
    ]:
        self.sources.add_alias(
            self.frontend_unit.physical_path,
            self.unit.file,
        )
        self.sources.observe(self.unit.file)
        self.sources.observe_ast_files(
            self.frontend_unit.ast,
            self.working_directory,
        )
        self._collect_children(
            self.frontend_unit.ast,
            (),
            None,
            "c++",
            False,
        )
        for task in self.body_tasks:
            self._scan_calls(
                task.body,
                task.caller,
                task.logical_file,
                task.supported,
                root=True,
            )
        return (
            tuple(self.occurrences),
            tuple(self.calls),
            tuple(self.limitations),
        )

    def _child_contexts(
        self,
        node: Mapping[str, Any],
        inherited_file: str | None,
    ) -> Iterable[tuple[Mapping[str, Any], str | None]]:
        current_file = inherited_file
        for child in _children(node):
            explicit = _explicit_file(child)
            if explicit is not None:
                current_file = explicit
            yield child, current_file

    def _logical(self, raw_file: str | None) -> str | None:
        return self.sources.logical_file(raw_file, self.working_directory)

    def _collect_children(
        self,
        parent: Mapping[str, Any],
        scope: tuple[str, ...],
        inherited_file: str | None,
        language_linkage: str,
        anonymous_namespace: bool,
    ) -> None:
        for node, raw_file in self._child_contexts(parent, inherited_file):
            if node.get("isImplicit"):
                continue
            kind = str(node.get("kind", ""))
            logical = self._logical(raw_file)
            if kind == "NamespaceDecl":
                name = str(node.get("name", ""))
                component = name or "<anonymous>"
                self._collect_children(
                    node,
                    (*scope, component),
                    raw_file,
                    language_linkage,
                    anonymous_namespace or not name,
                )
                continue
            if kind == "LinkageSpecDecl":
                language = str(node.get("language", "C++")).lower()
                self._collect_children(
                    node,
                    scope,
                    raw_file,
                    "c" if language == "c" else "c++",
                    anonymous_namespace,
                )
                continue
            if kind == "FunctionDecl":
                self._collect_free_function(
                    node,
                    scope,
                    logical,
                    language_linkage,
                    anonymous_namespace,
                )
                continue
            if kind == "FunctionTemplateDecl":
                self._collect_function_template(
                    node,
                    scope,
                    logical,
                    language_linkage,
                    anonymous_namespace,
                )
                continue
            if kind in {"CXXRecordDecl", "RecordDecl"}:
                self._collect_record_functions(
                    node,
                    scope,
                    logical,
                    language_linkage,
                    anonymous_namespace,
                )

    def _descriptor(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
        logical_file: str | None,
        language_linkage: str,
        anonymous_namespace: bool,
        *,
        supported: bool,
    ) -> _FunctionDescriptor:
        name = str(node.get("name", "")) or "<unnamed>"
        type_name = _qual_type(node) or "<unknown>"
        linkage = (
            "internal"
            if anonymous_namespace or node.get("storageClass") == "static"
            else "external"
        )
        return _FunctionDescriptor(
            name,
            _join_scope(scope, name),
            type_name,
            language_linkage,
            linkage,
            self.unit.file if linkage == "internal" else None,
            logical_file,
            supported,
        )

    def _register(
        self,
        node: Mapping[str, Any],
        descriptor: _FunctionDescriptor,
    ) -> None:
        identity = _node_id(node)
        if not identity:
            return
        existing = self.descriptors.get(identity)
        if existing is not None and existing != descriptor:
            raise ProjectIndexError(
                "one Clang function identity mapped to two project keys"
            )
        self.descriptors[identity] = descriptor

    def _collect_free_function(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
        logical_file: str | None,
        language_linkage: str,
        anonymous_namespace: bool,
    ) -> None:
        if logical_file is None:
            self._register(
                node,
                self._descriptor(
                    node,
                    scope,
                    None,
                    language_linkage,
                    anonymous_namespace,
                    supported=False,
                ),
            )
            return
        location = self.sources.location(node, logical_file)
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name or location is None:
            self._unsupported_function(
                node,
                scope,
                logical_file,
                language_linkage,
                anonymous_namespace,
                "malformed_function",
                "free function lacks a stable name, type, or project location",
            )
            return
        if _uses_macro_location(node):
            self._unsupported_function(
                node,
                scope,
                logical_file,
                language_linkage,
                anonymous_namespace,
                "macro_function_unsupported",
                "macro-expanded function semantics are outside A7.2",
            )
            return
        descriptor = self._descriptor(
            node,
            scope,
            logical_file,
            language_linkage,
            anonymous_namespace,
            supported=True,
        )
        self._register(node, descriptor)
        body = _node_body(node)
        definition = (
            ProjectDefinition(location, _definition_hash(body))
            if body is not None
            else None
        )
        self.occurrences.append(
            _FunctionOccurrence(descriptor, location, definition)
        )
        if body is not None:
            identity = descriptor.identity
            assert identity is not None
            self.body_tasks.append(
                _BodyTask(body, identity, logical_file, True)
            )

    def _unsupported_function(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
        logical_file: str,
        language_linkage: str,
        anonymous_namespace: bool,
        code: str,
        message: str,
    ) -> None:
        descriptor = self._descriptor(
            node,
            scope,
            logical_file,
            language_linkage,
            anonymous_namespace,
            supported=False,
        )
        self._register(node, descriptor)
        location = self.sources.location(node, logical_file)
        issue_unit = (
            self.unit.file if descriptor.linkage == "internal" else None
        )
        self.limitations.append(
            ProjectIssue(
                code,
                message,
                issue_unit,
                None,
                location,
            )
        )
        body = _node_body(node)
        if body is not None:
            self.body_tasks.append(
                _BodyTask(body, None, logical_file, False)
            )

    def _collect_function_template(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
        logical_file: str | None,
        language_linkage: str,
        anonymous_namespace: bool,
    ) -> None:
        functions = [
            child
            for child in _children(node)
            if child.get("kind") == "FunctionDecl"
        ]
        for function in functions:
            if logical_file is None:
                self._register(
                    function,
                    self._descriptor(
                        function,
                        scope,
                        None,
                        language_linkage,
                        anonymous_namespace,
                        supported=False,
                    ),
                )
                continue
            self._unsupported_function(
                function,
                scope,
                logical_file,
                language_linkage,
                anonymous_namespace,
                "unsupported_function",
                "function templates are outside A7.2",
            )

    def _collect_record_functions(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
        logical_file: str | None,
        language_linkage: str,
        anonymous_namespace: bool,
    ) -> None:
        record_name = str(node.get("name", "")) or "<anonymous-record>"
        record_scope = (*scope, record_name)
        for child in _children(node):
            kind = str(child.get("kind", ""))
            if child.get("isImplicit"):
                continue
            if kind in _FUNCTION_DECL_KINDS - {"FunctionDecl"}:
                if logical_file is None:
                    self._register(
                        child,
                        self._descriptor(
                            child,
                            record_scope,
                            None,
                            language_linkage,
                            anonymous_namespace,
                            supported=False,
                        ),
                    )
                else:
                    self._unsupported_function(
                        child,
                        record_scope,
                        logical_file,
                        language_linkage,
                        anonymous_namespace,
                        "unsupported_function",
                        "member functions are outside A7.2",
                    )
            elif kind in {"CXXRecordDecl", "RecordDecl"}:
                self._collect_record_functions(
                    child,
                    record_scope,
                    logical_file,
                    language_linkage,
                    anonymous_namespace,
                )

    def _scan_calls(
        self,
        node: Mapping[str, Any],
        caller: str | None,
        inherited_file: str,
        supported_caller: bool,
        *,
        root: bool = False,
    ) -> None:
        kind = str(node.get("kind", ""))
        if not root and kind in _FUNCTION_DECL_KINDS:
            if not node.get("isImplicit"):
                location = self.sources.location(node, inherited_file)
                self.limitations.append(
                    ProjectIssue(
                        "unsupported_function",
                        f"local {kind} is outside A7.2",
                        None,
                        None,
                        location,
                    )
                )
                body = _node_body(node)
                if body is not None:
                    self._scan_calls(
                        body,
                        None,
                        inherited_file,
                        False,
                        root=True,
                    )
            return
        logical_file = self._logical(_explicit_file(node)) or inherited_file
        if kind == "LambdaExpr":
            location = self.sources.location(node, logical_file)
            self.limitations.append(
                ProjectIssue(
                    "unsupported_function",
                    "lambda call operators are outside A7.2",
                    None,
                    None,
                    location,
                )
            )
            for child in _walk(node):
                if child is node:
                    continue
                body = (
                    _node_body(child)
                    if child.get("kind") in _FUNCTION_DECL_KINDS
                    else None
                )
                if body is not None:
                    self._scan_calls(
                        body,
                        None,
                        logical_file,
                        False,
                        root=True,
                    )
            return
        if kind in _CALL_KINDS:
            self._record_call(
                node,
                caller,
                logical_file,
                supported_caller,
            )
        for child in _children(node):
            self._scan_calls(
                child,
                caller,
                logical_file,
                supported_caller,
            )

    def _record_call(
        self,
        node: Mapping[str, Any],
        caller: str | None,
        logical_file: str,
        supported_caller: bool,
    ) -> None:
        location = self.sources.location(node, logical_file)
        if location is None:
            raise ProjectIndexError(
                "call expression lacks a stable project location"
            )
        kind = str(node.get("kind", ""))
        target_name = f"<{kind or 'call'}>"
        target_type = _qual_type(node) or "<unknown>"
        target: str | None = None
        classification = "unsupported"

        if kind == "CallExpr":
            children = _children(node)
            callee = children[0] if children else None
            references = (
                [
                    item
                    for item in _walk(callee)
                    if item.get("kind") == "DeclRefExpr"
                    and isinstance(item.get("referencedDecl"), Mapping)
                ]
                if callee is not None
                else []
            )
            function_reference = next(
                (
                    item["referencedDecl"]
                    for item in references
                    if item["referencedDecl"].get("kind")
                    == "FunctionDecl"
                ),
                None,
            )
            if isinstance(function_reference, Mapping):
                reference_id = str(function_reference.get("id", ""))
                descriptor = self.descriptors.get(reference_id)
                if descriptor is None:
                    target_name = str(
                        function_reference.get("name", "<unresolved>")
                    )
                    type_value = function_reference.get("type")
                    if isinstance(type_value, Mapping):
                        target_type = str(
                            type_value.get("qualType", "<unknown>")
                        )
                    classification = "unresolved"
                else:
                    target_name = descriptor.qualified_name
                    target_type = descriptor.type
                    target = descriptor.identity
                    if not supported_caller:
                        classification = "unsupported"
                    elif descriptor.project_file is None:
                        classification = "external"
                    elif not descriptor.supported:
                        classification = "unsupported"
                    else:
                        classification = "project"
            elif references:
                target_name = str(
                    references[0]["referencedDecl"].get(
                        "name",
                        "<indirect>",
                    )
                )
                classification = "unsupported"
            else:
                classification = "unresolved"
        if not supported_caller:
            classification = "unsupported"
            caller = None

        self.calls.append(
            _RawCall(
                caller,
                target,
                target_name,
                target_type,
                classification,
                location,
            )
        )
        if classification == "unsupported":
            self.limitations.append(
                ProjectIssue(
                    "unsupported_call",
                    (
                        f"{kind or 'call'} is indirect, member-based, "
                        "operator-based, constructed, or inside an "
                        "unsupported function"
                    ),
                    self.unit.file,
                    caller,
                    location,
                )
            )


def _merge_functions(
    occurrences: Sequence[_FunctionOccurrence],
) -> tuple[tuple[ProjectFunction, ...], tuple[ProjectIssue, ...]]:
    groups: dict[str, list[_FunctionOccurrence]] = {}
    for occurrence in occurrences:
        identity = occurrence.descriptor.identity
        if identity is None:
            raise ProjectIndexError(
                "supported function occurrence has no project identity"
            )
        groups.setdefault(identity, []).append(occurrence)

    functions: list[ProjectFunction] = []
    rejections: list[ProjectIssue] = []
    for identity in sorted(groups):
        group = groups[identity]
        descriptor = group[0].descriptor
        if any(item.descriptor.key_dict() != descriptor.key_dict() for item in group):
            raise ProjectIndexError("project function identity collision")
        declarations = tuple(
            sorted({item.declaration for item in group})
        )
        definitions = tuple(
            sorted(
                {
                    item.definition
                    for item in group
                    if item.definition is not None
                }
            )
        )
        if not definitions:
            status = "declaration_only"
        elif len(definitions) == 1:
            status = "defined"
        else:
            status = "odr_conflict"
        function = ProjectFunction(
            identity,
            descriptor.name,
            descriptor.qualified_name,
            descriptor.type,
            descriptor.language_linkage,
            descriptor.linkage,
            descriptor.owner_translation_unit,
            declarations,
            definitions,
            status,
        )
        functions.append(function)
        if status == "odr_conflict":
            rejections.append(
                ProjectIssue(
                    "odr_conflict",
                    (
                        f"function {descriptor.qualified_name} has "
                        f"{len(definitions)} distinct project definitions"
                    ),
                    descriptor.owner_translation_unit,
                    identity,
                    definitions[0].location,
                )
            )
    return tuple(functions), tuple(rejections)


def _finalize_calls(
    raw_calls: Sequence[_RawCall],
    functions: Sequence[ProjectFunction],
) -> tuple[tuple[ProjectCall, ...], tuple[ProjectIssue, ...]]:
    by_id = {function.id: function for function in functions}
    calls: dict[str, ProjectCall] = {}
    rejections: list[ProjectIssue] = []
    for raw in raw_calls:
        state = raw.classification
        if state == "project":
            target = by_id.get(raw.target or "")
            if target is None:
                state = "unresolved"
            elif target.status == "defined":
                state = "linked"
            elif target.status == "odr_conflict":
                state = "conflicting"
            else:
                state = "unresolved"
                rejections.append(
                    ProjectIssue(
                        "missing_definition",
                        (
                            f"direct callee {target.qualified_name} has no "
                            "project definition"
                        ),
                        None,
                        raw.caller,
                        raw.location,
                    )
                )
        elif state == "unresolved":
            rejections.append(
                ProjectIssue(
                    "unresolved_call",
                    (
                        f"direct call target {raw.target_name} could not be "
                        "resolved without guessing"
                    ),
                    None,
                    raw.caller,
                    raw.location,
                )
            )
        if state not in CALL_STATES:
            raise ProjectIndexError(
                f"internal call classification {state!r} is unsupported"
            )
        call = ProjectCall.create(
            caller=raw.caller,
            target=raw.target,
            target_name=raw.target_name,
            target_type=raw.target_type,
            state=state,
            location=raw.location,
        )
        calls[call.id] = call
    return tuple(calls.values()), tuple(rejections)


def _sanitize_diagnostic(
    message: str,
    *,
    root: Path,
    clang: str | None,
) -> str:
    sanitized = message.replace("\r", " ").replace("\n", " ")
    replacements = {
        str(root): "$ROOT",
        root.as_posix(): "$ROOT",
    }
    if clang is not None:
        clang_path = Path(clang)
        replacements[str(clang_path)] = "$CLANG"
        replacements[clang_path.as_posix()] = "$CLANG"
    for path, replacement in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        sanitized = sanitized.replace(path, replacement)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized or "frontend operation failed"


def build_project_index_from_manifest(
    project_root: str | os.PathLike[str],
    manifest: ProjectManifest,
    *,
    clang: str | None = None,
) -> ProjectIndex:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ProjectIndexError("project root must be an existing directory")
    if not manifest.valid:
        raise ProjectIndexError(
            "project index requires a valid project manifest"
        )

    sources = _SourceRegistry(root)
    unit_results: list[ProjectUnitResult] = []
    occurrences: list[_FunctionOccurrence] = []
    raw_calls: list[_RawCall] = []
    limitations: list[ProjectIssue] = []
    rejections: list[ProjectIssue] = []

    try:
        frontend = ClangJsonFrontend(clang)
        frontend_error: FrontendError | None = None
    except FrontendError as error:
        frontend = None
        frontend_error = error

    for unit in manifest.selected:
        source_path = root / unit.file
        working_directory = root / unit.directory
        if frontend_error is not None:
            diagnostic = _sanitize_diagnostic(
                str(frontend_error),
                root=root,
                clang=clang,
            )
            unit_results.append(
                ProjectUnitResult(
                    unit.file,
                    unit.id,
                    "frontend_error",
                    diagnostic,
                )
            )
            rejections.append(
                ProjectIssue(
                    "frontend_error",
                    diagnostic,
                    unit.file,
                )
            )
            continue
        try:
            content = source_path.read_bytes()
        except OSError:
            diagnostic = f"cannot read selected source {unit.file}"
            unit_results.append(
                ProjectUnitResult(
                    unit.file,
                    unit.id,
                    "frontend_error",
                    diagnostic,
                )
            )
            rejections.append(
                ProjectIssue(
                    "source_unreadable",
                    diagnostic,
                    unit.file,
                )
            )
            continue
        if _bytes_hash(content) != unit.content_sha256:
            diagnostic = (
                f"selected source {unit.file} changed after manifest creation"
            )
            unit_results.append(
                ProjectUnitResult(
                    unit.file,
                    unit.id,
                    "frontend_error",
                    diagnostic,
                )
            )
            rejections.append(
                ProjectIssue(
                    "stale_source",
                    diagnostic,
                    unit.file,
                )
            )
            continue
        try:
            compiler_arguments = _resolved_compiler_arguments(unit, root)
        except ProjectIndexError as error:
            diagnostic = str(error)
            unit_results.append(
                ProjectUnitResult(
                    unit.file,
                    unit.id,
                    "frontend_error",
                    diagnostic,
                )
            )
            rejections.append(
                ProjectIssue(
                    "compiler_argument_unsupported",
                    diagnostic,
                    unit.file,
                )
            )
            continue
        try:
            assert frontend is not None
            frontend_unit = frontend.parse_file(
                source_path,
                display_path=unit.file,
                compiler_arguments=compiler_arguments,
                working_directory=working_directory,
            )
            extracted = _UnitExtraction(
                root=root,
                unit=unit,
                frontend_unit=frontend_unit,
                working_directory=working_directory,
                sources=sources,
            ).run()
        except (FrontendError, ProjectIndexError) as error:
            diagnostic = _sanitize_diagnostic(
                str(error),
                root=root,
                clang=frontend.clang if frontend is not None else clang,
            )
            unit_results.append(
                ProjectUnitResult(
                    unit.file,
                    unit.id,
                    "frontend_error",
                    diagnostic,
                )
            )
            rejections.append(
                ProjectIssue(
                    "frontend_error",
                    diagnostic,
                    unit.file,
                )
            )
            continue
        unit_occurrences, unit_calls, unit_limitations = extracted
        occurrences.extend(unit_occurrences)
        raw_calls.extend(unit_calls)
        limitations.extend(unit_limitations)
        unit_results.append(
            ProjectUnitResult(unit.file, unit.id, "parsed")
        )

    functions, function_rejections = _merge_functions(occurrences)
    calls, call_rejections = _finalize_calls(raw_calls, functions)
    rejections.extend(function_rejections)
    rejections.extend(call_rejections)
    return ProjectIndex.create(
        manifest=manifest.id,
        sources=tuple(sources.sources.values()),
        translation_units=unit_results,
        functions=functions,
        calls=calls,
        limitations=limitations,
        rejections=rejections,
    )


def build_project_index(
    project_root: str | os.PathLike[str],
    compilation_database: str | os.PathLike[str] = "compile_commands.json",
    *,
    command_style: str | None = None,
    clang: str | None = None,
) -> ProjectIndex:
    manifest = build_project_manifest(
        project_root,
        compilation_database,
        command_style=command_style,
    )
    return build_project_index_from_manifest(
        project_root,
        manifest,
        clang=clang,
    )
