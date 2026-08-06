"""Lower a controlled Clang JSON AST subset into owned, versioned IR."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
import re
from typing import Any, Iterable, Mapping

from .array_types import array_type, is_array_type, parse_source_array_type
from .contracts import contracts_before, invariants_before
from .frontend import FrontendUnit
from .integer_types import integer_type, is_fixed_integer_type
from .record_types import RecordField, RecordType, is_record_type, record_type
from .model import (
    CallFrameEffect,
    Expr,
    FrameContract,
    FrameLocation,
    FunctionIR,
    IRNode,
    LoopVariable,
    ModuleIR,
    ReferenceBinding,
    ReferencePathStep,
    SourceLocation,
    Symbol,
)


SOURCE_TYPE_MAP = {
    "bool": "bool",
    "int": "i32",
    "unsigned int": "u32",
    "long long": "i64",
    "unsigned long long": "u64",
}
SUPPORTED_TYPES = set(SOURCE_TYPE_MAP)
TRANSPARENT_EXPR_KINDS = {
    "ParenExpr",
    "ExprWithCleanups",
    "FullExpr",
    "ConstantExpr",
}
BUILTIN_ASSERT_LINK = "<builtin-assert:void(bool)>"

_REFERENCE_SENTINEL = "$reference:"


@dataclass(frozen=True, slots=True)
class _ReferenceTarget:
    id: str
    root: str
    path: tuple[str, ...]
    type: str
    mutable: bool


@dataclass(frozen=True, slots=True)
class _ParameterProfile:
    name: str
    type: str
    passing: str


@dataclass(frozen=True, slots=True)
class _FunctionProfile:
    node: Mapping[str, Any]
    link_name: str
    parameters: tuple[_ParameterProfile, ...]
    frame: FrameContract | None


@dataclass(frozen=True, slots=True)
class _ReferenceArgument:
    root: str
    path: tuple[str, ...]
    type: str
    mutable: bool



def _raw_string_end(source: str, offset: int) -> int | None:
    """Return the end of a C++ raw string token beginning at ``offset``."""

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


def _preprocessor_directives(source: str) -> list[tuple[int, str]]:
    """Find real preprocessing directives without matching text in comments.

    Comments are preprocessing whitespace, so a block comment may legally
    precede ``#``. Newlines inside a block comment or raw string do not begin a
    new logical preprocessing line.
    """

    directives: list[tuple[int, str]] = []
    offset = 0
    prefix_is_whitespace = True
    while offset < len(source):
        raw_end = _raw_string_end(source, offset)
        if raw_end is not None:
            prefix_is_whitespace = False
            offset = raw_end
            continue

        char = source[offset]
        if offset == 0 and char == "\ufeff":
            offset += 1
            continue
        if char == "\\" and offset + 1 < len(source):
            if source[offset + 1] == "\n":
                offset += 2
                continue
            if source.startswith("\r\n", offset + 1):
                offset += 3
                continue
        if char in "\r\n":
            if char == "\r" and offset + 1 < len(source) and source[offset + 1] == "\n":
                offset += 1
            prefix_is_whitespace = True
            offset += 1
            continue
        if char.isspace():
            offset += 1
            continue
        if source.startswith("//", offset):
            newline = source.find("\n", offset + 2)
            offset = len(source) if newline < 0 else newline
            continue
        if source.startswith("/*", offset):
            close = source.find("*/", offset + 2)
            offset = len(source) if close < 0 else close + 2
            continue
        if char in {'"', "'"}:
            prefix_is_whitespace = False
            quote = char
            offset += 1
            while offset < len(source):
                if source[offset] == "\\" and offset + 1 < len(source):
                    if source.startswith("\r\n", offset + 1):
                        offset += 3
                        continue
                    offset += 2
                    continue
                if source[offset] == quote:
                    offset += 1
                    break
                if source[offset] in "\r\n":
                    break
                offset += 1
            continue
        marker = "#" if char == "#" else "%:" if source.startswith("%:", offset) else None
        if marker is not None and prefix_is_whitespace:
            name_match = re.match(
                r"[ \t]*(?:/\*.*?\*/[ \t]*)*([A-Za-z_]\w*)",
                source[offset + len(marker) :],
                flags=re.DOTALL,
            )
            name = name_match.group(1) if name_match else "<null>"
            directives.append((offset, name))
        prefix_is_whitespace = False
        offset += len(marker) if marker is not None else 1
    return directives


class UnsupportedNode(RuntimeError):
    def __init__(self, node: Mapping[str, Any], reason: str) -> None:
        super().__init__(reason)
        self.node = node
        self.reason = reason


def _location_object(node: Mapping[str, Any]) -> Mapping[str, Any]:
    location = node.get("loc")
    if isinstance(location, dict) and "offset" in location:
        return location
    source_range = node.get("range")
    if isinstance(source_range, dict):
        begin = source_range.get("begin")
        if isinstance(begin, dict):
            return begin
    return location if isinstance(location, dict) else {}


def _unpack_location(location: Mapping[str, Any]) -> tuple[int | None, bool]:
    if "expansionLoc" in location:
        nested = location.get("expansionLoc")
        if isinstance(nested, dict):
            offset, _ = _unpack_location(nested)
            return offset, True
    if "spellingLoc" in location:
        nested = location.get("spellingLoc")
        if isinstance(nested, dict):
            offset, _ = _unpack_location(nested)
            return offset, True
    offset = location.get("offset")
    return (int(offset), False) if isinstance(offset, int) else (None, False)


def node_offset(node: Mapping[str, Any]) -> int | None:
    return _unpack_location(_location_object(node))[0]


def declaration_begin_offset(node: Mapping[str, Any]) -> int | None:
    source_range = node.get("range")
    if isinstance(source_range, dict):
        begin = source_range.get("begin")
        if isinstance(begin, dict):
            offset, _ = _unpack_location(begin)
            if offset is not None:
                return offset
    return node_offset(node)


def node_end_offset(node: Mapping[str, Any]) -> int | None:
    source_range = node.get("range")
    if isinstance(source_range, dict):
        end = source_range.get("end")
        if isinstance(end, dict):
            offset, _ = _unpack_location(end)
            if offset is not None:
                return offset
    return node_offset(node)


def node_is_macro_expansion(node: Mapping[str, Any]) -> bool:
    return _unpack_location(_location_object(node))[1]


def _file_from_location(location: Mapping[str, Any]) -> str | None:
    for key in ("expansionLoc", "spellingLoc"):
        nested = location.get(key)
        if isinstance(nested, dict):
            found = _file_from_location(nested)
            if found is not None:
                return found
    file_name = location.get("file")
    return str(file_name) if file_name else None


def node_physical_file(node: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        candidates.append(source_range.get("begin"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            found = _file_from_location(candidate)
            if found is not None:
                return os.path.normcase(os.path.abspath(found))
    return None


def _location_has_included_from(location: Mapping[str, Any]) -> bool:
    if "includedFrom" in location:
        return True
    for key in ("expansionLoc", "spellingLoc"):
        nested = location.get(key)
        if isinstance(nested, dict) and _location_has_included_from(nested):
            return True
    return False


def node_is_from_include(node: Mapping[str, Any]) -> bool:
    candidates: list[Any] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        candidates.append(source_range.get("begin"))
    return any(
        isinstance(candidate, dict) and _location_has_included_from(candidate)
        for candidate in candidates
    )


def _qual_type(node: Mapping[str, Any]) -> str:
    type_info = node.get("type")
    if not isinstance(type_info, dict):
        return ""
    return str(type_info.get("qualType", ""))


def _normalize_value_type(type_name: str) -> str:
    normalized = re.sub(r"\bconst\b", "", type_name)
    return " ".join(normalized.split())


def _function_return_type(node: Mapping[str, Any]) -> str:
    qualified = _qual_type(node)
    return _normalize_value_type(qualified.split(" (", 1)[0])


class SemanticLowerer:
    def __init__(self, unit: FrontendUnit) -> None:
        self.unit = unit
        self._function_index = 0
        self._node_index = 0
        self._module_issue_index = 0
        self._current_function = ""
        self._return_type = ""
        self._symbol_index = 0
        self._types: dict[str, str] = {}
        self._versions: dict[str, int] = {}
        self._locals: list[Symbol] = []
        self._references: list[ReferenceBinding] = []
        self._reference_targets: dict[str, _ReferenceTarget] = {}
        self._reference_index = 0
        self._loop_depth = 0
        self._symbol_name_counts: dict[str, int] = {}
        self._function_links: dict[str, str] = {}
        self._function_return_types: dict[str, str] = {}
        self._function_profiles: dict[str, list[_FunctionProfile]] = {}
        self._function_profile_ids: dict[str, _FunctionProfile] = {}
        self._record_types: dict[str, RecordType] = {}
        self._record_order: list[RecordType] = []
        self._consumed_contract_lines: set[int] = set()

    def lower(self) -> ModuleIR:
        functions: list[FunctionIR] = []
        unsupported: list[IRNode] = []
        for offset, name in _preprocessor_directives(self.unit.source):
            unsupported.append(
                self._module_issue(
                    self.unit.line_map.location(offset),
                    f"preprocessor directive #{name} is unsupported",
                )
            )

        children = self.unit.ast.get("inner", [])
        source_nodes: list[Mapping[str, Any]] = []
        current_file: str | None = None
        for child in children:
            if not isinstance(child, dict):
                continue
            explicit_file = node_physical_file(child)
            if explicit_file is not None:
                current_file = explicit_file
            offset = node_offset(child)
            if (
                current_file == self.unit.physical_path
                and not node_is_from_include(child)
                and offset is not None
                and 0 <= offset <= self.unit.line_map.byte_length
            ):
                source_nodes.append(child)
        source_nodes.sort(key=lambda child: int(node_offset(child) or 0))
        unsupported.extend(
            self._index_record_types(
                child
                for child in source_nodes
                if child.get("kind") in {"RecordDecl", "CXXRecordDecl"}
                and child.get("completeDefinition")
            )
        )
        self._index_function_links(
            child for child in source_nodes if child.get("kind") == "FunctionDecl"
        )
        for child in source_nodes:
            kind = child.get("kind")
            if kind == "FunctionDecl":
                lowered = self._lower_function(child)
                if lowered is not None:
                    functions.append(lowered)
            elif kind not in {"RecordDecl", "CXXRecordDecl"}:
                unsupported.append(
                    self._module_issue(
                        self._location(child),
                        f"top-level {kind or 'unknown node'} is unsupported",
                    )
                )
        for match in re.finditer(
            r"(?m)^(?:\ufeff)?[ \t]*//[^\r\n]*cs:", self.unit.source
        ):
            location = self.unit.line_map.location(
                match.start() + match.group(0).find("cs:")
            )
            if location.line not in self._consumed_contract_lines:
                unsupported.append(
                    self._module_issue(
                        location,
                        "orphan cs: contract is not attached to a supported declaration "
                        "or while statement",
                    )
                )
        return ModuleIR(
            source=self.unit.display_path.replace("\\", "/"),
            functions=tuple(functions),
            unsupported=tuple(unsupported),
            records=tuple(self._record_order),
        )

    def _index_record_types(
        self, record_nodes: Iterable[Mapping[str, Any]]
    ) -> list[IRNode]:
        issues: list[IRNode] = []
        for node in record_nodes:
            name = str(node.get("name", ""))
            try:
                if not name:
                    raise UnsupportedNode(node, "anonymous records are unsupported")
                if name in self._record_types:
                    raise UnsupportedNode(
                        node, f"duplicate record definition {name!r} is unsupported"
                    )
                profile = self._lower_record_type(node)
                self._record_types[name] = profile
                self._record_order.append(profile)
            except UnsupportedNode as error:
                issues.append(
                    self._module_issue(
                        self._location(error.node), error.reason
                    )
                )
        return issues

    def _lower_record_type(self, node: Mapping[str, Any]) -> RecordType:
        name = str(node.get("name", ""))
        if node.get("tagUsed") != "struct":
            raise UnsupportedNode(node, "only named struct records are supported")
        if node.get("bases"):
            raise UnsupportedNode(node, "record inheritance is unsupported")
        fields: list[RecordField] = []
        for child in node.get("inner", []):
            if not isinstance(child, dict):
                continue
            kind = child.get("kind")
            if kind == "FieldDecl":
                field_name = str(child.get("name", ""))
                raw_type = _qual_type(child)
                source_type = _normalize_value_type(raw_type)
                type_name = self._resolve_source_type(source_type)
                if not field_name:
                    raise UnsupportedNode(child, "anonymous fields are unsupported")
                if child.get("isBitfield"):
                    raise UnsupportedNode(child, "bitfields are unsupported")
                if child.get("access") not in {None, "public"}:
                    raise UnsupportedNode(child, "non-public fields are unsupported")
                if re.search(r"\bvolatile\b", raw_type):
                    raise UnsupportedNode(child, "volatile fields are unsupported")
                if child.get("inner"):
                    raise UnsupportedNode(
                        child, "default member initializers are unsupported"
                    )
                if not self._supported_field_type(type_name):
                    raise UnsupportedNode(
                        child, f"field type {source_type!r} is unsupported"
                    )
                fields.append(RecordField(field_name, type_name))
                continue
            if kind == "FullComment" or child.get("isImplicit"):
                continue
            raise UnsupportedNode(
                child, f"record member kind {kind or '<unknown>'} is unsupported"
            )
        try:
            return RecordType(name, tuple(fields))
        except ValueError as error:
            raise UnsupportedNode(node, str(error)) from error

    def _resolve_source_type(self, source_type: str) -> str:
        if source_type in SOURCE_TYPE_MAP:
            return SOURCE_TYPE_MAP[source_type]
        record = self._record_types.get(source_type)
        if record is not None:
            return record.name
        if "[" in source_type or "]" in source_type:
            try:
                array = parse_source_array_type(source_type, SOURCE_TYPE_MAP)
            except ValueError:
                return source_type
            if array is not None:
                return array.name
        return source_type

    @staticmethod
    def _supported_value_type(type_name: str) -> bool:
        return (
            type_name == "bool"
            or is_fixed_integer_type(type_name)
            or is_record_type(type_name)
        )

    @staticmethod
    def _supported_call_result_type(type_name: str) -> bool:
        return is_fixed_integer_type(type_name) or is_record_type(type_name)

    @staticmethod
    def _supported_field_type(type_name: str) -> bool:
        return (
            SemanticLowerer._supported_value_type(type_name)
            or is_array_type(type_name)
        )
    def _parameter_profile(self, node: Mapping[str, Any]) -> _ParameterProfile:
        name = str(node.get("name", ""))
        raw_type = _qual_type(node)
        normalized = _normalize_value_type(raw_type)
        if "&" not in normalized:
            return _ParameterProfile(
                name,
                self._resolve_source_type(normalized),
                "value",
            )
        referent_source = _normalize_value_type(normalized.rsplit("&", 1)[0])
        passing = (
            "const_reference"
            if re.search(r"\bconst\b", raw_type)
            else "mutable_reference"
        )
        if "&&" in raw_type or normalized.count("&") != 1:
            passing = "unsupported_reference"
        return _ParameterProfile(
            name,
            self._resolve_source_type(referent_source),
            passing,
        )

    def _index_function_links(
        self, function_nodes: Iterable[Mapping[str, Any]]
    ) -> None:
        records: list[
            tuple[Mapping[str, Any], str, tuple[str, ...], tuple[_ParameterProfile, ...]]
        ] = []
        signatures_by_name_arity: dict[
            tuple[str, int], set[tuple[str, ...]]
        ] = {}
        for node in function_nodes:
            name = str(node.get("name", ""))
            parameter_nodes = tuple(
                child
                for child in node.get("inner", [])
                if isinstance(child, dict) and child.get("kind") == "ParmVarDecl"
            )
            signature = tuple(_normalize_value_type(_qual_type(child)) for child in parameter_nodes)
            parameters = tuple(self._parameter_profile(child) for child in parameter_nodes)
            records.append((node, name, signature, parameters))
            signatures_by_name_arity.setdefault((name, len(signature)), set()).add(
                signature
            )

        for node, name, signature, parameters in records:
            overloaded = len(signatures_by_name_arity[(name, len(signature))]) > 1
            if self._is_builtin_assert_declaration(node):
                link_name = BUILTIN_ASSERT_LINK
            else:
                link_name = f"{name}({','.join(signature)})" if overloaded else name
            source_return_type = _function_return_type(node)
            return_type = self._resolve_source_type(source_return_type)
            self._function_return_types[link_name] = return_type
            declaration_id = node.get("id")
            if declaration_id is not None:
                self._function_links[str(declaration_id)] = link_name
            begin_byte_offset = declaration_begin_offset(node) or 0
            begin_offset = self.unit.line_map.char_offset_from_byte_offset(
                begin_byte_offset
            )
            _, frame, _ = contracts_before(
                self.unit.source,
                begin_offset,
                self.unit.line_map,
                {parameter.name: parameter.type for parameter in parameters},
                return_type,
                {parameter.name: parameter.passing for parameter in parameters},
            )
            profile = _FunctionProfile(node, link_name, parameters, frame)
            self._function_profiles.setdefault(link_name, []).append(profile)
            if declaration_id is not None:
                self._function_profile_ids[str(declaration_id)] = profile

    @staticmethod
    def _frame_key(
        profile: _FunctionProfile,
        frame: FrameContract,
    ) -> tuple[tuple[int, tuple[str, ...], str], ...]:
        parameter_indices = {
            parameter.name: index for index, parameter in enumerate(profile.parameters)
        }
        return tuple(
            (
                parameter_indices[target.root],
                tuple(step.value for step in target.path),
                target.type,
            )
            for target in frame.targets
        )

    def _effective_frame(self, profile: _FunctionProfile) -> FrameContract | None:
        framed = [
            (candidate, candidate.frame)
            for candidate in self._function_profiles.get(profile.link_name, ())
            if candidate.frame is not None
            and len(candidate.parameters) == len(profile.parameters)
        ]
        if not framed:
            return None
        keys = {self._frame_key(candidate, frame) for candidate, frame in framed}
        if len(keys) != 1:
            raise UnsupportedNode(
                profile.node,
                "conflicting modifies contracts across declarations are unsupported",
            )
        source_profile, source_frame = framed[0]
        source_indices = {
            parameter.name: index
            for index, parameter in enumerate(source_profile.parameters)
        }
        return replace(
            source_frame,
            targets=tuple(
                replace(
                    target,
                    root=profile.parameters[source_indices[target.root]].name,
                )
                for target in source_frame.targets
            ),
        )
    def _function_link(self, node: Mapping[str, Any]) -> str:
        declaration_id = node.get("id")
        if declaration_id is not None:
            linked = self._function_links.get(str(declaration_id))
            if linked is not None:
                return linked
        return str(node.get("name", ""))

    @staticmethod
    def _is_builtin_assert_declaration(node: Mapping[str, Any]) -> bool:
        if str(node.get("name", "")) != "assert":
            return False
        inner = [child for child in node.get("inner", []) if isinstance(child, dict)]
        if any(
            child.get("kind") in {"CompoundStmt", "CXXTryStmt"}
            for child in inner
        ):
            return False
        parameters = [child for child in inner if child.get("kind") == "ParmVarDecl"]
        return (
            _function_return_type(node) == "void"
            and len(parameters) == 1
            and _qual_type(parameters[0]) == "bool"
        )

    def _lower_function(self, node: Mapping[str, Any]) -> FunctionIR | None:
        name = str(node.get("name", ""))
        link_name = self._function_link(node)
        inner = [child for child in node.get("inner", []) if isinstance(child, dict)]
        parameter_nodes = [child for child in inner if child.get("kind") == "ParmVarDecl"]
        function_try_node = next(
            (child for child in inner if child.get("kind") == "CXXTryStmt"),
            None,
        )
        body_node = next(
            (child for child in inner if child.get("kind") == "CompoundStmt"),
            None,
        )
        source_return_type = _function_return_type(node)
        return_type = self._resolve_source_type(source_return_type)
        if link_name == BUILTIN_ASSERT_LINK:
            return None

        self._function_index += 1
        function_id = f"f{self._function_index:04d}"
        self._current_function = function_id
        self._return_type = return_type
        self._symbol_index = 0
        self._types = {}
        self._versions = {}
        self._locals = []
        self._references = []
        self._reference_targets = {}
        self._reference_index = 0
        self._loop_depth = 0
        self._symbol_name_counts = {}

        function_location = self._location(node)
        begin_byte_offset = declaration_begin_offset(node) or 0
        begin_offset = self.unit.line_map.char_offset_from_byte_offset(
            begin_byte_offset
        )
        initial_error: UnsupportedNode | None = None
        if node_is_macro_expansion(node):
            initial_error = UnsupportedNode(node, "macro-generated function is unsupported")
        if "&" in source_return_type:
            initial_error = UnsupportedNode(
                node, "reference returns are unsupported because the target lifetime escapes"
            )
        elif return_type == "void":
            if body_node is not None:
                initial_error = UnsupportedNode(
                    node, "void function definitions are outside the reviewed subset"
                )
        elif not self._supported_value_type(return_type):
            initial_error = UnsupportedNode(
                node, f"return type {source_return_type or '<unknown>'!r} is unsupported"
            )

        declaration_id = node.get("id")
        profile = (
            self._function_profile_ids.get(str(declaration_id))
            if declaration_id is not None
            else None
        )
        if profile is None:
            profile = _FunctionProfile(
                node,
                link_name,
                tuple(self._parameter_profile(item) for item in parameter_nodes),
                None,
            )

        parameters: list[Symbol] = []
        environment: dict[str, str] = {}
        for parameter_node, parameter_profile in zip(parameter_nodes, profile.parameters):
            parameter_name = str(parameter_node.get("name", ""))
            raw_parameter_type = _qual_type(parameter_node)
            source_parameter_type = _normalize_value_type(raw_parameter_type)
            parameter_type = parameter_profile.type
            passing = parameter_profile.passing
            if not parameter_name:
                initial_error = UnsupportedNode(
                    parameter_node, "unnamed parameters are unsupported"
                )
                parameter_name = f"unnamed_{len(parameters)}"
            if parameter_name == "result":
                initial_error = UnsupportedNode(
                    parameter_node,
                    "parameter name 'result' is reserved for postconditions",
                )
            if re.search(r"\bvolatile\b", raw_parameter_type):
                initial_error = UnsupportedNode(
                    parameter_node, "volatile parameters are unsupported"
                )
            if passing == "unsupported_reference":
                initial_error = UnsupportedNode(
                    parameter_node, "only lvalue reference parameters are supported"
                )
            elif not self._supported_value_type(parameter_type):
                initial_error = UnsupportedNode(
                    parameter_node,
                    f"parameter type {source_parameter_type or '<unknown>'!r} is unsupported",
                )
            if parameter_name in environment:
                initial_error = UnsupportedNode(
                    parameter_node, f"duplicate parameter {parameter_name!r}"
                )
            ir_name = self._new_symbol_name(parameter_name)
            self._types[ir_name] = parameter_type or "i32"
            self._versions[ir_name] = 0
            versioned = f"{ir_name}#0"
            environment[parameter_name] = versioned
            parameters.append(
                self._new_symbol(
                    ir_name,
                    parameter_type or "i32",
                    versioned,
                    self._location(parameter_node),
                    source_name=parameter_name,
                    passing=passing,
                )
            )

        if function_try_node is not None:
            initial_error = UnsupportedNode(
                function_try_node, "function try blocks are unsupported"
            )

        parameter_types = {
            (symbol.source_name or symbol.name): symbol.type for symbol in parameters
        }
        parameter_modes = {
            (symbol.source_name or symbol.name): symbol.passing or "value"
            for symbol in parameters
        }
        contracts, declared_frame, contract_issues = contracts_before(
            self.unit.source,
            begin_offset,
            self.unit.line_map,
            parameter_types,
            return_type,
            parameter_modes,
        )
        self._consumed_contract_lines.update(
            contract.location.line for contract in contracts
        )
        if declared_frame is not None:
            self._consumed_contract_lines.add(declared_frame.location.line)
        self._consumed_contract_lines.update(
            issue.location.line for issue in contract_issues
        )
        if contract_issues and initial_error is None:
            issue = contract_issues[0]
            initial_error = UnsupportedNode(
                node, f"contract at {issue.location.line}:{issue.location.column}: {issue.reason}"
            )
        effective_frame: FrameContract | None = None
        try:
            effective_frame = self._effective_frame(profile)
        except UnsupportedNode as error:
            if initial_error is None:
                initial_error = error
        reference_parameters = tuple(
            symbol for symbol in parameters if symbol.passing != "value"
        )
        if reference_parameters and effective_frame is None and initial_error is None:
            initial_error = UnsupportedNode(
                node, "reference parameters require an explicit cs: modifies contract"
            )
        if reference_parameters and body_node is not None and (
            initial_error is None
            or initial_error.reason == "void function definitions are outside the reviewed subset"
        ):
            initial_error = UnsupportedNode(
                node,
                "reference-parameter definitions are unsupported; use a contracted declaration",
            )
        symbols_by_source = {
            symbol.source_name or symbol.name: symbol for symbol in parameters
        }
        lowered_frame = None
        if effective_frame is not None:
            lowered_frame = replace(
                effective_frame,
                targets=tuple(
                    replace(target, root=symbols_by_source[target.root].id)
                    for target in effective_frame.targets
                ),
            )
        replacements = {
            (symbol.source_name or symbol.name): Expr.variable(
                symbol.versioned_name, symbol.type
            )
            for symbol in parameters
        }
        lowered_contracts = tuple(
            replace(contract, expression=contract.expression.substitute(replacements))
            for contract in contracts
        )
        if contract_issues and initial_error is None:
            issue = contract_issues[0]
            initial_error = UnsupportedNode(
                node, f"contract at {issue.location.line}:{issue.location.column}: {issue.reason}"
            )
        body: tuple[IRNode, ...]
        if initial_error is not None:
            body = (self._unsupported(initial_error.node, initial_error.reason),)
        elif body_node is None:
            body = ()
        else:
            try:
                assumes = [
                    self._node(
                        "assume",
                        contract.location,
                        expression=contract.expression,
                        origin="requires",
                    )
                    for contract in lowered_contracts
                    if contract.kind == "requires"
                ]
                lowered_body, _, falls_through = self._lower_sequence(
                    body_node.get("inner", []), environment
                )
                if falls_through and name == "main" and return_type == "i32":
                    lowered_body.append(
                        self._node(
                            "return",
                            self._end_location(body_node),
                            expression=Expr.integer(0),
                            origin="implicit_main_fallthrough",
                        )
                    )
                body = tuple(assumes + lowered_body)
            except UnsupportedNode as error:
                body = (self._unsupported(error.node, error.reason),)

        return FunctionIR(
            id=function_id,
            name=name,
            return_type=return_type,
            location=function_location,
            parameters=tuple(parameters),
            locals=tuple(self._locals),
            contracts=lowered_contracts,
            body=body,
            references=tuple(self._references),
            frame=lowered_frame,
            has_body=body_node is not None or function_try_node is not None,
            link_name=link_name,
        )

    def _lower_sequence(
        self, raw_nodes: list[Any], environment: Mapping[str, str]
    ) -> tuple[list[IRNode], dict[str, str], bool]:
        nodes: list[IRNode] = []
        current = dict(environment)
        falls_through = True
        for index, raw in enumerate(raw_nodes):
            if not falls_through:
                self._discard_lower_sequence(raw_nodes[index:], current)
                break
            if not isinstance(raw, dict):
                continue
            produced, current, falls_through = self._lower_statement(raw, current)
            nodes.extend(produced)
        return nodes, current, falls_through

    def _discard_lower_sequence(
        self, raw_nodes: list[Any], environment: Mapping[str, str]
    ) -> None:
        """Validate unreachable syntax without letting it affect emitted IR."""

        saved_types = dict(self._types)
        saved_versions = dict(self._versions)
        saved_locals = list(self._locals)
        saved_references = list(self._references)
        saved_reference_targets = dict(self._reference_targets)
        saved_reference_index = self._reference_index
        saved_loop_depth = self._loop_depth
        saved_name_counts = dict(self._symbol_name_counts)
        saved_node_index = self._node_index
        try:
            self._lower_sequence(raw_nodes, dict(environment))
        finally:
            self._types = saved_types
            self._versions = saved_versions
            self._locals = saved_locals
            self._references = saved_references
            self._reference_targets = saved_reference_targets
            self._reference_index = saved_reference_index
            self._loop_depth = saved_loop_depth
            self._symbol_name_counts = saved_name_counts
            self._node_index = saved_node_index

    def _lower_statement(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> tuple[list[IRNode], dict[str, str], bool]:
        self._reject_macro(node)
        kind = str(node.get("kind", ""))
        current = dict(environment)

        if kind == "CompoundStmt":
            outer_names = set(current)
            nodes, nested, falls = self._lower_sequence(node.get("inner", []), current)
            scoped = {name: value for name, value in nested.items() if name in outer_names}
            return nodes, scoped, falls

        if kind == "DeclStmt":
            produced: list[IRNode] = []
            for declaration in node.get("inner", []):
                if not isinstance(declaration, dict) or declaration.get("kind") != "VarDecl":
                    raise UnsupportedNode(node, "only local variable declarations are supported")
                declaration_nodes, current = self._lower_local(declaration, current)
                produced.extend(declaration_nodes)
            return produced, current, True

        if kind == "BinaryOperator" and node.get("opcode") == "=":
            inner = self._inner(node, 2)
            name, steps, writable = self._lvalue_path(inner[0], current)
            if not writable:
                raise UnsupportedNode(node, "assignment through a const reference is unsupported")
            if name not in current:
                raise UnsupportedNode(node, f"assignment to unknown variable {name!r}")
            ir_name = self._version_base(current[name])
            root_type = self._types[ir_name]
            root = Expr.variable(current[name], root_type)
            destination = self._path_expression(root, steps, node)
            call_node = self._direct_call_expression(inner[1])
            if call_node is not None:
                if steps:
                    raise UnsupportedNode(
                        node, "call results may only replace a whole local value"
                    )
                if not self._supported_call_result_type(root_type):
                    raise UnsupportedNode(
                        node, "only integer or value-record call results may be assigned"
                    )
                produced, current, target = self._lower_call(
                    call_node, current, result_root=ir_name
                )
                assert target is not None
                current[name] = target
                return [produced], current, True
            value = self._expression(inner[1], current)
            if value.type != destination.type:
                raise UnsupportedNode(node, "assignment changes the value type")
            expression = self._replace_path(root, steps, value, node)
            target = self._next_version(ir_name)
            current[name] = target
            return [
                self._node(
                    "assign",
                    self._location(node),
                    target=target,
                    expression=expression,
                )
            ], current, True
        if kind == "IfStmt":
            return self._lower_if(node, current)

        if kind == "WhileStmt":
            return self._lower_while(node, current)

        if kind == "ReturnStmt":
            inner = [child for child in node.get("inner", []) if isinstance(child, dict)]
            if len(inner) != 1:
                raise UnsupportedNode(node, "return must contain exactly one expression")
            value = self._expression(inner[0], current)
            if value.type != self._return_type:
                raise UnsupportedNode(
                    node,
                    f"return type mismatch: expected {self._return_type}, got {value.type}",
                )
            return [
                self._node("return", self._location(node), expression=value)
            ], current, False

        if kind == "CallExpr":
            call, current, _ = self._lower_call(node, current, result_root=None)
            if call.callee == BUILTIN_ASSERT_LINK:
                if len(call.arguments) != 1 or call.arguments[0].type != "bool":
                    raise UnsupportedNode(node, "assert requires one boolean argument")
                return [
                    self._node(
                        "assert", self._location(node), expression=call.arguments[0]
                    )
                ], current, True
            return [call], current, True

        if kind == "NullStmt":
            return [], current, True
        if kind in {
            "DoStmt",
            "ForStmt",
            "CXXForRangeStmt",
            "SwitchStmt",
            "CXXTryStmt",
            "CXXThrowExpr",
            "GotoStmt",
        }:
            raise UnsupportedNode(node, f"{kind} is unsupported in prototype v0")
        raise UnsupportedNode(node, f"statement kind {kind or '<unknown>'} is unsupported")

    def _lower_local(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> tuple[list[IRNode], dict[str, str]]:
        self._reject_macro(node)
        current = dict(environment)
        name = str(node.get("name", ""))
        raw_type_name = _qual_type(node)
        source_type_name = _normalize_value_type(raw_type_name)
        if "&" in source_type_name:
            return self._lower_reference(node, environment, name, raw_type_name)
        try:
            array_profile = parse_source_array_type(source_type_name, SOURCE_TYPE_MAP)
        except ValueError as error:
            raise UnsupportedNode(node, str(error)) from error
        type_name = (
            array_profile.name
            if array_profile is not None
            else self._resolve_source_type(source_type_name)
        )
        if not name:
            raise UnsupportedNode(node, "unnamed local variable is unsupported")
        if name in current:
            raise UnsupportedNode(node, f"shadowing variable {name!r} is unsupported")
        if re.search(r"\bvolatile\b", raw_type_name):
            raise UnsupportedNode(node, "volatile local variables are unsupported")
        if node.get("storageClass") == "static" or node.get("tls") is not None:
            raise UnsupportedNode(
                node, "static and thread_local local variables are unsupported"
            )
        if not self._supported_field_type(type_name):
            raise UnsupportedNode(node, f"local type {source_type_name!r} is unsupported")
        initializer_nodes = [
            child for child in node.get("inner", []) if isinstance(child, dict)
        ]
        if not initializer_nodes:
            raise UnsupportedNode(node, f"uninitialized local {name!r} is unsupported")
        ir_name = self._new_symbol_name(name)
        self._types[ir_name] = type_name
        self._versions[ir_name] = -1
        call_node = self._direct_call_expression(initializer_nodes[-1])
        if call_node is not None:
            if not self._supported_call_result_type(type_name):
                raise UnsupportedNode(
                    node, "only integer or value-record call results may initialize locals"
                )
            call, current, target = self._lower_call(
                call_node, environment, result_root=ir_name
            )
            assert target is not None
            current[name] = target
            self._locals.append(
                self._new_symbol(
                    ir_name,
                    type_name,
                    target,
                    self._location(node),
                    source_name=name,
                )
            )
            return [call], current
        target = self._next_version(ir_name)
        current[name] = target
        self._locals.append(
            self._new_symbol(
                ir_name,
                type_name,
                target,
                self._location(node),
                source_name=name,
            )
        )
        value = self._expression(initializer_nodes[-1], environment)
        if value.type != type_name:
            raise UnsupportedNode(node, "initializer type does not match local type")
        return [
            self._node("assign", self._location(node), target=target, expression=value)
        ], current

    def _lower_reference(
        self,
        node: Mapping[str, Any],
        environment: Mapping[str, str],
        name: str,
        raw_type_name: str,
    ) -> tuple[list[IRNode], dict[str, str]]:
        current = dict(environment)
        if self._loop_depth:
            raise UnsupportedNode(node, "references declared inside loops are unsupported")
        if not name:
            raise UnsupportedNode(node, "unnamed local reference is unsupported")
        if name == "result":
            raise UnsupportedNode(node, "reference name 'result' is reserved")
        if name in current:
            raise UnsupportedNode(node, f"shadowing variable {name!r} is unsupported")
        if re.search(r"\bvolatile\b", raw_type_name):
            raise UnsupportedNode(node, "volatile references are unsupported")
        if node.get("storageClass") == "static" or node.get("tls") is not None:
            raise UnsupportedNode(node, "static and thread_local references are unsupported")
        if "&&" in raw_type_name or raw_type_name.count("&") != 1:
            raise UnsupportedNode(node, "only local lvalue references are supported")
        referent_source = _normalize_value_type(raw_type_name.rsplit("&", 1)[0])
        if "*" in referent_source or "[" in referent_source:
            raise UnsupportedNode(node, "pointer and array references are unsupported")
        type_name = self._resolve_source_type(referent_source)
        if not self._supported_value_type(type_name):
            raise UnsupportedNode(
                node, f"reference target type {referent_source!r} is unsupported"
            )
        initializer_nodes = [
            child for child in node.get("inner", []) if isinstance(child, dict)
        ]
        if len(initializer_nodes) != 1:
            raise UnsupportedNode(node, "reference must have exactly one initializer")
        root, steps, target_mutable = self._lvalue_path(
            initializer_nodes[0], current
        )
        if root not in current or self._is_reference_value(current[root]):
            raise UnsupportedNode(node, "reference target must be a live owned local")
        if any(not isinstance(step, str) for step in steps):
            raise UnsupportedNode(
                node, "array-element reference targets are outside the reviewed subset"
            )
        target_root = Expr.variable(
            current[root], self._types[self._version_base(current[root])]
        )
        target_expression = self._path_expression(target_root, steps, node)
        if target_expression.type != type_name:
            raise UnsupportedNode(node, "reference initializer type does not match")
        mutable = re.search(r"\bconst\b", raw_type_name) is None
        if mutable and not target_mutable:
            raise UnsupportedNode(node, "mutable reference cannot target const access")
        target_ir = self._version_base(current[root])
        field_path = tuple(str(step) for step in steps)
        for value in current.values():
            if not self._is_reference_value(value):
                continue
            existing = self._reference_targets[value.removeprefix(_REFERENCE_SENTINEL)]
            if existing.root != root:
                continue
            common = min(len(existing.path), len(field_path))
            if existing.path[:common] == field_path[:common]:
                raise UnsupportedNode(
                    node, "reference target overlaps an existing live reference"
                )
        self._reference_index += 1
        reference_id = f"{self._current_function}.r{self._reference_index:04d}"
        target = _ReferenceTarget(
            reference_id,
            root,
            field_path,
            type_name,
            mutable and target_mutable,
        )
        self._reference_targets[reference_id] = target
        current[name] = _REFERENCE_SENTINEL + reference_id
        self._references.append(
            ReferenceBinding(
                id=reference_id,
                name=name,
                type=type_name,
                target=target_ir,
                path=tuple(
                    ReferencePathStep("field", field_name)
                    for field_name in field_path
                ),
                mutable=target.mutable,
                location=self._location(node),
            )
        )
        return [], current

    @staticmethod
    def _is_reference_value(value: str) -> bool:
        return value.startswith(_REFERENCE_SENTINEL)

    def _lower_if(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> tuple[list[IRNode], dict[str, str], bool]:
        if node.get("hasInit") or node.get("hasVar"):
            raise UnsupportedNode(node, "if initializers and condition variables are unsupported")
        inner = [child for child in node.get("inner", []) if isinstance(child, dict)]
        has_else = bool(node.get("hasElse"))
        expected = 3 if has_else else 2
        if len(inner) != expected:
            raise UnsupportedNode(node, "unsupported Clang if-statement shape")
        condition = self._expression(inner[0], environment)
        if condition.type != "bool":
            raise UnsupportedNode(node, "if condition must be boolean")

        branch_id = self._new_node_id()
        then_nodes, then_env, then_falls = self._lower_statement(
            inner[1], dict(environment)
        )
        if has_else:
            else_nodes, else_env, else_falls = self._lower_statement(
                inner[2], dict(environment)
            )
        else:
            else_nodes, else_env, else_falls = [], dict(environment), True

        output = dict(environment)
        merges: list[IRNode] = []
        if then_falls and else_falls:
            for name in sorted(environment):
                true_name = then_env.get(name, environment[name])
                false_name = else_env.get(name, environment[name])
                if true_name == false_name:
                    output[name] = true_name
                    continue
                ir_name = self._version_base(environment[name])
                target = self._next_version(ir_name)
                output[name] = target
                merges.append(
                    self._node(
                        "merge",
                        self._location(node),
                        target=target,
                        incoming_true=Expr.variable(true_name, self._types[ir_name]),
                        incoming_false=Expr.variable(false_name, self._types[ir_name]),
                    )
                )
        elif then_falls:
            output = {name: then_env[name] for name in environment}
        elif else_falls:
            output = {name: else_env[name] for name in environment}

        branch = IRNode(
            id=branch_id,
            kind="branch",
            location=self._location(node),
            expression=condition,
            then_body=tuple(then_nodes),
            else_body=tuple(else_nodes),
            merges=tuple(merges),
        )
        return [branch], output, then_falls or else_falls

    def _lower_while(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> tuple[list[IRNode], dict[str, str], bool]:
        if node.get("hasVar"):
            raise UnsupportedNode(
                node, "while condition variables are unsupported"
            )
        inner = [
            child for child in node.get("inner", []) if isinstance(child, dict)
        ]
        if len(inner) != 2:
            raise UnsupportedNode(node, "unsupported Clang while-statement shape")

        assigned = self._assigned_names(inner[1], environment)
        modified_names = sorted(name for name in assigned if name in environment)
        head_environment = dict(environment)
        for name in modified_names:
            ir_name = self._version_base(environment[name])
            head_environment[name] = self._next_version(ir_name)

        begin_byte_offset = declaration_begin_offset(node)
        if begin_byte_offset is None:
            raise UnsupportedNode(node, "while statement has no source offset")
        statement_offset = self.unit.line_map.char_offset_from_byte_offset(
            begin_byte_offset
        )
        invariants, invariant_issues = invariants_before(
            self.unit.source,
            statement_offset,
            self.unit.line_map,
            {
                name: self._environment_type(name, environment)
                for name in environment
            },
            "WhileStmt",
        )
        self._consumed_contract_lines.update(
            invariant.location.line for invariant in invariants
        )
        self._consumed_contract_lines.update(
            issue.location.line for issue in invariant_issues
        )
        if invariant_issues:
            issue = invariant_issues[0]
            raise UnsupportedNode(
                node,
                f"invariant at {issue.location.line}:{issue.location.column}: "
                f"{issue.reason}",
            )

        replacements = {
            name: self._environment_expression(name, head_environment)
            for name in head_environment
        }
        lowered_invariants = tuple(
            replace(
                invariant,
                expression=invariant.expression.substitute(replacements),
            )
            for invariant in invariants
        )
        condition = self._expression(inner[0], head_environment)
        if condition.type != "bool":
            raise UnsupportedNode(node, "while condition must be boolean")

        loop_id = self._new_node_id()
        self._loop_depth += 1
        try:
            body_nodes, body_environment, _ = self._lower_statement(
                inner[1], head_environment
            )
        finally:
            self._loop_depth -= 1
        output = dict(environment)
        loop_variables: list[LoopVariable] = []
        for name in modified_names:
            ir_name = self._version_base(environment[name])
            exit_name = self._next_version(ir_name)
            output[name] = exit_name
            loop_variables.append(
                LoopVariable(
                    name=ir_name,
                    type=self._types[ir_name],
                    entry=environment[name],
                    head=head_environment[name],
                    back_edge=body_environment.get(name, head_environment[name]),
                    exit=exit_name,
                )
            )

        loop = IRNode(
            id=loop_id,
            kind="loop",
            location=self._location(node),
            expression=condition,
            invariants=lowered_invariants,
            loop_variables=tuple(loop_variables),
            body=tuple(body_nodes),
            termination="non_goal",
        )
        return [loop], output, True

    def _environment_type(
        self, name: str, environment: Mapping[str, str]
    ) -> str:
        value = environment[name]
        if self._is_reference_value(value):
            return self._reference_targets[
                value.removeprefix(_REFERENCE_SENTINEL)
            ].type
        return self._types[self._version_base(value)]

    def _environment_expression(
        self, name: str, environment: Mapping[str, str]
    ) -> Expr:
        value = environment[name]
        if not self._is_reference_value(value):
            return Expr.variable(value, self._types[self._version_base(value)])
        target = self._reference_targets[value.removeprefix(_REFERENCE_SENTINEL)]
        root_value = environment.get(target.root)
        if root_value is None or self._is_reference_value(root_value):
            raise RuntimeError("reference target is outside its lexical lifetime")
        result = Expr.variable(
            root_value, self._types[self._version_base(root_value)]
        )
        for field_name in target.path:
            result = Expr.project(result, field_name)
        return result

    def _assigned_names(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> set[str]:
        assigned: set[str] = set()
        if node.get("kind") == "BinaryOperator" and node.get("opcode") == "=":
            inner = [
                child for child in node.get("inner", []) if isinstance(child, dict)
            ]
            if inner:
                try:
                    assigned.add(self._lvalue_root_name(inner[0], environment))
                except UnsupportedNode:
                    pass
        for child in node.get("inner", []):
            if isinstance(child, dict):
                assigned.update(self._assigned_names(child, environment))
        return assigned

    def _expression(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> Expr:
        self._reject_macro(node)
        kind = str(node.get("kind", ""))
        if kind in TRANSPARENT_EXPR_KINDS:
            return self._expression(self._inner(node, 1)[0], environment)
        if kind == "ImplicitCastExpr":
            inner = self._inner(node, 1)[0]
            cast_kind = str(node.get("castKind", ""))
            value = self._expression(inner, environment)
            if cast_kind in {"LValueToRValue", "NoOp"}:
                return value
            destination_source = _normalize_value_type(_qual_type(node))
            destination = self._resolve_source_type(destination_source)
            if cast_kind == "IntegralToBoolean" and is_fixed_integer_type(value.type):
                return Expr.binary(
                    "!=", value, Expr.integer(0, value.type), "bool"
                )
            if cast_kind == "IntegralCast" and (
                (is_fixed_integer_type(value.type) and is_fixed_integer_type(destination))
                or (value.type == "bool" and is_fixed_integer_type(destination))
            ):
                return Expr.cast(value, destination)
            raise UnsupportedNode(node, f"implicit cast {cast_kind!r} is unsupported")
        if kind == "IntegerLiteral":
            source_type = _normalize_value_type(_qual_type(node))
            type_name = SOURCE_TYPE_MAP.get(source_type)
            if type_name is None or not is_fixed_integer_type(type_name):
                raise UnsupportedNode(
                    node, f"integer literal type {source_type!r} is unsupported"
                )
            value = int(str(node.get("value", "0")))
            if not integer_type(type_name).contains(value):
                raise UnsupportedNode(node, "integer literal is outside its resolved type")
            return Expr.integer(value, type_name)
        if kind == "CXXBoolLiteralExpr":
            return Expr.boolean(bool(node.get("value")))
        if kind == "InitListExpr":
            source_type = _normalize_value_type(_qual_type(node))
            record_profile = self._record_types.get(source_type)
            children = [
                child for child in node.get("inner", []) if isinstance(child, dict)
            ]
            if record_profile is not None:
                if len(children) != len(record_profile.fields) or any(
                    child.get("kind") == "ImplicitValueInitExpr"
                    for child in children
                ):
                    raise UnsupportedNode(
                        node,
                        "record initializer must explicitly initialize every field",
                    )
                values = tuple(
                    self._expression(child, environment) for child in children
                )
                try:
                    return Expr.record(values, record_profile.name)
                except ValueError as error:
                    raise UnsupportedNode(node, str(error)) from error
            try:
                profile = parse_source_array_type(source_type, SOURCE_TYPE_MAP)
            except ValueError as error:
                raise UnsupportedNode(node, str(error)) from error
            if profile is None:
                raise UnsupportedNode(node, "initializer list type is unsupported")
            if len(children) != profile.length or any(
                child.get("kind") == "ImplicitValueInitExpr" for child in children
            ):
                raise UnsupportedNode(
                    node, "array initializer must explicitly initialize every element"
                )
            values = tuple(
                self._expression(child, environment) for child in children
            )
            if any(value.type != profile.element_type for value in values):
                raise UnsupportedNode(
                    node, "array initializer element type is inconsistent"
                )
            return Expr.array(values, profile.element_type)
        if kind == "CXXConstructExpr":
            destination = self._resolve_source_type(
                _normalize_value_type(_qual_type(node))
            )
            children = [
                child for child in node.get("inner", []) if isinstance(child, dict)
            ]
            if not is_record_type(destination) or len(children) != 1:
                raise UnsupportedNode(
                    node, "only exact value-record copy construction is supported"
                )
            value = self._expression(children[0], environment)
            if value.type != destination:
                raise UnsupportedNode(node, "record copy changes the value type")
            return value
        if kind in {"ArraySubscriptExpr", "MemberExpr"}:
            name, steps, _ = self._lvalue_path(node, environment)
            if name not in environment:
                raise UnsupportedNode(
                    node, f"reference to non-local aggregate {name!r}"
                )
            versioned = environment[name]
            root = Expr.variable(
                versioned, self._types[self._version_base(versioned)]
            )
            return self._path_expression(root, steps, node)
        if kind == "DeclRefExpr":
            name = self._decl_name(node)
            if name not in environment:
                raise UnsupportedNode(node, f"reference to non-local name {name!r}")
            return self._environment_expression(name, environment)
        if kind == "UnaryOperator":
            operator = str(node.get("opcode", ""))
            value = self._expression(self._inner(node, 1)[0], environment)
            if operator == "+" and is_fixed_integer_type(value.type):
                return value
            if operator == "-" and is_fixed_integer_type(value.type):
                return Expr.unary("-", value, value.type)
            if operator == "~" and is_fixed_integer_type(value.type):
                result_source = _normalize_value_type(_qual_type(node))
                result_type = SOURCE_TYPE_MAP.get(result_source, result_source)
                if result_type != value.type:
                    raise UnsupportedNode(node, "bitwise complement type is inconsistent")
                return Expr.unary("~", value, value.type)
            if operator == "!" and value.type == "bool":
                return Expr.unary("!", value, "bool")
            raise UnsupportedNode(node, f"unary operator {operator!r} is unsupported")
        if kind == "BinaryOperator":
            operator = str(node.get("opcode", ""))
            if operator == "=":
                raise UnsupportedNode(node, "assignment expressions are unsupported")
            if operator not in {
                "+",
                "-",
                "*",
                "/",
                "%",
                "&",
                "|",
                "^",
                "<<",
                ">>",
                "==",
                "!=",
                "<",
                "<=",
                ">",
                ">=",
                "&&",
                "||",
            }:
                raise UnsupportedNode(node, f"binary operator {operator!r} is unsupported")
            left_node, right_node = self._inner(node, 2)
            left = self._expression(left_node, environment)
            right = self._expression(right_node, environment)
            if operator in {"+", "-", "*", "/", "%", "&", "|", "^"}:
                if (
                    not is_fixed_integer_type(left.type)
                    or left.type != right.type
                ):
                    raise UnsupportedNode(
                        node, f"{operator} requires matching fixed-width operands"
                    )
                result_source = _normalize_value_type(_qual_type(node))
                result_type = SOURCE_TYPE_MAP.get(result_source, result_source)
                if result_type != left.type:
                    raise UnsupportedNode(node, "integer result type is inconsistent")
                return Expr.binary(operator, left, right, result_type)
            if operator in {"<<", ">>"}:
                if not (
                    is_fixed_integer_type(left.type)
                    and is_fixed_integer_type(right.type)
                ):
                    raise UnsupportedNode(
                        node, f"{operator} requires promoted fixed-width operands"
                    )
                result_source = _normalize_value_type(_qual_type(node))
                result_type = SOURCE_TYPE_MAP.get(result_source, result_source)
                if result_type != left.type:
                    raise UnsupportedNode(node, "shift result type is inconsistent")
                return Expr.binary(operator, left, right, result_type)
            if operator in {"&&", "||"}:
                if left.type != "bool" or right.type != "bool":
                    raise UnsupportedNode(node, f"{operator} requires boolean operands")
                return Expr.binary(operator, left, right, "bool")
            if operator in {"<", "<=", ">", ">="}:
                if (
                    not is_fixed_integer_type(left.type)
                    or left.type != right.type
                ):
                    raise UnsupportedNode(
                        node, f"{operator} requires matching fixed-width operands"
                    )
            elif left.type != right.type:
                raise UnsupportedNode(node, f"{operator} operands have different types")
            return Expr.binary(operator, left, right, "bool")
        if kind == "CallExpr":
            raise UnsupportedNode(node, "calls nested inside expressions are unsupported")
        raise UnsupportedNode(node, f"expression kind {kind or '<unknown>'} is unsupported")

    def _direct_call_expression(
        self, node: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        current = node
        while str(current.get("kind", "")) in TRANSPARENT_EXPR_KINDS:
            current = self._inner(current, 1)[0]
        if (
            current.get("kind") == "ImplicitCastExpr"
            and current.get("castKind") == "NoOp"
        ):
            current = self._inner(current, 1)[0]
        return current if current.get("kind") == "CallExpr" else None

    def _resolve_call(
        self, node: Mapping[str, Any]
    ) -> tuple[str, _FunctionProfile | None, list[Mapping[str, Any]]]:
        inner = [child for child in node.get("inner", []) if isinstance(child, dict)]
        if not inner:
            raise UnsupportedNode(node, "call has no callee")
        callee_node = self._strip_expr(inner[0])
        if callee_node.get("kind") != "DeclRefExpr":
            raise UnsupportedNode(node, "indirect and member calls are unsupported")
        callee = self._decl_name(callee_node)
        profile = None
        referenced = callee_node.get("referencedDecl")
        if isinstance(referenced, dict):
            declaration_id = referenced.get("id")
            if declaration_id is not None:
                key = str(declaration_id)
                callee = self._function_links.get(key, callee)
                profile = self._function_profile_ids.get(key)
        if profile is None:
            profile = next(
                (
                    candidate
                    for candidate in self._function_profiles.get(callee, ())
                    if len(candidate.parameters) == len(inner) - 1
                ),
                None,
            )
        return callee, profile, inner[1:]

    @staticmethod
    def _paths_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
        common = min(len(left), len(right))
        return left[:common] == right[:common]

    def _lower_call(
        self,
        node: Mapping[str, Any],
        environment: Mapping[str, str],
        *,
        result_root: str | None,
    ) -> tuple[IRNode, dict[str, str], str | None]:
        callee, profile, argument_nodes = self._resolve_call(node)
        current = dict(environment)
        if profile is None:
            arguments = tuple(
                self._expression(argument, environment) for argument in argument_nodes
            )
            parameter_profiles = tuple(
                _ParameterProfile("", argument.type, "value") for argument in arguments
            )
            frame = None
        else:
            if len(profile.parameters) != len(argument_nodes):
                raise UnsupportedNode(node, "call argument count does not match declaration")
            parameter_profiles = profile.parameters
            try:
                frame = self._effective_frame(profile)
            except UnsupportedNode as error:
                raise UnsupportedNode(node, error.reason) from error
            lowered_arguments: list[Expr] = []
            reference_arguments: list[_ReferenceArgument | None] = []
            for parameter, argument_node in zip(parameter_profiles, argument_nodes):
                if parameter.passing == "value":
                    lowered_arguments.append(self._expression(argument_node, environment))
                    reference_arguments.append(None)
                    continue
                if parameter.passing not in {"const_reference", "mutable_reference"}:
                    raise UnsupportedNode(node, "unsupported reference parameter mode")
                root, raw_path, writable = self._lvalue_path(argument_node, environment)
                if root not in environment or self._is_reference_value(environment[root]):
                    raise UnsupportedNode(
                        argument_node, "reference argument must target a live owned local"
                    )
                if any(not isinstance(step, str) for step in raw_path):
                    raise UnsupportedNode(
                        argument_node, "array-element reference arguments are unsupported"
                    )
                path = tuple(str(step) for step in raw_path)
                root_value = Expr.variable(
                    environment[root],
                    self._types[self._version_base(environment[root])],
                )
                value = self._path_expression(root_value, path, argument_node)
                if value.type != parameter.type:
                    raise UnsupportedNode(node, "reference argument type does not match")
                if parameter.passing == "mutable_reference" and not writable:
                    raise UnsupportedNode(node, "mutable reference argument is const")
                lowered_arguments.append(value)
                reference_arguments.append(
                    _ReferenceArgument(root, path, value.type, writable)
                )
            arguments = tuple(lowered_arguments)
            live_references = [
                reference for reference in reference_arguments if reference is not None
            ]
            for index, reference in enumerate(live_references):
                for existing in live_references[:index]:
                    if reference.root == existing.root and self._paths_overlap(
                        reference.path, existing.path
                    ):
                        raise UnsupportedNode(
                            node, "overlapping reference arguments are unsupported"
                        )
            if live_references and frame is None:
                raise UnsupportedNode(
                    node, "reference call requires an explicit cs: modifies contract"
                )

        reference_by_name = {
            parameter.name: reference
            for parameter, reference in zip(
                parameter_profiles,
                reference_arguments if profile is not None else (),
            )
            if reference is not None
        }
        modified_by_root: dict[str, list[FrameLocation]] = {}
        root_sources: dict[str, str] = {}
        if frame is not None:
            for target in frame.targets:
                reference = reference_by_name.get(target.root)
                if reference is None:
                    raise UnsupportedNode(
                        node, "modifies target does not name a mutable reference argument"
                    )
                combined_path = reference.path + tuple(
                    step.value for step in target.path
                )
                root_value = Expr.variable(
                    environment[reference.root],
                    self._types[self._version_base(environment[reference.root])],
                )
                actual = self._path_expression(root_value, combined_path, node)
                if actual.type != target.type:
                    raise UnsupportedNode(node, "modifies target type does not match actual")
                root_ir = self._version_base(environment[reference.root])
                location = FrameLocation(
                    root_ir,
                    tuple(ReferencePathStep("field", step) for step in combined_path),
                    target.type,
                )
                modified_by_root.setdefault(root_ir, []).append(location)
                root_sources[root_ir] = reference.root
        effects: list[CallFrameEffect] = []
        for root_ir, locations in modified_by_root.items():
            for index, location in enumerate(locations):
                path = tuple(step.value for step in location.path)
                for existing in locations[:index]:
                    existing_path = tuple(step.value for step in existing.path)
                    if self._paths_overlap(path, existing_path):
                        raise UnsupportedNode(
                            node, "aliased modifies locations are unsupported"
                        )
            source_root = root_sources[root_ir]
            before = current[source_root]
            after = self._next_version(root_ir)
            current[source_root] = after
            effects.append(
                CallFrameEffect(
                    root_ir,
                    self._types[root_ir],
                    before,
                    after,
                    tuple(locations),
                )
            )

        post_arguments: list[Expr] = []
        if profile is not None and any(
            parameter.passing != "value" for parameter in parameter_profiles
        ):
            for parameter, before, reference in zip(
                parameter_profiles, arguments, reference_arguments
            ):
                if reference is None:
                    post_arguments.append(before)
                    continue
                root_value = Expr.variable(
                    current[reference.root],
                    self._types[self._version_base(current[reference.root])],
                )
                post_arguments.append(
                    self._path_expression(root_value, reference.path, node)
                )

        target = None
        return_type = self._function_return_types.get(callee)
        if result_root is not None:
            target_type = self._types[result_root]
            if (
                return_type is None
                or not self._supported_call_result_type(return_type)
                or target_type != return_type
            ):
                shown = return_type or "unknown"
                raise UnsupportedNode(
                    node,
                    f"assigned call result type {shown!r} does not match {target_type!r}",
                )
            target = self._next_version(result_root)
        return (
            self._node(
                "call",
                self._location(node),
                target=target,
                result_type=return_type if target is not None else None,
                callee=callee,
                arguments=arguments,
                post_arguments=tuple(post_arguments),
                frame_effects=tuple(effects),
            ),
            current,
            target,
        )
    def _strip_expr(self, node: Mapping[str, Any]) -> Mapping[str, Any]:
        current = node
        while str(current.get("kind", "")) in TRANSPARENT_EXPR_KINDS | {
            "ImplicitCastExpr"
        }:
            current = self._inner(current, 1)[0]
        return current

    def _lvalue_path(
        self,
        node: Mapping[str, Any],
        environment: Mapping[str, str],
    ) -> tuple[str, tuple[str | Expr, ...], bool]:
        current = node
        while str(current.get("kind", "")) in TRANSPARENT_EXPR_KINDS:
            current = self._inner(current, 1)[0]
        if current.get("kind") == "ImplicitCastExpr":
            if current.get("castKind") not in {"ArrayToPointerDecay", "NoOp"}:
                raise UnsupportedNode(
                    current,
                    f"lvalue cast {current.get('castKind')!r} is unsupported",
                )
            return self._lvalue_path(self._inner(current, 1)[0], environment)
        kind = current.get("kind")
        if kind == "DeclRefExpr":
            name = self._decl_name(current)
            value = environment.get(name)
            if value is not None and self._is_reference_value(value):
                target = self._reference_targets[
                    value.removeprefix(_REFERENCE_SENTINEL)
                ]
                return target.root, tuple(target.path), target.mutable
            return name, (), True
        if kind == "MemberExpr":
            if current.get("isArrow"):
                raise UnsupportedNode(current, "pointer member access is unsupported")
            base = self._inner(current, 1)[0]
            name, steps, writable = self._lvalue_path(base, environment)
            field_name = str(current.get("name", ""))
            if not field_name:
                raise UnsupportedNode(current, "unnamed member access is unsupported")
            return name, steps + (field_name,), writable
        if kind == "ArraySubscriptExpr":
            base, index_node = self._inner(current, 2)
            name, steps, writable = self._lvalue_path(base, environment)
            index = self._expression(index_node, environment)
            return name, steps + (index,), writable
        raise UnsupportedNode(
            current, "assignment target must be a direct owned-value path"
        )

    def _lvalue_root_name(
        self, node: Mapping[str, Any], environment: Mapping[str, str]
    ) -> str:
        return self._lvalue_path(node, environment)[0]

    @staticmethod
    def _path_expression(
        root: Expr,
        steps: tuple[str | Expr, ...],
        node: Mapping[str, Any],
    ) -> Expr:
        result = root
        try:
            for step in steps:
                result = (
                    Expr.project(result, step)
                    if isinstance(step, str)
                    else Expr.select(result, step)
                )
        except ValueError as error:
            raise UnsupportedNode(node, str(error)) from error
        return result

    @staticmethod
    def _replace_path(
        root: Expr,
        steps: tuple[str | Expr, ...],
        replacement: Expr,
        node: Mapping[str, Any],
    ) -> Expr:
        if not steps:
            return replacement
        step = steps[0]
        try:
            if isinstance(step, str):
                child = Expr.project(root, step)
                updated = SemanticLowerer._replace_path(
                    child, steps[1:], replacement, node
                )
                return Expr.update(root, step, updated)
            if len(steps) != 1:
                raise ValueError(
                    "arrays of aggregate elements are outside the reviewed subset"
                )
            return Expr.store(root, step, replacement)
        except ValueError as error:
            raise UnsupportedNode(node, str(error)) from error

    @staticmethod
    def _decl_name(node: Mapping[str, Any]) -> str:
        referenced = node.get("referencedDecl")
        if isinstance(referenced, dict) and referenced.get("name"):
            return str(referenced["name"])
        return str(node.get("name", ""))

    @staticmethod
    def _inner(node: Mapping[str, Any], count: int) -> list[Mapping[str, Any]]:
        children = [child for child in node.get("inner", []) if isinstance(child, dict)]
        if len(children) != count:
            raise UnsupportedNode(
                node, f"{node.get('kind', 'node')} expected {count} child nodes"
            )
        return children

    def _reject_macro(self, node: Mapping[str, Any]) -> None:
        if node_is_macro_expansion(node):
            raise UnsupportedNode(node, "macro-expanded semantic node is unsupported")

    def _location(self, node: Mapping[str, Any]) -> SourceLocation:
        offset = node_offset(node)
        return self.unit.line_map.location_from_byte_offset(
            offset if offset is not None else 0
        )

    def _end_location(self, node: Mapping[str, Any]) -> SourceLocation:
        offset = node_end_offset(node)
        return self.unit.line_map.location_from_byte_offset(
            offset if offset is not None else 0
        )

    def _new_symbol_name(self, source_name: str) -> str:
        occurrence = self._symbol_name_counts.get(source_name, 0) + 1
        self._symbol_name_counts[source_name] = occurrence
        return source_name if occurrence == 1 else f"{source_name}@{occurrence}"

    @staticmethod
    def _version_base(versioned_name: str) -> str:
        return versioned_name.rsplit("#", 1)[0]

    def _new_symbol(
        self,
        name: str,
        type_name: str,
        versioned: str,
        location: SourceLocation,
        source_name: str | None = None,
        passing: str | None = None,
    ) -> Symbol:
        self._symbol_index += 1
        return Symbol(
            id=f"{self._current_function}.s{self._symbol_index:04d}",
            name=name,
            type=type_name,
            versioned_name=versioned,
            location=location,
            source_name=source_name,
            passing=passing,
        )

    def _next_version(self, name: str) -> str:
        self._versions[name] += 1
        return f"{name}#{self._versions[name]}"

    def _new_node_id(self) -> str:
        self._node_index += 1
        return f"n{self._node_index:05d}"

    def _node(
        self,
        kind: str,
        location: SourceLocation,
        **kwargs: Any,
    ) -> IRNode:
        return IRNode(id=self._new_node_id(), kind=kind, location=location, **kwargs)

    def _unsupported(self, node: Mapping[str, Any], reason: str) -> IRNode:
        return self._node("unsupported", self._location(node), reason=reason)

    def _module_issue(self, location: SourceLocation, reason: str) -> IRNode:
        self._module_issue_index += 1
        return IRNode(
            id=f"u{self._module_issue_index:05d}",
            kind="unsupported",
            location=location,
            reason=reason,
        )
