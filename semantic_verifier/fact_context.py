"""Deterministic, byte-bounded context packs over exact indexed facts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any

from .fact_queries import (
    MAX_NEIGHBORHOOD_DEPTH,
    FactWorld,
)
from .facts import FACT_SCHEMA


CONTEXT_SCHEMA = "codeskeptic.fact-context/v1"
DEFAULT_CONTEXT_BUDGET = 2000
MAX_CONTEXT_BUDGET = 2000

_CATEGORY_COUNT_KEYS = {
    "limitation": "limitations",
    "purity": "purity",
    "relation": "relations",
}
_CATEGORY_PRIORITY = {
    "purity": 0,
    "limitation": 1,
    "relation": 2,
}
_RELATION_PRIORITY = {
    "calls": 0,
    "mutates": 1,
    "owns": 2,
    "uses": 3,
    "defines": 4,
}


class FactContextError(ValueError):
    """Raised when an exact context pack cannot be produced."""


class ContextBudgetError(FactContextError):
    """Raised when a byte budget is invalid or cannot fit the envelope."""


@dataclass(frozen=True, slots=True)
class _Candidate:
    category: str
    distance: int
    row: Mapping[str, Any]

    def sort_key(self) -> tuple[Any, ...]:
        relation = (
            str(self.row["value"]["kind"])
            if self.category == "relation"
            else ""
        )
        return (
            self.distance,
            (
                3
                if self.category == "purity" and self.distance > 0
                else _CATEGORY_PRIORITY[self.category]
            ),
            _RELATION_PRIORITY.get(relation, -1),
            _compact_json(self.row),
        )


@dataclass(frozen=True, slots=True)
class FactContextPack:
    budget_bytes: int
    index_id: str
    source: Mapping[str, Any]
    root: Mapping[str, Any]
    items: tuple[Mapping[str, Any], ...]
    omitted: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_bytes": self.budget_bytes,
            "items": [
                dict(item)
                for item in self.items
            ],
            "omitted": dict(self.omitted),
            "provenance": {
                "index_id": self.index_id,
                "index_schema": FACT_SCHEMA,
                "source": dict(self.source),
            },
            "root": dict(self.root),
            "schema": CONTEXT_SCHEMA,
        }

    def to_json(self) -> str:
        return _compact_json(self.to_dict()) + "\n"

    @property
    def size_bytes(self) -> int:
        return len(self.to_json().encode("utf-8"))


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_budget(budget_bytes: object) -> int:
    if (
        isinstance(budget_bytes, bool)
        or not isinstance(budget_bytes, int)
        or budget_bytes < 1
        or budget_bytes > MAX_CONTEXT_BUDGET
    ):
        raise ContextBudgetError(
            (
                "context budget must be an integer between 1 and "
                f"{MAX_CONTEXT_BUDGET} bytes"
            )
        )
    return budget_bytes


def _symbol_label(symbol: Mapping[str, Any]) -> str:
    return str(symbol["qualified_name"])


def _ranked_candidates(
    world: FactWorld,
    selector: str,
) -> tuple[Mapping[str, Any], tuple[_Candidate, ...]]:
    neighborhood = world.neighborhood(
        selector,
        MAX_NEIGHBORHOOD_DEPTH,
    )
    answer = neighborhood.answer
    symbols = {
        str(row["symbol"]["id"]): row["symbol"]
        for row in answer["symbols"]
    }
    distances = {
        str(row["symbol"]["id"]): int(row["distance"])
        for row in answer["symbols"]
    }

    candidates: list[_Candidate] = []
    for purity in world.index.purity:
        distance = distances.get(purity.function)
        if distance is None:
            continue
        row = {
            "category": "purity",
            "distance": distance,
            "value": purity.to_dict(),
        }
        candidates.append(
            _Candidate("purity", distance, row)
        )

    for limitation in world.index.limitations:
        if limitation.context is None:
            distance = 0
        else:
            selected_distance = distances.get(limitation.context)
            if selected_distance is None:
                continue
            distance = selected_distance
        row = {
            "category": "limitation",
            "distance": distance,
            "value": limitation.to_dict(),
        }
        candidates.append(
            _Candidate("limitation", distance, row)
        )

    for edge in answer["edges"]:
        source = str(edge["source"])
        target = str(edge["target"])
        distance = max(distances[source], distances[target])
        row = {
            "category": "relation",
            "distance": distance,
            "labels": {
                "source": _symbol_label(symbols[source]),
                "target": _symbol_label(symbols[target]),
            },
            "value": dict(edge),
        }
        candidates.append(
            _Candidate("relation", distance, row)
        )

    return neighborhood.target, tuple(
        sorted(candidates, key=lambda candidate: candidate.sort_key())
    )


def _omitted_counts(
    candidates: Sequence[_Candidate],
) -> dict[str, int]:
    counts = Counter(
        _CATEGORY_COUNT_KEYS[candidate.category]
        for candidate in candidates
    )
    return {
        "limitations": counts["limitations"],
        "purity": counts["purity"],
        "relations": counts["relations"],
        "total": len(candidates),
    }


def _make_pack(
    *,
    budget_bytes: int,
    world: FactWorld,
    root: Mapping[str, Any],
    selected: Sequence[_Candidate],
    omitted: Sequence[_Candidate],
) -> FactContextPack:
    return FactContextPack(
        budget_bytes=budget_bytes,
        index_id=world.index.id,
        source=world.index.source.to_dict(),
        root=root,
        items=tuple(candidate.row for candidate in selected),
        omitted=_omitted_counts(omitted),
    )


def _minimum_envelope_budget(
    world: FactWorld,
    root: Mapping[str, Any],
    candidates: Sequence[_Candidate],
) -> int:
    for budget in range(1, MAX_CONTEXT_BUDGET + 1):
        pack = _make_pack(
            budget_bytes=budget,
            world=world,
            root=root,
            selected=(),
            omitted=candidates,
        )
        if pack.size_bytes <= budget:
            return budget
    raise ContextBudgetError(
        "root/provenance envelope exceeds the maximum context budget"
    )


def build_fact_context(
    world: FactWorld,
    selector: str,
    budget_bytes: int = DEFAULT_CONTEXT_BUDGET,
) -> FactContextPack:
    """Build the highest-ranked prefix that fits the requested byte budget."""

    budget = _validate_budget(budget_bytes)
    root, candidates = _ranked_candidates(world, selector)

    minimum = _minimum_envelope_budget(
        world,
        root,
        candidates,
    )
    if budget < minimum:
        raise ContextBudgetError(
            (
                f"context budget {budget} cannot fit root/provenance "
                f"envelope; requires at least {minimum} bytes"
            )
        )

    selected: list[_Candidate] = []
    for index, candidate in enumerate(candidates):
        tentative = _make_pack(
            budget_bytes=budget,
            world=world,
            root=root,
            selected=(*selected, candidate),
            omitted=candidates[index + 1 :],
        )
        if tentative.size_bytes > budget:
            break
        selected.append(candidate)

    final = _make_pack(
        budget_bytes=budget,
        world=world,
        root=root,
        selected=selected,
        omitted=candidates[len(selected) :],
    )
    if final.size_bytes > budget:
        raise ContextBudgetError(
            "internal context accounting exceeded the requested budget"
        )
    return final


def minimum_fact_context_budget(
    world: FactWorld,
    selector: str,
) -> int:
    """Return the exact smallest budget that can hold the required envelope."""

    root, candidates = _ranked_candidates(world, selector)
    return _minimum_envelope_budget(world, root, candidates)
