"""Deterministic fact extraction from the isolated Clang JSON frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Iterable, Mapping

from .facts import (
    CallFact,
    DefinitionFact,
    FactIndex,
    FactLimitation,
    FactLocation,
    FactSource,
    FactSymbol,
    MutationFact,
    PurityFact,
    UseFact,
)
from .frontend import ClangJsonFrontend, FrontendUnit
from .lowering import (
    node_is_from_include,
    node_is_macro_expansion,
    node_offset,
    node_physical_file,
)


class FactExtractionError(RuntimeError):
    """Raised when an admitted AST cannot form a valid fact index."""


def _children(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inner = node.get("inner")
    if not isinstance(inner, list):
        return []
    return [child for child in inner if isinstance(child, Mapping)]


def _qual_type(node: Mapping[str, Any]) -> str:
    type_info = node.get("type")
    if not isinstance(type_info, Mapping):
        return ""
    value = type_info.get("qualType")
    return str(value) if value else ""


def _node_id(node: Mapping[str, Any]) -> str:
    value = node.get("id")
    return str(value) if value else ""


def _has_body(node: Mapping[str, Any]) -> bool:
    return any(child.get("kind") == "CompoundStmt" for child in _children(node))


def _body(node: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next(
        (
            child
            for child in _children(node)
            if child.get("kind") == "CompoundStmt"
        ),
        None,
    )


def _parameter_nodes(
    node: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    return [
        child
        for child in _children(node)
        if child.get("kind") == "ParmVarDecl"
    ]


def _walk(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def _first_offset(node: Mapping[str, Any]) -> int:
    offset = node_offset(node)
    return offset if offset is not None else 2**63 - 1


def _has_graph_relevant_initializer(node: Mapping[str, Any]) -> bool:
    relevant = {
        "CallExpr",
        "CXXConstructExpr",
        "CXXMemberCallExpr",
        "CXXNewExpr",
        "CXXOperatorCallExpr",
        "DeclRefExpr",
        "MemberExpr",
    }
    return any(
        child is not node and child.get("kind") in relevant
        for child in _walk(node)
    )


def _join_scope(scope: tuple[str, ...], name: str) -> str:
    return "::".join((*scope, name)) if scope else name


@dataclass(slots=True)
class _FunctionGroup:
    qualified_name: str
    name: str
    type: str
    linkage: str
    nodes: list[Mapping[str, Any]] = field(default_factory=list)
    declaration: FactLocation | None = None
    definition: FactLocation | None = None
    definition_node: Mapping[str, Any] | None = None
    symbol: FactSymbol | None = None


@dataclass(slots=True)
class _RecordGroup:
    qualified_name: str
    name: str
    nodes: list[Mapping[str, Any]] = field(default_factory=list)
    declaration: FactLocation | None = None
    definition: FactLocation | None = None
    definition_node: Mapping[str, Any] | None = None
    symbol: FactSymbol | None = None


@dataclass(slots=True)
class _VariableGroup:
    qualified_name: str
    name: str
    type: str
    linkage: str
    nodes: list[Mapping[str, Any]] = field(default_factory=list)
    declaration: FactLocation | None = None
    definition: FactLocation | None = None
    symbol: FactSymbol | None = None


class ClangFactExtractor:
    """Extract the D1 v0 world model from a real Clang JSON AST."""

    def __init__(self, clang: str | None = None) -> None:
        self.frontend = ClangJsonFrontend(clang)

    def extract_file(
        self,
        path: str | os.PathLike[str],
        *,
        display_path: str | None = None,
    ) -> FactIndex:
        unit = self.frontend.parse_file(path, display_path=display_path)
        return _FactExtraction(unit).run()

    def extract_source(
        self,
        source: str,
        display_path: str = "input.cpp",
    ) -> FactIndex:
        unit = self.frontend.parse_source(source, display_path)
        return _FactExtraction(unit).run()

    def extract_unit(self, unit: FrontendUnit) -> FactIndex:
        return _FactExtraction(unit).run()


def extract_facts(
    source: str,
    display_path: str = "input.cpp",
    *,
    clang: str | None = None,
) -> FactIndex:
    """Convenience entry point for in-memory C++17 source."""

    return ClangFactExtractor(clang).extract_source(source, display_path)


class _FactExtraction:

    def __init__(self, unit: FrontendUnit) -> None:
        self.unit = unit
        self.source = FactSource.from_text(unit.display_path, unit.source)
        self.functions: dict[tuple[str, str], _FunctionGroup] = {}
        self.records: dict[str, _RecordGroup] = {}
        self.globals: dict[tuple[str, str], _VariableGroup] = {}
        self.symbols: list[FactSymbol] = []
        self.clang_symbols: dict[str, FactSymbol] = {}
        self.field_nodes: list[tuple[_RecordGroup, Mapping[str, Any]]] = []
        self.local_nodes: list[
            tuple[_FunctionGroup, Mapping[str, Any]]
        ] = []
        self.definitions: dict[str, DefinitionFact] = {}
        self.uses: dict[str, UseFact] = {}
        self.calls: dict[str, CallFact] = {}
        self.mutations: dict[str, MutationFact] = {}
        self.limitations: dict[
            tuple[object, ...],
            FactLimitation,
        ] = {}
        self.virtual_method_ids: set[str] = set()

    def run(self) -> FactIndex:
        roots = self._source_roots()
        self._collect_top_level(roots, ())
        self._build_primary_symbols()
        self._build_owned_symbols()
        self._build_declaration_facts()
        self._extract_function_bodies()
        purity = self._derive_purity()
        return FactIndex.create(
            source=self.source,
            symbols=self.symbols,
            definitions=tuple(self.definitions.values()),
            uses=tuple(self.uses.values()),
            calls=tuple(self.calls.values()),
            mutations=tuple(self.mutations.values()),
            purity=purity,
            limitations=tuple(self.limitations.values()),
        )

    def _source_roots(self) -> list[Mapping[str, Any]]:
        roots: list[Mapping[str, Any]] = []
        current_file: str | None = None
        for child in _children(self.unit.ast):
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
                roots.append(child)
        return sorted(roots, key=_first_offset)

    def _location(self, node: Mapping[str, Any]) -> FactLocation:
        offset = node_offset(node)
        if offset is None:
            raise FactExtractionError(
                f"{node.get('kind', 'AST node')} has no source location"
            )
        location = self.unit.line_map.location_from_byte_offset(offset)
        return FactLocation(
            self.source.file,
            location.line,
            location.column,
        )

    def _collect_top_level(
        self,
        nodes: Iterable[Mapping[str, Any]],
        scope: tuple[str, ...],
    ) -> None:
        for node in sorted(nodes, key=_first_offset):
            kind = str(node.get("kind", ""))
            if node.get("isImplicit"):
                continue
            if node_is_macro_expansion(node):
                self._add_limitation(
                    "macro_location",
                    f"{kind or 'declaration'} uses a macro-expanded location",
                    None,
                    node,
                )
                continue
            if kind == "NamespaceDecl":
                name = str(node.get("name", ""))
                if not name:
                    self._add_limitation(
                        "unsupported_ast",
                        "anonymous namespaces are unsupported in fact extraction v0",
                        None,
                        node,
                    )
                    continue
                self._collect_top_level(_children(node), (*scope, name))
                continue
            if kind in {"LinkageSpecDecl", "ExportDecl"}:
                self._collect_top_level(_children(node), scope)
                continue
            if kind == "FunctionDecl":
                self._collect_function(node, scope)
                continue
            if kind in {"CXXRecordDecl", "RecordDecl"}:
                self._collect_record(node, scope)
                continue
            if kind == "VarDecl":
                self._collect_global(node, scope)
                continue
            if kind in {"EmptyDecl", "StaticAssertDecl"}:
                continue
            self._add_limitation(
                "unsupported_ast",
                f"top-level {kind or 'unknown node'} is unsupported",
                None,
                node,
            )

    def _collect_function(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
    ) -> None:
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name:
            self._add_limitation(
                "unsupported_ast",
                "function declarations require a name and canonical type",
                None,
                node,
            )
            return
        qualified = _join_scope(scope, name)
        key = (qualified, type_name)
        linkage = (
            "internal"
            if node.get("storageClass") == "static"
            else "external"
        )
        group = self.functions.get(key)
        if group is None:
            group = _FunctionGroup(
                qualified,
                name,
                type_name,
                linkage,
            )
            self.functions[key] = group
        elif group.linkage != linkage:
            self._add_limitation(
                "unsupported_ast",
                f"inconsistent linkage for function {qualified}",
                None,
                node,
            )
        group.nodes.append(node)
        location = self._location(node)
        if (
            group.declaration is None
            or location < group.declaration
        ):
            group.declaration = location
        if _has_body(node):
            if group.definition_node is not None:
                self._add_limitation(
                    "unsupported_ast",
                    f"multiple definitions of function {qualified}",
                    None,
                    node,
                )
            else:
                group.definition = location
                group.definition_node = node

    def _collect_record(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
    ) -> None:
        name = str(node.get("name", ""))
        if not name:
            self._add_limitation(
                "unsupported_ast",
                "anonymous records are unsupported in fact extraction v0",
                None,
                node,
            )
            return
        qualified = _join_scope(scope, name)
        group = self.records.get(qualified)
        if group is None:
            group = _RecordGroup(qualified, name)
            self.records[qualified] = group
        group.nodes.append(node)
        location = self._location(node)
        if group.declaration is None or location < group.declaration:
            group.declaration = location
        if node.get("completeDefinition"):
            if group.definition_node is not None:
                self._add_limitation(
                    "unsupported_ast",
                    f"multiple definitions of record {qualified}",
                    None,
                    node,
                )
            else:
                group.definition = location
                group.definition_node = node

    def _collect_global(
        self,
        node: Mapping[str, Any],
        scope: tuple[str, ...],
    ) -> None:
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name:
            self._add_limitation(
                "unsupported_ast",
                "global variables require a name and canonical type",
                None,
                node,
            )
            return
        qualified = _join_scope(scope, name)
        key = (qualified, type_name)
        linkage = (
            "internal"
            if node.get("storageClass") == "static"
            else "external"
        )
        group = self.globals.get(key)
        if group is None:
            group = _VariableGroup(
                qualified,
                name,
                type_name,
                linkage,
            )
            self.globals[key] = group
        group.nodes.append(node)
        location = self._location(node)
        if group.declaration is None or location < group.declaration:
            group.declaration = location
        if node.get("storageClass") != "extern":
            if group.definition is not None:
                self._add_limitation(
                    "unsupported_ast",
                    f"multiple definitions of global {qualified}",
                    None,
                    node,
                )
            else:
                group.definition = location

    def _add_limitation(
        self,
        code: str,
        message: str,
        context: str | None,
        node: Mapping[str, Any] | None,
    ) -> None:
        location: FactLocation | None = None
        if node is not None and node_offset(node) is not None:
            location = self._location(node)
        limitation = FactLimitation(
            code,
            message,
            context,
            location,
        )
        self.limitations[limitation.sort_key()] = limitation

    def _register(self, node: Mapping[str, Any], symbol: FactSymbol) -> None:
        identity = _node_id(node)
        if identity:
            existing = self.clang_symbols.get(identity)
            if existing is not None and existing.id != symbol.id:
                raise FactExtractionError(
                    "one Clang declaration mapped to two public symbols"
                )
            self.clang_symbols[identity] = symbol

    def _build_primary_symbols(self) -> None:
        for qualified in sorted(self.records):
            group = self.records[qualified]
            if group.declaration is None:
                raise FactExtractionError("record declaration location is missing")
            group.symbol = FactSymbol.create(
                kind="record",
                name=group.name,
                qualified_name=group.qualified_name,
                type=f"record {group.qualified_name}",
                linkage="external",
                owner=None,
                declaration=group.declaration,
                definition=group.definition,
            )
            self.symbols.append(group.symbol)
            for node in group.nodes:
                self._register(node, group.symbol)

        for key in sorted(self.functions):
            group = self.functions[key]
            if group.declaration is None:
                raise FactExtractionError(
                    "function declaration location is missing"
                )
            group.symbol = FactSymbol.create(
                kind="function",
                name=group.name,
                qualified_name=group.qualified_name,
                type=group.type,
                linkage=group.linkage,
                owner=None,
                declaration=group.declaration,
                definition=group.definition,
            )
            self.symbols.append(group.symbol)
            for node in group.nodes:
                self._register(node, group.symbol)
            if group.definition_node is None:
                self._add_limitation(
                    "unsupported_ast",
                    (
                        f"function {group.qualified_name} has no "
                        "main-file definition"
                    ),
                    group.symbol.id,
                    group.nodes[0],
                )

        for key in sorted(self.globals):
            group = self.globals[key]
            if group.declaration is None:
                raise FactExtractionError(
                    "global declaration location is missing"
                )
            group.symbol = FactSymbol.create(
                kind="variable",
                name=group.name,
                qualified_name=group.qualified_name,
                type=group.type,
                linkage=group.linkage,
                owner=None,
                declaration=group.declaration,
                definition=group.definition,
            )
            self.symbols.append(group.symbol)
            for node in group.nodes:
                self._register(node, group.symbol)
                if _has_graph_relevant_initializer(node):
                    self._add_limitation(
                        "unsupported_ast",
                        (
                            f"global initializer for {group.qualified_name} "
                            "has no function context in fact extraction v0"
                        ),
                        group.symbol.id,
                        node,
                    )

    def _build_owned_symbols(self) -> None:
        for qualified in sorted(self.records):
            group = self.records[qualified]
            if group.symbol is None or group.definition_node is None:
                continue
            for child in _children(group.definition_node):
                kind = str(child.get("kind", ""))
                if child.get("isImplicit"):
                    continue
                if kind == "FieldDecl":
                    self._build_field(group, child)
                elif kind in {
                    "CXXMethodDecl",
                    "CXXConstructorDecl",
                    "CXXConversionDecl",
                    "CXXDestructorDecl",
                }:
                    method_id = _node_id(child)
                    if child.get("virtual") and method_id:
                        self.virtual_method_ids.add(method_id)
                    code = (
                        "virtual_dispatch"
                        if child.get("virtual")
                        else "unsupported_ast"
                    )
                    self._add_limitation(
                        code,
                        (
                            f"record member {child.get('name', kind)} "
                            "is outside fact extraction v0"
                        ),
                        group.symbol.id,
                        child,
                    )
                elif kind not in {
                    "AccessSpecDecl",
                    "CXXRecordDecl",
                    "FriendDecl",
                    "StaticAssertDecl",
                }:
                    self._add_limitation(
                        "unsupported_ast",
                        f"record child {kind or 'unknown node'} is unsupported",
                        group.symbol.id,
                        child,
                    )

        for key in sorted(self.functions):
            group = self.functions[key]
            if group.symbol is None:
                continue
            representative = group.definition_node or group.nodes[0]
            selected = _parameter_nodes(representative)
            for index, parameter in enumerate(selected):
                self._build_parameter(group, parameter, index)
            for node in group.nodes:
                for index, parameter in enumerate(_parameter_nodes(node)):
                    if index >= len(selected):
                        self._add_limitation(
                            "unsupported_ast",
                            (
                                f"inconsistent parameter list for "
                                f"{group.qualified_name}"
                            ),
                            group.symbol.id,
                            parameter,
                        )
                        continue
                    selected_id = _node_id(selected[index])
                    selected_symbol = self.clang_symbols.get(selected_id)
                    if selected_symbol is not None:
                        self._register(parameter, selected_symbol)

            if group.definition_node is not None:
                body = _body(group.definition_node)
                if body is not None:
                    for local in self._body_variable_nodes(body):
                        self._build_local(group, local)

    def _build_field(
        self,
        group: _RecordGroup,
        node: Mapping[str, Any],
    ) -> None:
        if group.symbol is None:
            raise FactExtractionError("field owner is missing")
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name:
            self._add_limitation(
                "unsupported_ast",
                "record fields require a name and canonical type",
                group.symbol.id,
                node,
            )
            return
        location = self._location(node)
        symbol = FactSymbol.create(
            kind="field",
            name=name,
            qualified_name=f"{group.qualified_name}::{name}",
            type=type_name,
            linkage="none",
            owner=group.symbol.id,
            declaration=location,
            definition=location,
        )
        self.symbols.append(symbol)
        self._register(node, symbol)
        self.field_nodes.append((group, node))

    def _build_parameter(
        self,
        group: _FunctionGroup,
        node: Mapping[str, Any],
        index: int,
    ) -> None:
        if group.symbol is None:
            raise FactExtractionError("parameter owner is missing")
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name:
            self._add_limitation(
                "unsupported_ast",
                (
                    f"parameter {index} of {group.qualified_name} "
                    "requires a name and canonical type"
                ),
                group.symbol.id,
                node,
            )
            return
        location = self._location(node)
        symbol = FactSymbol.create(
            kind="parameter",
            name=name,
            qualified_name=(
                f"{group.qualified_name}::{name}@parameter:{index}"
            ),
            type=type_name,
            linkage="none",
            owner=group.symbol.id,
            declaration=location,
            definition=location,
        )
        self.symbols.append(symbol)
        self._register(node, symbol)

    def _body_variable_nodes(
        self,
        node: Mapping[str, Any],
    ) -> Iterable[Mapping[str, Any]]:
        for child in _children(node):
            kind = str(child.get("kind", ""))
            if kind in {
                "LambdaExpr",
                "BlockDecl",
                "FunctionDecl",
                "CXXRecordDecl",
                "RecordDecl",
            }:
                continue
            if kind == "VarDecl":
                yield child
                continue
            yield from self._body_variable_nodes(child)

    def _build_local(
        self,
        group: _FunctionGroup,
        node: Mapping[str, Any],
    ) -> None:
        if group.symbol is None:
            raise FactExtractionError("local owner is missing")
        if node_is_macro_expansion(node):
            self._add_limitation(
                "macro_location",
                "local declaration uses a macro-expanded location",
                group.symbol.id,
                node,
            )
            return
        name = str(node.get("name", ""))
        type_name = _qual_type(node)
        if not name or not type_name:
            self._add_limitation(
                "unsupported_ast",
                "local variables require a name and canonical type",
                group.symbol.id,
                node,
            )
            return
        location = self._location(node)
        symbol = FactSymbol.create(
            kind="variable",
            name=name,
            qualified_name=(
                f"{group.qualified_name}::{name}"
                f"@{location.line}:{location.column}"
            ),
            type=type_name,
            linkage="none",
            owner=group.symbol.id,
            declaration=location,
            definition=location,
        )
        self.symbols.append(symbol)
        self._register(node, symbol)
        self.local_nodes.append((group, node))

    def _build_declaration_facts(self) -> None:
        for group in self.records.values():
            if group.symbol is None:
                continue
            location = group.definition or group.declaration
            if location is None:
                raise FactExtractionError("record fact location is missing")
            self._add_definition(
                group.symbol.id,
                None,
                "definition" if group.definition is not None else "declaration",
                location,
            )

        for group in self.functions.values():
            if group.symbol is None:
                continue
            location = group.definition or group.declaration
            if location is None:
                raise FactExtractionError("function fact location is missing")
            self._add_definition(
                group.symbol.id,
                None,
                "definition" if group.definition is not None else "declaration",
                location,
            )

        for group in self.globals.values():
            if group.symbol is None:
                continue
            location = group.definition or group.declaration
            if location is None:
                raise FactExtractionError("global fact location is missing")
            kind = (
                "initialization"
                if any(node.get("init") for node in group.nodes)
                else (
                    "definition"
                    if group.definition is not None
                    else "declaration"
                )
            )
            self._add_definition(
                group.symbol.id,
                None,
                kind,
                location,
            )

        for group, node in self.field_nodes:
            symbol = self.clang_symbols.get(_node_id(node))
            if symbol is not None:
                self._add_definition(
                    symbol.id,
                    None,
                    "declaration",
                    symbol.declaration,
                )

        for symbol in self.symbols:
            if symbol.kind == "parameter":
                self._add_definition(
                    symbol.id,
                    symbol.owner,
                    "parameter",
                    symbol.declaration,
                )

        for group, node in self.local_nodes:
            if group.symbol is None:
                continue
            symbol = self.clang_symbols.get(_node_id(node))
            if symbol is None:
                continue
            initialized = bool(node.get("init")) or bool(_children(node))
            self._add_definition(
                symbol.id,
                group.symbol.id,
                "initialization" if initialized else "declaration",
                symbol.declaration,
            )
            if initialized:
                self._add_mutation(
                    group.symbol.id,
                    symbol.id,
                    "initialization",
                    symbol.declaration,
                )

    def _add_definition(
        self,
        symbol: str,
        context: str | None,
        kind: str,
        location: FactLocation,
    ) -> None:
        fact = DefinitionFact.create(
            symbol=symbol,
            context=context,
            kind=kind,
            location=location,
        )
        self.definitions[fact.id] = fact

    def _add_use(
        self,
        symbol: str,
        context: str,
        kind: str,
        location: FactLocation,
    ) -> None:
        fact = UseFact.create(
            symbol=symbol,
            context=context,
            kind=kind,
            location=location,
        )
        self.uses[fact.id] = fact

    def _add_call(
        self,
        caller: str,
        callee: str,
        location: FactLocation,
    ) -> None:
        fact = CallFact.create(
            caller=caller,
            callee=callee,
            kind="direct",
            location=location,
        )
        self.calls[fact.id] = fact

    def _add_mutation(
        self,
        context: str,
        target: str,
        kind: str,
        location: FactLocation,
    ) -> None:
        fact = MutationFact.create(
            context=context,
            target=target,
            kind=kind,
            location=location,
        )
        self.mutations[fact.id] = fact

    def _extract_function_bodies(self) -> None:
        for key in sorted(self.functions):
            group = self.functions[key]
            if group.symbol is None or group.definition_node is None:
                continue
            body = _body(group.definition_node)
            if body is not None:
                self._visit(body, group.symbol.id)

    def _visit(
        self,
        node: Mapping[str, Any],
        function: str,
    ) -> None:
        kind = str(node.get("kind", ""))
        if node_is_macro_expansion(node):
            self._add_limitation(
                "macro_location",
                f"{kind or 'expression'} uses a macro-expanded location",
                function,
                node,
            )
            return

        if kind == "VarDecl":
            for child in _children(node):
                self._visit(child, function)
            return

        if kind == "BinaryOperator" and node.get("opcode") == "=":
            children = _children(node)
            if len(children) != 2:
                self._unsupported_expression(node, function)
                return
            self._handle_target(
                children[0],
                function,
                "write",
                "assignment",
            )
            self._visit(children[1], function)
            return

        if kind == "CompoundAssignOperator":
            children = _children(node)
            if len(children) != 2:
                self._unsupported_expression(node, function)
                return
            self._handle_target(
                children[0],
                function,
                "read_write",
                "compound_assignment",
            )
            self._visit(children[1], function)
            return

        if kind == "UnaryOperator" and node.get("opcode") in {"++", "--"}:
            children = _children(node)
            if len(children) != 1:
                self._unsupported_expression(node, function)
                return
            mutation_kind = (
                "increment" if node.get("opcode") == "++" else "decrement"
            )
            self._handle_target(
                children[0],
                function,
                "read_write",
                mutation_kind,
            )
            return

        if kind in {"CallExpr", "CXXMemberCallExpr"}:
            self._visit_call(node, function)
            return

        if kind == "DeclRefExpr":
            self._visit_decl_ref(node, function, "read")
            return

        if kind == "MemberExpr":
            self._visit_member(node, function, "read")
            return

        if kind == "ArraySubscriptExpr":
            self._add_limitation(
                "unsupported_ast",
                "array subscripting is outside fact extraction v0",
                function,
                node,
            )
            for child in _children(node):
                self._visit(child, function)
            return

        if kind in {
            "BlockExpr",
            "CXXDeleteExpr",
            "CXXNewExpr",
            "CXXOperatorCallExpr",
            "GCCAsmStmt",
            "LambdaExpr",
            "MSAsmStmt",
        }:
            self._unsupported_expression(node, function)
            return

        for child in _children(node):
            self._visit(child, function)

    def _unsupported_expression(
        self,
        node: Mapping[str, Any],
        function: str,
    ) -> None:
        self._add_limitation(
            "unsupported_ast",
            (
                f"{node.get('kind', 'expression')} is outside "
                "fact extraction v0"
            ),
            function,
            node,
        )

    def _visit_call(
        self,
        node: Mapping[str, Any],
        function: str,
    ) -> None:
        children = _children(node)
        if not children:
            self._add_limitation(
                "unresolved_symbol",
                "call expression has no callable child",
                function,
                node,
            )
            return

        callee = children[0]
        if node.get("kind") == "CXXMemberCallExpr":
            member = next(
                (
                    item
                    for item in _walk(callee)
                    if item.get("kind") == "MemberExpr"
                ),
                None,
            )
            member_id = (
                str(member.get("referencedMemberDecl", ""))
                if member is not None
                else ""
            )
            code = (
                "virtual_dispatch"
                if member_id in self.virtual_method_ids
                else "unsupported_ast"
            )
            self._add_limitation(
                code,
                (
                    "virtual member dispatch is unsupported"
                    if code == "virtual_dispatch"
                    else "member calls are outside fact extraction v0"
                ),
                function,
                node,
            )
        else:
            references = [
                item
                for item in _walk(callee)
                if item.get("kind") == "DeclRefExpr"
            ]
            function_ref = next(
                (
                    item
                    for item in references
                    if isinstance(item.get("referencedDecl"), Mapping)
                    and item["referencedDecl"].get("kind")
                    == "FunctionDecl"
                ),
                None,
            )
            if function_ref is not None:
                referenced = function_ref["referencedDecl"]
                symbol = self.clang_symbols.get(
                    str(referenced.get("id", ""))
                )
                if symbol is not None and symbol.kind == "function":
                    self._add_call(
                        function,
                        symbol.id,
                        self._location(node),
                    )
                else:
                    self._add_limitation(
                        "unresolved_symbol",
                        (
                            f"direct callee {referenced.get('name', '<unknown>')} "
                            "is outside the main-file index"
                        ),
                        function,
                        node,
                    )
            else:
                data_ref = next(
                    (
                        item
                        for item in references
                        if isinstance(item.get("referencedDecl"), Mapping)
                    ),
                    None,
                )
                if data_ref is not None:
                    self._add_limitation(
                        "indirect_call",
                        "indirect calls are unsupported in fact extraction v0",
                        function,
                        node,
                    )
                else:
                    self._add_limitation(
                        "unresolved_symbol",
                        "call target could not be resolved",
                        function,
                        node,
                    )

        for child in children:
            self._visit(child, function)

    def _visit_decl_ref(
        self,
        node: Mapping[str, Any],
        function: str,
        use_kind: str,
    ) -> None:
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, Mapping):
            self._add_limitation(
                "unresolved_symbol",
                "declaration reference has no referenced declaration",
                function,
                node,
            )
            return
        identity = str(referenced.get("id", ""))
        symbol = self.clang_symbols.get(identity)
        if symbol is None:
            referenced_kind = str(referenced.get("kind", ""))
            if referenced_kind in {
                "BindingDecl",
                "FieldDecl",
                "FunctionDecl",
                "ParmVarDecl",
                "VarDecl",
            }:
                self._add_limitation(
                    "unresolved_symbol",
                    (
                        f"{referenced_kind} "
                        f"{referenced.get('name', '<unnamed>')} "
                        "is outside the main-file index"
                    ),
                    function,
                    node,
                )
            return
        if symbol.kind in {"function", "record"}:
            return
        self._add_use(
            symbol.id,
            function,
            use_kind,
            self._location(node),
        )

    def _visit_member(
        self,
        node: Mapping[str, Any],
        function: str,
        use_kind: str,
    ) -> None:
        member_id = str(node.get("referencedMemberDecl", ""))
        symbol = self.clang_symbols.get(member_id)
        if symbol is not None and symbol.kind == "field":
            self._add_use(
                symbol.id,
                function,
                use_kind,
                self._location(node),
            )
        elif member_id and member_id not in self.virtual_method_ids:
            self._add_limitation(
                "unresolved_symbol",
                (
                    f"member {node.get('name', '<unnamed>')} "
                    "is outside the main-file index"
                ),
                function,
                node,
            )
        for child in _children(node):
            self._visit(child, function)

    @staticmethod

    def _unwrap(node: Mapping[str, Any]) -> Mapping[str, Any]:
        current = node
        transparent = {
            "CStyleCastExpr",
            "CXXConstCastExpr",
            "CXXReinterpretCastExpr",
            "CXXStaticCastExpr",
            "ExprWithCleanups",
            "ImplicitCastExpr",
            "MaterializeTemporaryExpr",
            "ParenExpr",
        }
        while current.get("kind") in transparent:
            children = _children(current)
            if len(children) != 1:
                break
            current = children[0]
        return current

    def _handle_target(
        self,
        node: Mapping[str, Any],
        function: str,
        use_kind: str,
        mutation_kind: str,
    ) -> None:
        target = self._unwrap(node)
        kind = str(target.get("kind", ""))
        candidates: list[
            tuple[FactSymbol, Mapping[str, Any], str]
        ] = []

        if kind == "DeclRefExpr":
            symbol = self._symbol_from_decl_ref(target)
            if symbol is not None:
                candidates.append((symbol, target, use_kind))
        elif kind == "MemberExpr":
            for item in _walk(target):
                item_kind = str(item.get("kind", ""))
                if item_kind == "MemberExpr":
                    symbol = self.clang_symbols.get(
                        str(item.get("referencedMemberDecl", ""))
                    )
                    if symbol is not None and symbol.kind == "field":
                        candidates.append((symbol, item, use_kind))
                elif item_kind == "DeclRefExpr":
                    symbol = self._symbol_from_decl_ref(item)
                    if symbol is not None:
                        candidates.append((symbol, item, "address"))
        elif kind == "ArraySubscriptExpr":
            self._add_limitation(
                "unsupported_ast",
                "array mutation is outside fact extraction v0",
                function,
                target,
            )
            for item in _walk(target):
                if item.get("kind") == "DeclRefExpr":
                    symbol = self._symbol_from_decl_ref(item)
                    if symbol is not None:
                        candidates.append((symbol, item, "address"))
        else:
            self._add_limitation(
                "unsupported_ast",
                f"assignment target {kind or 'unknown node'} is unsupported",
                function,
                target,
            )
            return

        unique: dict[str, tuple[FactSymbol, Mapping[str, Any], str]] = {}
        for symbol, item, item_use in candidates:
            if symbol.kind not in {"field", "parameter", "variable"}:
                continue
            existing = unique.get(symbol.id)
            if existing is None or item_use == "read_write":
                unique[symbol.id] = (symbol, item, item_use)

        if not unique:
            self._add_limitation(
                "unresolved_symbol",
                "assignment target has no indexed storage symbol",
                function,
                target,
            )
            return

        for symbol, item, item_use in unique.values():
            location = self._location(item)
            self._add_use(
                symbol.id,
                function,
                item_use,
                location,
            )
            self._add_definition(
                symbol.id,
                function,
                "assignment",
                location,
            )
            self._add_mutation(
                function,
                symbol.id,
                mutation_kind,
                location,
            )

    def _symbol_from_decl_ref(
        self,
        node: Mapping[str, Any],
    ) -> FactSymbol | None:
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, Mapping):
            return None
        symbol = self.clang_symbols.get(
            str(referenced.get("id", ""))
        )
        if symbol is None or symbol.kind in {"function", "record"}:
            return None
        return symbol

    def _derive_purity(self) -> tuple[PurityFact, ...]:
        function_symbols = {
            group.symbol.id: group.symbol
            for group in self.functions.values()
            if group.symbol is not None
        }
        symbols = {symbol.id: symbol for symbol in self.symbols}
        impure: dict[str, set[str]] = {
            identity: set() for identity in function_symbols
        }
        unknown: dict[str, set[str]] = {
            identity: set() for identity in function_symbols
        }

        for mutation in self.mutations.values():
            target = symbols[mutation.target]
            if target.kind == "variable" and target.owner is None:
                impure[mutation.context].add("global_mutation")
            elif (
                target.kind == "parameter"
                and target.owner == mutation.context
            ):
                impure[mutation.context].add("parameter_mutation")

        limitation_reasons = {
            "indirect_call": "indirect_call",
            "macro_location": "unsupported_construct",
            "unsupported_ast": "unsupported_construct",
            "unresolved_symbol": "unresolved_call",
            "virtual_dispatch": "virtual_dispatch",
        }
        for limitation in self.limitations.values():
            if limitation.context not in function_symbols:
                continue
            unknown[limitation.context].add(
                limitation_reasons[limitation.code]
            )

        call_edges = [
            (call.caller, call.callee)
            for call in self.calls.values()
        ]
        changed = True
        while changed:
            changed = False
            for caller, callee in call_edges:
                if impure[callee]:
                    before = len(impure[caller])
                    impure[caller].add("direct_impure_call")
                    if len(impure[caller]) != before:
                        changed = True
                if unknown[callee]:
                    before = len(unknown[caller])
                    unknown[caller].update(unknown[callee])
                    if len(unknown[caller]) != before:
                        changed = True

        purity: list[PurityFact] = []
        for identity in sorted(function_symbols):
            if impure[identity]:
                reasons = tuple(
                    sorted(impure[identity] | unknown[identity])
                )
                purity.append(PurityFact(identity, "impure", reasons))
            elif unknown[identity]:
                purity.append(
                    PurityFact(
                        identity,
                        "unknown",
                        tuple(sorted(unknown[identity])),
                    )
                )
            else:
                purity.append(PurityFact(identity, "pure", ()))
        return tuple(purity)
