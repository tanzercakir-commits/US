"""Owned, proof-neutral Memory IR v7 representation values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


MEMORY_SCHEMA = "codeskeptic.memory-model/v7"
MEMORY_ID_SCHEMA = "codeskeptic.memory-identity/v7"

REGION_KINDS = frozenset({"global", "heap", "stack"})
LIFETIME_STATES = frozenset({"alive", "declared", "ended"})
ALLOCATION_STATES = frozenset(
    {"allocated", "freed", "not_applicable", "unallocated"}
)
POINTER_KINDS = frozenset({"address_of", "typed_null"})
MEMORY_OPERATION_KINDS = frozenset(
    {"allocation", "lifetime", "load", "store"}
)

_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_INDEX_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class MemoryIRError(ValueError):
    """Raised when a Memory IR value is malformed or internally inconsistent."""


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
        "schema": MEMORY_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MemoryIRError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_RE.fullmatch(text) is None:
        raise MemoryIRError(f"{field} must be a lowercase sha256 identity")
    return text


def _require_non_negative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MemoryIRError(f"{field} must be a non-negative integer")
    return value


def _require_positive(value: object, field: str) -> int:
    number = _require_non_negative(value, field)
    if number == 0:
        raise MemoryIRError(f"{field} must be positive")
    return number


def _require_alignment(value: object, field: str) -> int:
    alignment = _require_positive(value, field)
    if alignment & (alignment - 1):
        raise MemoryIRError(f"{field} must be a power of two")
    return alignment


def _require_type(value: object, field: str) -> str:
    type_name = _require_text(value, field)
    if type_name.strip() != type_name:
        raise MemoryIRError(f"{field} must be canonical type text")
    return type_name


def pointer_type(pointee: str) -> str:
    return f"ptr<{_require_type(pointee, 'pointer pointee type')}>"


def is_pointer_type(type_name: object) -> bool:
    return (
        isinstance(type_name, str)
        and type_name.startswith("ptr<")
        and type_name.endswith(">")
        and len(type_name) > 5
    )


def pointee_type(type_name: str) -> str:
    if not is_pointer_type(type_name):
        raise MemoryIRError(f"unsupported pointer type {type_name!r}")
    return type_name[4:-1]


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    if set(value) != expected:
        raise MemoryIRError(
            f"{field} fields must be exactly {sorted(expected)!r}"
        )


@dataclass(frozen=True, order=True, slots=True)
class MemoryPathStep:
    kind: str
    value: str
    type: str
    offset_bytes: int
    extent_bytes: int

    def __post_init__(self) -> None:
        if self.kind not in {"field", "index"}:
            raise MemoryIRError("memory path step kind is unsupported")
        value = _require_text(self.value, "memory path step value")
        if self.kind == "index" and _INDEX_RE.fullmatch(value) is None:
            raise MemoryIRError(
                "memory index path step must be canonical non-negative decimal"
            )
        _require_type(self.type, "memory path step type")
        _require_non_negative(
            self.offset_bytes,
            "memory path step offset_bytes",
        )
        _require_positive(
            self.extent_bytes,
            "memory path step extent_bytes",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "extent_bytes": self.extent_bytes,
            "kind": self.kind,
            "offset_bytes": self.offset_bytes,
            "type": self.type,
            "value": self.value,
        }


@dataclass(frozen=True, order=True, slots=True)
class MemoryRegion:
    id: str
    kind: str
    owner: str | None
    source_key: str
    extent_bytes: int
    alignment_bytes: int
    initial_lifetime: str
    initial_allocation: str

    def __post_init__(self) -> None:
        _require_hash(self.id, "region.id")
        if self.kind not in REGION_KINDS:
            raise MemoryIRError("region.kind is unsupported")
        if self.owner is not None:
            _require_text(self.owner, "region.owner")
        _require_text(self.source_key, "region.source_key")
        _require_positive(self.extent_bytes, "region.extent_bytes")
        _require_alignment(self.alignment_bytes, "region.alignment_bytes")
        if self.initial_lifetime not in LIFETIME_STATES:
            raise MemoryIRError("region.initial_lifetime is unsupported")
        if self.initial_allocation not in ALLOCATION_STATES:
            raise MemoryIRError("region.initial_allocation is unsupported")
        expected = {
            "global": (None, "alive", "not_applicable"),
            "heap": ("required", "declared", "unallocated"),
            "stack": ("required", "declared", "not_applicable"),
        }[self.kind]
        owner_policy, lifetime, allocation = expected
        if (owner_policy is None) != (self.owner is None):
            raise MemoryIRError(
                f"{self.kind} region owner policy is violated"
            )
        if (
            self.initial_lifetime != lifetime
            or self.initial_allocation != allocation
        ):
            raise MemoryIRError(
                f"{self.kind} region initial state is not canonical"
            )
        if self.id != _content_id("region", self.identity_dict()):
            raise MemoryIRError("region.id does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        owner: str | None,
        source_key: str,
        extent_bytes: int,
        alignment_bytes: int,
    ) -> "MemoryRegion":
        initial_lifetime = "alive" if kind == "global" else "declared"
        initial_allocation = (
            "unallocated" if kind == "heap" else "not_applicable"
        )
        fields: dict[str, object] = {
            "alignment_bytes": alignment_bytes,
            "extent_bytes": extent_bytes,
            "initial_allocation": initial_allocation,
            "initial_lifetime": initial_lifetime,
            "kind": kind,
            "owner": owner,
            "source_key": source_key,
        }
        return cls(
            _content_id("region", fields),
            kind,
            owner,
            source_key,
            extent_bytes,
            alignment_bytes,
            initial_lifetime,
            initial_allocation,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "alignment_bytes": self.alignment_bytes,
            "extent_bytes": self.extent_bytes,
            "initial_allocation": self.initial_allocation,
            "initial_lifetime": self.initial_lifetime,
            "kind": self.kind,
            "owner": self.owner,
            "source_key": self.source_key,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}

@dataclass(frozen=True, order=True, slots=True)
class MemoryObject:
    id: str
    region: str
    type: str
    path: tuple[MemoryPathStep, ...]
    offset_bytes: int
    extent_bytes: int
    alignment_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.path, tuple):
            raise MemoryIRError("object.path must be an immutable tuple")
        if any(not isinstance(step, MemoryPathStep) for step in self.path):
            raise MemoryIRError("object.path contains a malformed step")
        _require_hash(self.id, "object.id")
        _require_hash(self.region, "object.region")
        _require_type(self.type, "object.type")
        _require_non_negative(self.offset_bytes, "object.offset_bytes")
        _require_positive(self.extent_bytes, "object.extent_bytes")
        alignment = _require_alignment(
            self.alignment_bytes,
            "object.alignment_bytes",
        )
        if self.offset_bytes % alignment:
            raise MemoryIRError("object offset violates its alignment")
        expected_offset = sum(step.offset_bytes for step in self.path)
        if self.offset_bytes != expected_offset:
            raise MemoryIRError(
                "object offset must equal its canonical path offsets"
            )
        if self.path and self.path[-1].type != self.type:
            raise MemoryIRError(
                "object terminal path type does not match object.type"
            )
        if not self.path and self.offset_bytes != 0:
            raise MemoryIRError("root object must begin at region offset zero")
        if self.id != _content_id("object", self.identity_dict()):
            raise MemoryIRError("object.id does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        region: str,
        type: str,
        path: Sequence[MemoryPathStep] = (),
        extent_bytes: int,
        alignment_bytes: int,
    ) -> "MemoryObject":
        path_items = tuple(path)
        offset_bytes = sum(step.offset_bytes for step in path_items)
        fields: dict[str, object] = {
            "alignment_bytes": alignment_bytes,
            "extent_bytes": extent_bytes,
            "offset_bytes": offset_bytes,
            "path": [step.to_dict() for step in path_items],
            "region": region,
            "type": type,
        }
        return cls(
            _content_id("object", fields),
            region,
            type,
            path_items,
            offset_bytes,
            extent_bytes,
            alignment_bytes,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "alignment_bytes": self.alignment_bytes,
            "extent_bytes": self.extent_bytes,
            "offset_bytes": self.offset_bytes,
            "path": [step.to_dict() for step in self.path],
            "region": self.region,
            "type": self.type,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, order=True, slots=True)
class MemoryLocation:
    id: str
    object: str
    type: str
    path: tuple[MemoryPathStep, ...]
    offset_bytes: int
    extent_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.path, tuple):
            raise MemoryIRError("location.path must be an immutable tuple")
        if any(not isinstance(step, MemoryPathStep) for step in self.path):
            raise MemoryIRError("location.path contains a malformed step")
        _require_hash(self.id, "location.id")
        _require_hash(self.object, "location.object")
        _require_type(self.type, "location.type")
        _require_non_negative(self.offset_bytes, "location.offset_bytes")
        _require_positive(self.extent_bytes, "location.extent_bytes")
        expected_offset = sum(step.offset_bytes for step in self.path)
        if self.offset_bytes != expected_offset:
            raise MemoryIRError(
                "location offset must equal its canonical path offsets"
            )
        if self.path and self.path[-1].type != self.type:
            raise MemoryIRError(
                "location terminal path type does not match location.type"
            )
        if not self.path and self.offset_bytes != 0:
            raise MemoryIRError("root location offset must be zero")
        if self.id != _content_id("location", self.identity_dict()):
            raise MemoryIRError("location.id does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        object: str,
        type: str,
        path: Sequence[MemoryPathStep] = (),
        extent_bytes: int,
    ) -> "MemoryLocation":
        path_items = tuple(path)
        offset_bytes = sum(step.offset_bytes for step in path_items)
        fields: dict[str, object] = {
            "extent_bytes": extent_bytes,
            "object": object,
            "offset_bytes": offset_bytes,
            "path": [step.to_dict() for step in path_items],
            "type": type,
        }
        return cls(
            _content_id("location", fields),
            object,
            type,
            path_items,
            offset_bytes,
            extent_bytes,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "extent_bytes": self.extent_bytes,
            "object": self.object,
            "offset_bytes": self.offset_bytes,
            "path": [step.to_dict() for step in self.path],
            "type": self.type,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, order=True, slots=True)
class MemoryPointer:
    id: str
    kind: str
    type: str
    region: str | None
    location: str | None
    offset_bytes: int

    def __post_init__(self) -> None:
        _require_hash(self.id, "pointer.id")
        if self.kind not in POINTER_KINDS:
            raise MemoryIRError("pointer.kind is unsupported")
        pointee_type(self.type)
        _require_non_negative(self.offset_bytes, "pointer.offset_bytes")
        if self.kind == "typed_null":
            if (
                self.region is not None
                or self.location is not None
                or self.offset_bytes != 0
            ):
                raise MemoryIRError(
                    "typed null cannot carry provenance or an offset"
                )
        else:
            _require_hash(self.region, "pointer.region")
            _require_hash(self.location, "pointer.location")
        if self.id != _content_id("pointer", self.identity_dict()):
            raise MemoryIRError("pointer.id does not match canonical content")

    @classmethod
    def typed_null(cls, pointee: str) -> "MemoryPointer":
        fields: dict[str, object] = {
            "kind": "typed_null",
            "location": None,
            "offset_bytes": 0,
            "region": None,
            "type": pointer_type(pointee),
        }
        return cls(
            _content_id("pointer", fields),
            "typed_null",
            pointer_type(pointee),
            None,
            None,
            0,
        )

    @classmethod
    def address_of(
        cls,
        *,
        pointee: str,
        region: str,
        location: str,
        offset_bytes: int,
    ) -> "MemoryPointer":
        fields: dict[str, object] = {
            "kind": "address_of",
            "location": location,
            "offset_bytes": offset_bytes,
            "region": region,
            "type": pointer_type(pointee),
        }
        return cls(
            _content_id("pointer", fields),
            "address_of",
            pointer_type(pointee),
            region,
            location,
            offset_bytes,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "location": self.location,
            "offset_bytes": self.offset_bytes,
            "region": self.region,
            "type": self.type,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, order=True, slots=True)
class MemoryState:
    id: str
    function: str
    ordinal: int

    def __post_init__(self) -> None:
        _require_hash(self.id, "state.id")
        _require_text(self.function, "state.function")
        _require_non_negative(self.ordinal, "state.ordinal")
        if self.id != _content_id("state", self.identity_dict()):
            raise MemoryIRError("state.id does not match canonical content")

    @classmethod
    def create(cls, function: str, ordinal: int) -> "MemoryState":
        fields: dict[str, object] = {
            "function": function,
            "ordinal": ordinal,
        }
        return cls(
            _content_id("state", fields),
            function,
            ordinal,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "ordinal": self.ordinal,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}


@dataclass(frozen=True, order=True, slots=True)
class MemoryOperation:
    id: str
    kind: str
    state_before: str
    state_after: str
    pointer: str | None = None
    location: str | None = None
    region: str | None = None
    lifetime_before: str | None = None
    lifetime_after: str | None = None
    allocation_before: str | None = None
    allocation_after: str | None = None

    def __post_init__(self) -> None:
        _require_hash(self.id, "operation.id")
        if self.kind not in MEMORY_OPERATION_KINDS:
            raise MemoryIRError("operation.kind is unsupported")
        _require_hash(self.state_before, "operation.state_before")
        _require_hash(self.state_after, "operation.state_after")
        if self.kind == "load":
            self._require_access(read_only=True)
        elif self.kind == "store":
            self._require_access(read_only=False)
        elif self.kind == "lifetime":
            self._require_transition(
                allowed={("declared", "alive"), ("alive", "ended")},
                before=self.lifetime_before,
                after=self.lifetime_after,
                other_before=self.allocation_before,
                other_after=self.allocation_after,
                label="lifetime",
            )
        else:
            self._require_transition(
                allowed={
                    ("unallocated", "allocated"),
                    ("allocated", "freed"),
                },
                before=self.allocation_before,
                after=self.allocation_after,
                other_before=self.lifetime_before,
                other_after=self.lifetime_after,
                label="allocation",
            )
        if self.id != _content_id("operation", self.identity_dict()):
            raise MemoryIRError(
                "operation.id does not match canonical content"
            )

    def _require_access(self, *, read_only: bool) -> None:
        _require_hash(self.pointer, "operation.pointer")
        _require_hash(self.location, "operation.location")
        if self.region is not None:
            raise MemoryIRError("load/store operation cannot carry region")
        if any(
            value is not None
            for value in (
                self.lifetime_before,
                self.lifetime_after,
                self.allocation_before,
                self.allocation_after,
            )
        ):
            raise MemoryIRError("load/store operation cannot carry a transition")
        if read_only != (self.state_before == self.state_after):
            raise MemoryIRError(
                "load must preserve state and store must advance state"
            )

    def _require_transition(
        self,
        *,
        allowed: set[tuple[str, str]],
        before: str | None,
        after: str | None,
        other_before: str | None,
        other_after: str | None,
        label: str,
    ) -> None:
        _require_hash(self.region, "operation.region")
        if self.pointer is not None or self.location is not None:
            raise MemoryIRError(
                f"{label} transition cannot carry pointer/location"
            )
        if (before, after) not in allowed:
            raise MemoryIRError(
                f"operation {label} transition is unsupported"
            )
        if other_before is not None or other_after is not None:
            raise MemoryIRError(
                f"{label} transition carries the other state dimension"
            )
        if self.state_before == self.state_after:
            raise MemoryIRError(f"{label} transition must advance memory state")

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        state_before: str,
        state_after: str,
        pointer: str | None = None,
        location: str | None = None,
        region: str | None = None,
        lifetime_before: str | None = None,
        lifetime_after: str | None = None,
        allocation_before: str | None = None,
        allocation_after: str | None = None,
    ) -> "MemoryOperation":
        fields: dict[str, object] = {
            "allocation_after": allocation_after,
            "allocation_before": allocation_before,
            "kind": kind,
            "lifetime_after": lifetime_after,
            "lifetime_before": lifetime_before,
            "location": location,
            "pointer": pointer,
            "region": region,
            "state_after": state_after,
            "state_before": state_before,
        }
        return cls(
            _content_id("operation", fields),
            kind,
            state_before,
            state_after,
            pointer,
            location,
            region,
            lifetime_before,
            lifetime_after,
            allocation_before,
            allocation_after,
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "allocation_after": self.allocation_after,
            "allocation_before": self.allocation_before,
            "kind": self.kind,
            "lifetime_after": self.lifetime_after,
            "lifetime_before": self.lifetime_before,
            "location": self.location,
            "pointer": self.pointer,
            "region": self.region,
            "state_after": self.state_after,
            "state_before": self.state_before,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class MemoryModel:
    id: str
    regions: tuple[MemoryRegion, ...]
    objects: tuple[MemoryObject, ...]
    locations: tuple[MemoryLocation, ...]
    pointers: tuple[MemoryPointer, ...]
    states: tuple[MemoryState, ...]
    schema: str = MEMORY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != MEMORY_SCHEMA:
            raise MemoryIRError("unsupported memory model schema")
        field_types = {
            "regions": MemoryRegion,
            "objects": MemoryObject,
            "locations": MemoryLocation,
            "pointers": MemoryPointer,
            "states": MemoryState,
        }
        for field_name, item_type in field_types.items():
            values = getattr(self, field_name)
            if not isinstance(values, tuple):
                raise MemoryIRError(
                    f"memory model {field_name} must be an immutable tuple"
                )
            if any(not isinstance(item, item_type) for item in values):
                raise MemoryIRError(
                    f"memory model {field_name} contains a malformed value"
                )
            if values != tuple(sorted(values, key=lambda item: item.id)):
                raise MemoryIRError(
                    f"memory model {field_name} must be sorted by identity"
                )
            ids = [item.id for item in values]
            if len(ids) != len(set(ids)):
                raise MemoryIRError(
                    f"memory model {field_name} contains duplicate identities"
                )
        self._validate_references()
        _require_hash(self.id, "memory model.id")
        if self.id != _content_id("memory-model", self.identity_dict()):
            raise MemoryIRError(
                "memory model id does not match canonical content"
            )

    def _validate_references(self) -> None:
        regions = {item.id: item for item in self.regions}
        objects = {item.id: item for item in self.objects}
        locations = {item.id: item for item in self.locations}
        state_keys: set[tuple[str, int]] = set()
        for state in self.states:
            key = (state.function, state.ordinal)
            if key in state_keys:
                raise MemoryIRError(
                    "memory states repeat one function/ordinal"
                )
            state_keys.add(key)
        for item in self.objects:
            region = regions.get(item.region)
            if region is None:
                raise MemoryIRError("object.region is dangling")
            if item.offset_bytes + item.extent_bytes > region.extent_bytes:
                raise MemoryIRError("object lies outside its region extent")
            if item.alignment_bytes > region.alignment_bytes:
                raise MemoryIRError(
                    "object alignment exceeds its region alignment"
                )
        for item in self.locations:
            owner = objects.get(item.object)
            if owner is None:
                raise MemoryIRError("location.object is dangling")
            if item.offset_bytes + item.extent_bytes > owner.extent_bytes:
                raise MemoryIRError("location lies outside its object extent")
            if not item.path and item.type != owner.type:
                raise MemoryIRError(
                    "root location type does not match its object"
                )
        for item in self.pointers:
            if item.kind == "typed_null":
                continue
            location = locations.get(item.location or "")
            if location is None:
                raise MemoryIRError("pointer.location is dangling")
            owner = objects[location.object]
            if item.region != owner.region:
                raise MemoryIRError(
                    "pointer provenance does not match its location region"
                )
            expected_offset = owner.offset_bytes + location.offset_bytes
            if item.offset_bytes != expected_offset:
                raise MemoryIRError(
                    "pointer offset does not match its address-of location"
                )
            if pointee_type(item.type) != location.type:
                raise MemoryIRError(
                    "pointer pointee type does not match its location"
                )

    @classmethod
    def create(
        cls,
        *,
        regions: Sequence[MemoryRegion] = (),
        objects: Sequence[MemoryObject] = (),
        locations: Sequence[MemoryLocation] = (),
        pointers: Sequence[MemoryPointer] = (),
        states: Sequence[MemoryState] = (),
    ) -> "MemoryModel":
        region_items = tuple(sorted(regions, key=lambda item: item.id))
        object_items = tuple(sorted(objects, key=lambda item: item.id))
        location_items = tuple(sorted(locations, key=lambda item: item.id))
        pointer_items = tuple(sorted(pointers, key=lambda item: item.id))
        state_items = tuple(sorted(states, key=lambda item: item.id))
        fields: dict[str, object] = {
            "locations": [item.to_dict() for item in location_items],
            "objects": [item.to_dict() for item in object_items],
            "pointers": [item.to_dict() for item in pointer_items],
            "regions": [item.to_dict() for item in region_items],
            "schema": MEMORY_SCHEMA,
            "states": [item.to_dict() for item in state_items],
        }
        return cls(
            _content_id("memory-model", fields),
            region_items,
            object_items,
            location_items,
            pointer_items,
            state_items,
        )

    @classmethod
    def empty(cls) -> "MemoryModel":
        return cls.create()

    def identity_dict(self) -> dict[str, object]:
        return {
            "locations": [item.to_dict() for item in self.locations],
            "objects": [item.to_dict() for item in self.objects],
            "pointers": [item.to_dict() for item in self.pointers],
            "regions": [item.to_dict() for item in self.regions],
            "schema": self.schema,
            "states": [item.to_dict() for item in self.states],
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def validate_operation(self, operation: MemoryOperation) -> None:
        states = {item.id: item for item in self.states}
        before = states.get(operation.state_before)
        after = states.get(operation.state_after)
        if before is None or after is None:
            raise MemoryIRError("memory operation state is dangling")
        if before.function != after.function:
            raise MemoryIRError(
                "memory operation states belong to different functions"
            )
        if operation.kind == "load":
            if before != after:
                raise MemoryIRError("load must retain one memory state")
        elif after.ordinal != before.ordinal + 1:
            raise MemoryIRError(
                "mutating memory operation must advance one state ordinal"
            )
        if operation.kind in {"load", "store"}:
            pointers = {item.id: item for item in self.pointers}
            locations = {item.id: item for item in self.locations}
            pointer = pointers.get(operation.pointer or "")
            location = locations.get(operation.location or "")
            if pointer is None or location is None:
                raise MemoryIRError(
                    "memory access pointer/location is dangling"
                )
            if pointer.kind != "address_of":
                raise MemoryIRError(
                    "memory access cannot use typed null as an address"
                )
            if pointer.location != location.id:
                raise MemoryIRError(
                    "memory access pointer and location disagree"
                )
        else:
            regions = {item.id: item for item in self.regions}
            region = regions.get(operation.region or "")
            if region is None:
                raise MemoryIRError("memory transition region is dangling")
            if operation.kind == "allocation" and region.kind != "heap":
                raise MemoryIRError(
                    "allocation transitions require a heap region"
                )


def _path_step_from_dict(
    value: object,
    field: str,
) -> MemoryPathStep:
    if not isinstance(value, Mapping):
        raise MemoryIRError(f"{field} must be an object")
    _exact_keys(
        value,
        {"extent_bytes", "kind", "offset_bytes", "type", "value"},
        field,
    )
    return MemoryPathStep(
        value["kind"],
        value["value"],
        value["type"],
        value["offset_bytes"],
        value["extent_bytes"],
    )


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise MemoryIRError(f"{field} must be an array")
    return value


def memory_model_from_dict(value: object) -> MemoryModel:
    if not isinstance(value, Mapping):
        raise MemoryIRError("memory model must be an object")
    _exact_keys(
        value,
        {
            "id",
            "locations",
            "objects",
            "pointers",
            "regions",
            "schema",
            "states",
        },
        "memory model",
    )

    def path(raw: object, field: str) -> tuple[MemoryPathStep, ...]:
        return tuple(
            _path_step_from_dict(item, f"{field}[{index}]")
            for index, item in enumerate(_array(raw, field))
        )

    regions: list[MemoryRegion] = []
    for index, raw in enumerate(_array(value["regions"], "regions")):
        field = f"regions[{index}]"
        if not isinstance(raw, Mapping):
            raise MemoryIRError(f"{field} must be an object")
        _exact_keys(
            raw,
            {
                "alignment_bytes",
                "extent_bytes",
                "id",
                "initial_allocation",
                "initial_lifetime",
                "kind",
                "owner",
                "source_key",
            },
            field,
        )
        regions.append(
            MemoryRegion(
                raw["id"],
                raw["kind"],
                raw["owner"],
                raw["source_key"],
                raw["extent_bytes"],
                raw["alignment_bytes"],
                raw["initial_lifetime"],
                raw["initial_allocation"],
            )
        )

    objects: list[MemoryObject] = []
    for index, raw in enumerate(_array(value["objects"], "objects")):
        field = f"objects[{index}]"
        if not isinstance(raw, Mapping):
            raise MemoryIRError(f"{field} must be an object")
        _exact_keys(
            raw,
            {
                "alignment_bytes",
                "extent_bytes",
                "id",
                "offset_bytes",
                "path",
                "region",
                "type",
            },
            field,
        )
        objects.append(
            MemoryObject(
                raw["id"],
                raw["region"],
                raw["type"],
                path(raw["path"], f"{field}.path"),
                raw["offset_bytes"],
                raw["extent_bytes"],
                raw["alignment_bytes"],
            )
        )

    locations: list[MemoryLocation] = []
    for index, raw in enumerate(_array(value["locations"], "locations")):
        field = f"locations[{index}]"
        if not isinstance(raw, Mapping):
            raise MemoryIRError(f"{field} must be an object")
        _exact_keys(
            raw,
            {
                "extent_bytes",
                "id",
                "object",
                "offset_bytes",
                "path",
                "type",
            },
            field,
        )
        locations.append(
            MemoryLocation(
                raw["id"],
                raw["object"],
                raw["type"],
                path(raw["path"], f"{field}.path"),
                raw["offset_bytes"],
                raw["extent_bytes"],
            )
        )

    pointers: list[MemoryPointer] = []
    for index, raw in enumerate(_array(value["pointers"], "pointers")):
        field = f"pointers[{index}]"
        if not isinstance(raw, Mapping):
            raise MemoryIRError(f"{field} must be an object")
        _exact_keys(
            raw,
            {"id", "kind", "location", "offset_bytes", "region", "type"},
            field,
        )
        pointers.append(
            MemoryPointer(
                raw["id"],
                raw["kind"],
                raw["type"],
                raw["region"],
                raw["location"],
                raw["offset_bytes"],
            )
        )

    states: list[MemoryState] = []
    for index, raw in enumerate(_array(value["states"], "states")):
        field = f"states[{index}]"
        if not isinstance(raw, Mapping):
            raise MemoryIRError(f"{field} must be an object")
        _exact_keys(raw, {"function", "id", "ordinal"}, field)
        states.append(
            MemoryState(raw["id"], raw["function"], raw["ordinal"])
        )

    model = MemoryModel(
        value["id"],
        tuple(regions),
        tuple(objects),
        tuple(locations),
        tuple(pointers),
        tuple(states),
        value["schema"],
    )
    return model


def memory_operation_from_dict(value: object) -> MemoryOperation:
    if not isinstance(value, Mapping):
        raise MemoryIRError("memory operation must be an object")
    _exact_keys(
        value,
        {
            "allocation_after",
            "allocation_before",
            "id",
            "kind",
            "lifetime_after",
            "lifetime_before",
            "location",
            "pointer",
            "region",
            "state_after",
            "state_before",
        },
        "memory operation",
    )
    try:
        return MemoryOperation(
            value["id"],
            value["kind"],
            value["state_before"],
            value["state_after"],
            value["pointer"],
            value["location"],
            value["region"],
            value["lifetime_before"],
            value["lifetime_after"],
            value["allocation_before"],
            value["allocation_after"],
        )
    except (KeyError, TypeError) as error:
        raise MemoryIRError(
            "memory operation fields have invalid types"
        ) from error


def load_memory_model_json(text: str) -> MemoryModel:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise MemoryIRError(f"invalid memory model JSON: {error}") from error
    try:
        model = memory_model_from_dict(value)
    except (KeyError, TypeError) as error:
        raise MemoryIRError("memory model fields have invalid types") from error
    if model.to_json() != text:
        raise MemoryIRError("memory model JSON is not canonical")
    return model


def load_memory_operation_json(text: str) -> MemoryOperation:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise MemoryIRError(f"invalid memory operation JSON: {error}") from error
    operation = memory_operation_from_dict(value)
    if operation.to_json() != text:
        raise MemoryIRError("memory operation JSON is not canonical")
    return operation
