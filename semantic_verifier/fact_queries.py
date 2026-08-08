"""Deterministic queries over one validated fact index."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .facts import (
    FactIndex,
    FactLocation,
    FactSymbol,
    load_fact_index_json,
)


QUERY_SCHEMA = "codeskeptic.fact-query-result/v1"
QUERY_KINDS = frozenset({"neighborhood", "who-calls", "who-mutates"})
MAX_NEIGHBORHOOD_DEPTH = 8


class FactQueryError(ValueError):
    """Raised when an exact fact query cannot be formed."""


class SymbolNotFoundError(FactQueryError):
    """Raised when a selector matches no symbol."""


class AmbiguousSymbolError(FactQueryError):
    """Raised when a qualified-name selector matches several symbols."""


@dataclass(frozen=True, slots=True)
class FactQueryResult:
    kind: str
    selector: str
    index_id: str
    target: Mapping[str, Any]
    answer: Mapping[str, Any]
    limitations: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if self.kind not in QUERY_KINDS:
            raise FactQueryError(f"unsupported query kind {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": dict(self.answer),
            "index_id": self.index_id,
            "limitations": [
                dict(limitation)
                for limitation in self.limitations
            ],
            "query": {
                "kind": self.kind,
                "selector": self.selector,
            },
            "schema": QUERY_SCHEMA,
            "target": dict(self.target),
        }

    def to_json(self) -> str:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    def to_text(self) -> str:
        target = self.target
        lines = [
            f"query: {self.kind}",
            (
                f"target: {target['qualified_name']} "
                f"[{target['kind']}] {target['id']}"
            ),
        ]
        if self.kind == "who-calls":
            callers = self.answer["callers"]
            lines.append(f"callers: {len(callers)}")
            for item in callers:
                symbol = item["symbol"]
                sites = ", ".join(
                    _location_text(site)
                    for site in item["sites"]
                )
                lines.append(
                    f"- {symbol['qualified_name']} {symbol['id']} at {sites}"
                )
        elif self.kind == "who-mutates":
            mutators = self.answer["mutators"]
            lines.append(f"mutators: {len(mutators)}")
            for item in mutators:
                symbol = item["symbol"]
                facts = ", ".join(
                    (
                        f"{mutation['kind']}@"
                        f"{_location_text(mutation['location'])}"
                    )
                    for mutation in item["mutations"]
                )
                lines.append(
                    f"- {symbol['qualified_name']} {symbol['id']}: {facts}"
                )
        else:
            lines.append(f"depth: {self.answer['depth']}")
            lines.append(f"symbols: {len(self.answer['symbols'])}")
            for item in self.answer["symbols"]:
                symbol = item["symbol"]
                lines.append(
                    (
                        f"- d={item['distance']} "
                        f"{symbol['qualified_name']} "
                        f"[{symbol['kind']}] {symbol['id']}"
                    )
                )
            lines.append(f"edges: {len(self.answer['edges'])}")
            for edge in self.answer["edges"]:
                lines.append(
                    (
                        f"- {edge['kind']}: {edge['source']} "
                        f"-> {edge['target']}"
                    )
                )
        lines.append(f"limitations: {len(self.limitations)}")
        for limitation in self.limitations:
            location = limitation.get("location")
            suffix = (
                f" at {_location_text(location)}"
                if isinstance(location, Mapping)
                else ""
            )
            lines.append(
                f"- {limitation['code']}: {limitation['message']}{suffix}"
            )
        return "\n".join(lines) + "\n"


def _location_text(location: Mapping[str, Any]) -> str:
    return (
        f"{location['file']}:{location['line']}:"
        f"{location['column']}"
    )


def read_fact_index(path: str | Path) -> FactIndex:
    """Read strict UTF-8 fact-index JSON from disk."""

    return load_fact_index_json(
        Path(path).read_bytes().decode("utf-8")
    )


class FactWorld:
    """Pure query view over one D1 fact index."""

    def __init__(self, index: FactIndex) -> None:
        self.index = index
        self.symbols = {
            symbol.id: symbol
            for symbol in index.symbols
        }
        self.by_qualified_name: dict[str, list[FactSymbol]] = {}
        for symbol in index.symbols:
            self.by_qualified_name.setdefault(
                symbol.qualified_name,
                [],
            ).append(symbol)
        for matches in self.by_qualified_name.values():
            matches.sort(
                key=lambda symbol: (
                    symbol.kind,
                    symbol.type,
                    symbol.id,
                )
            )
        self.edges = self._build_edges()
        self.adjacency = self._build_adjacency(self.edges)

    def select(
        self,
        selector: str,
        *,
        kinds: frozenset[str] | None = None,
    ) -> FactSymbol:
        if not isinstance(selector, str) or not selector:
            raise FactQueryError("symbol selector must be non-empty text")
        direct = self.symbols.get(selector)
        matches = (
            [direct]
            if direct is not None
            else list(self.by_qualified_name.get(selector, ()))
        )
        if not matches:
            raise SymbolNotFoundError(
                f"symbol selector {selector!r} matched no symbol"
            )
        if len(matches) > 1:
            candidates = "; ".join(
                (
                    f"{symbol.kind} {symbol.qualified_name} "
                    f"{symbol.type} {symbol.id}"
                )
                for symbol in matches
            )
            raise AmbiguousSymbolError(
                (
                    f"symbol selector {selector!r} is ambiguous: "
                    f"{candidates}"
                )
            )
        symbol = matches[0]
        if kinds is not None and symbol.kind not in kinds:
            expected = ", ".join(sorted(kinds))
            raise FactQueryError(
                (
                    f"symbol {symbol.qualified_name!r} has kind "
                    f"{symbol.kind!r}; expected one of {expected}"
                )
            )
        return symbol
    def who_calls(self, selector: str) -> FactQueryResult:
        target = self.select(
            selector,
            kinds=frozenset({"function"}),
        )
        grouped: dict[str, list[Any]] = {}
        for call in self.index.calls:
            if call.callee == target.id:
                grouped.setdefault(call.caller, []).append(call)
        callers: list[dict[str, Any]] = []
        relevant = {target.id}
        for caller_id in sorted(grouped):
            relevant.add(caller_id)
            calls = sorted(
                grouped[caller_id],
                key=lambda call: (
                    call.location,
                    call.id,
                ),
            )
            callers.append(
                {
                    "call_ids": [call.id for call in calls],
                    "sites": [
                        call.location.to_dict()
                        for call in calls
                    ],
                    "symbol": self.symbols[caller_id].to_dict(),
                }
            )
        return FactQueryResult(
            "who-calls",
            selector,
            self.index.id,
            target.to_dict(),
            {"callers": callers},
            self._relevant_limitations(relevant),
        )

    def who_mutates(self, selector: str) -> FactQueryResult:
        target = self.select(
            selector,
            kinds=frozenset({"field", "parameter", "variable"}),
        )
        grouped: dict[str, list[Any]] = {}
        for mutation in self.index.mutations:
            if mutation.target == target.id:
                grouped.setdefault(
                    mutation.context,
                    [],
                ).append(mutation)
        mutators: list[dict[str, Any]] = []
        relevant = {target.id}
        for function_id in sorted(grouped):
            relevant.add(function_id)
            mutations = sorted(
                grouped[function_id],
                key=lambda mutation: (
                    mutation.location,
                    mutation.kind,
                    mutation.id,
                ),
            )
            mutators.append(
                {
                    "mutations": [
                        {
                            "id": mutation.id,
                            "kind": mutation.kind,
                            "location": mutation.location.to_dict(),
                        }
                        for mutation in mutations
                    ],
                    "symbol": self.symbols[function_id].to_dict(),
                }
            )
        return FactQueryResult(
            "who-mutates",
            selector,
            self.index.id,
            target.to_dict(),
            {"mutators": mutators},
            self._relevant_limitations(relevant),
        )

    def neighborhood(
        self,
        selector: str,
        depth: int = 2,
    ) -> FactQueryResult:
        if (
            isinstance(depth, bool)
            or not isinstance(depth, int)
            or depth < 0
            or depth > MAX_NEIGHBORHOOD_DEPTH
        ):
            raise FactQueryError(
                (
                    "neighborhood depth must be an integer "
                    f"between 0 and {MAX_NEIGHBORHOOD_DEPTH}"
                )
            )
        target = self.select(selector)
        distances: dict[str, int] = {target.id: 0}
        frontier = [target.id]
        for current_depth in range(depth):
            discovered: list[str] = []
            for identity in sorted(frontier):
                for neighbor in sorted(
                    self.adjacency.get(identity, ())
                ):
                    if neighbor in distances:
                        continue
                    distances[neighbor] = current_depth + 1
                    discovered.append(neighbor)
            frontier = sorted(set(discovered))
            if not frontier:
                break

        symbol_rows = [
            {
                "distance": distances[identity],
                "symbol": self.symbols[identity].to_dict(),
            }
            for identity in sorted(
                distances,
                key=lambda identity: (
                    distances[identity],
                    self.symbols[identity].qualified_name,
                    self.symbols[identity].kind,
                    self.symbols[identity].type,
                    identity,
                ),
            )
        ]
        edges = [
            edge
            for edge in self.edges
            if edge["source"] in distances
            and edge["target"] in distances
        ]
        return FactQueryResult(
            "neighborhood",
            selector,
            self.index.id,
            target.to_dict(),
            {
                "depth": depth,
                "edges": edges,
                "symbols": symbol_rows,
            },
            self._relevant_limitations(set(distances)),
        )

    def query(
        self,
        kind: str,
        selector: str,
        *,
        depth: int = 2,
    ) -> FactQueryResult:
        if kind == "who-calls":
            return self.who_calls(selector)
        if kind == "who-mutates":
            return self.who_mutates(selector)
        if kind == "neighborhood":
            return self.neighborhood(selector, depth)
        raise FactQueryError(f"unsupported query kind {kind!r}")

    def _relevant_limitations(
        self,
        identities: set[str],
    ) -> tuple[Mapping[str, Any], ...]:
        selected = [
            limitation
            for limitation in self.index.limitations
            if limitation.context is None
            or limitation.context in identities
        ]
        return tuple(
            limitation.to_dict()
            for limitation in sorted(
                selected,
                key=lambda limitation: limitation.sort_key(),
            )
        )

    def _build_edges(self) -> tuple[dict[str, Any], ...]:
        edges: list[dict[str, Any]] = []
        for symbol in self.index.symbols:
            if symbol.owner is not None:
                edges.append(
                    self._edge(
                        "owns",
                        symbol.owner,
                        symbol.id,
                        None,
                        symbol.kind,
                        symbol.declaration,
                    )
                )
        for definition in self.index.definitions:
            if definition.context is not None:
                edges.append(
                    self._edge(
                        "defines",
                        definition.context,
                        definition.symbol,
                        definition.id,
                        definition.kind,
                        definition.location,
                    )
                )
        for use in self.index.uses:
            edges.append(
                self._edge(
                    "uses",
                    use.context,
                    use.symbol,
                    use.id,
                    use.kind,
                    use.location,
                )
            )
        for call in self.index.calls:
            edges.append(
                self._edge(
                    "calls",
                    call.caller,
                    call.callee,
                    call.id,
                    call.kind,
                    call.location,
                )
            )
        for mutation in self.index.mutations:
            edges.append(
                self._edge(
                    "mutates",
                    mutation.context,
                    mutation.target,
                    mutation.id,
                    mutation.kind,
                    mutation.location,
                )
            )
        return tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge["kind"],
                    edge["source"],
                    edge["target"],
                    edge["detail"],
                    edge["fact_id"] or "",
                    _location_sort_key(edge["location"]),
                ),
            )
        )

    @staticmethod
    def _edge(
        kind: str,
        source: str,
        target: str,
        fact_id: str | None,
        detail: str,
        location: FactLocation,
    ) -> dict[str, Any]:
        return {
            "detail": detail,
            "fact_id": fact_id,
            "kind": kind,
            "location": location.to_dict(),
            "source": source,
            "target": target,
        }

    @staticmethod
    def _build_adjacency(
        edges: Iterable[Mapping[str, Any]],
    ) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            source = str(edge["source"])
            target = str(edge["target"])
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)
        return adjacency


def _location_sort_key(
    location: Mapping[str, Any],
) -> tuple[str, int, int]:
    return (
        str(location["file"]),
        int(location["line"]),
        int(location["column"]),
    )
