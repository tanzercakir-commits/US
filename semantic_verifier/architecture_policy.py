"""Strict, deterministic architectural dependency policy model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .facts import FactSymbol


ARCHITECTURE_POLICY_SCHEMA = "codeskeptic.architecture-policy/v1"
ARCHITECTURE_POLICY_ID_SCHEMA = (
    "codeskeptic.architecture-policy-identity/v1"
)
SELECTOR_KINDS = frozenset(
    {
        "qualified_name",
        "qualified_name_prefix",
        "source_prefix",
    }
)
DEPENDENCY_DECISIONS = frozenset({"allow", "forbid"})

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LAYER_NAME_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
_DRIVE_PATTERN = re.compile(r"[A-Za-z]:")


class ArchitecturePolicyError(ValueError):
    """Raised when an architecture policy violates the v1 contract."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _identity_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _policy_id(payload: Mapping[str, Any]) -> str:
    envelope = {
        "kind": "architecture-policy",
        "schema": ARCHITECTURE_POLICY_ID_SCHEMA,
        "value": payload,
    }
    digest = hashlib.sha256(_identity_bytes(envelope)).hexdigest()
    return f"sha256:{digest}"


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ArchitecturePolicyError(
            f"{field} must be non-empty text"
        )
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    field: str,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    unexpected = sorted(keys - required)
    if missing:
        raise ArchitecturePolicyError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unexpected:
        raise ArchitecturePolicyError(
            (
                f"{field} has unexpected fields: "
                f"{', '.join(unexpected)}"
            )
        )


def _normalize_source_prefix(value: object) -> str:
    text = _require_text(
        value,
        "selector.value",
    ).replace(chr(92), "/")
    if text.startswith("./"):
        text = text[2:]
    parts = text.split("/")
    if (
        not text
        or text.startswith("/")
        or _DRIVE_PATTERN.match(text)
        or "//" in text
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ArchitecturePolicyError(
            "source_prefix must be a normalized relative path prefix"
        )
    return text


@dataclass(frozen=True, order=True, slots=True)
class LayerSelector:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in SELECTOR_KINDS:
            raise ArchitecturePolicyError(
                f"selector.kind has unsupported value {self.kind!r}"
            )
        if self.kind == "source_prefix":
            normalized = _normalize_source_prefix(self.value)
        else:
            normalized = _require_text(
                self.value,
                "selector.value",
            )
        object.__setattr__(self, "value", normalized)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "value": self.value,
        }

    def matches(self, symbol: FactSymbol) -> bool:
        if self.kind == "qualified_name":
            return symbol.qualified_name == self.value
        if self.kind == "qualified_name_prefix":
            return symbol.qualified_name.startswith(self.value)
        return symbol.declaration.file.startswith(self.value)


@dataclass(frozen=True, slots=True)
class ArchitectureLayer:
    name: str
    selectors: tuple[LayerSelector, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or _LAYER_NAME_PATTERN.fullmatch(self.name) is None
        ):
            raise ArchitecturePolicyError(
                (
                    "layer.name must match "
                    "[a-z][a-z0-9-]{0,62}"
                )
            )
        ordered = tuple(sorted(self.selectors))
        if not ordered:
            raise ArchitecturePolicyError(
                f"layer {self.name!r} must have at least one selector"
            )
        if len(ordered) != len(set(ordered)):
            raise ArchitecturePolicyError(
                f"layer {self.name!r} has duplicate selectors"
            )
        object.__setattr__(self, "selectors", ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "selectors": [
                selector.to_dict()
                for selector in self.selectors
            ],
        }

    def matches(self, symbol: FactSymbol) -> bool:
        return any(
            selector.matches(symbol)
            for selector in self.selectors
        )


@dataclass(frozen=True, order=True, slots=True)
class DependencyRule:
    source_layer: str
    target_layer: str
    decision: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.source_layer, "dependency.from"),
            (self.target_layer, "dependency.to"),
        ):
            if (
                not isinstance(value, str)
                or _LAYER_NAME_PATTERN.fullmatch(value) is None
            ):
                raise ArchitecturePolicyError(
                    f"{field} must name a valid layer"
                )
        if self.decision not in DEPENDENCY_DECISIONS:
            raise ArchitecturePolicyError(
                (
                    "dependency.decision has unsupported value "
                    f"{self.decision!r}"
                )
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "decision": self.decision,
            "from": self.source_layer,
            "to": self.target_layer,
        }


@dataclass(frozen=True, slots=True)
class ArchitecturePolicy:
    id: str
    layers: tuple[ArchitectureLayer, ...]
    dependencies: tuple[DependencyRule, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or _HASH_PATTERN.fullmatch(self.id) is None
        ):
            raise ArchitecturePolicyError(
                "policy.id must be a lowercase sha256 identity"
            )

        layers = tuple(
            sorted(self.layers, key=lambda layer: layer.name)
        )
        if not layers:
            raise ArchitecturePolicyError(
                "policy must define at least one layer"
            )
        names = [layer.name for layer in layers]
        if len(names) != len(set(names)):
            raise ArchitecturePolicyError(
                "policy has duplicate layer names"
            )

        selectors: list[LayerSelector] = []
        for layer in layers:
            selectors.extend(layer.selectors)
        if len(selectors) != len(set(selectors)):
            raise ArchitecturePolicyError(
                "policy has duplicate selectors across layers"
            )

        dependencies = tuple(
            sorted(
                self.dependencies,
                key=lambda rule: (
                    rule.source_layer,
                    rule.target_layer,
                ),
            )
        )
        pairs = [
            (rule.source_layer, rule.target_layer)
            for rule in dependencies
        ]
        if len(pairs) != len(set(pairs)):
            raise ArchitecturePolicyError(
                "policy has duplicate dependency pairs"
            )

        name_set = set(names)
        for source, target in pairs:
            if source not in name_set or target not in name_set:
                raise ArchitecturePolicyError(
                    (
                        "dependency pair references unknown layer: "
                        f"{source!r} -> {target!r}"
                    )
                )

        expected_pairs = {
            (source, target)
            for source in names
            for target in names
        }
        missing = sorted(expected_pairs - set(pairs))
        if missing:
            rendered = ", ".join(
                f"{source}->{target}"
                for source, target in missing
            )
            raise ArchitecturePolicyError(
                f"policy is missing dependency pairs: {rendered}"
            )

        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "dependencies", dependencies)
        expected_id = _policy_id(self.content_dict())
        if self.id != expected_id:
            raise ArchitecturePolicyError(
                "policy.id does not match canonical policy content"
            )

    @classmethod
    def create(
        cls,
        *,
        layers: Sequence[ArchitectureLayer],
        dependencies: Sequence[DependencyRule],
    ) -> "ArchitecturePolicy":
        ordered_layers = tuple(
            sorted(layers, key=lambda layer: layer.name)
        )
        ordered_dependencies = tuple(
            sorted(
                dependencies,
                key=lambda rule: (
                    rule.source_layer,
                    rule.target_layer,
                ),
            )
        )
        content = {
            "dependencies": [
                rule.to_dict()
                for rule in ordered_dependencies
            ],
            "layers": [
                layer.to_dict()
                for layer in ordered_layers
            ],
            "schema": ARCHITECTURE_POLICY_SCHEMA,
        }
        return cls(
            _policy_id(content),
            ordered_layers,
            ordered_dependencies,
        )

    def content_dict(self) -> dict[str, Any]:
        return {
            "dependencies": [
                rule.to_dict()
                for rule in self.dependencies
            ],
            "layers": [
                layer.to_dict()
                for layer in self.layers
            ],
            "schema": ARCHITECTURE_POLICY_SCHEMA,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content_dict(),
            "id": self.id,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def classify(self, symbol: FactSymbol) -> tuple[str, ...]:
        return tuple(
            layer.name
            for layer in self.layers
            if layer.matches(symbol)
        )

    def decision(
        self,
        source_layer: str,
        target_layer: str,
    ) -> str:
        for rule in self.dependencies:
            if (
                rule.source_layer == source_layer
                and rule.target_layer == target_layer
            ):
                return rule.decision
        raise ArchitecturePolicyError(
            (
                "dependency decision requested for unknown pair: "
                f"{source_layer!r} -> {target_layer!r}"
            )
        )


def _selector_from_payload(
    payload: object,
    field: str,
) -> LayerSelector:
    if not isinstance(payload, Mapping):
        raise ArchitecturePolicyError(
            f"{field} must be an object"
        )
    _require_exact_keys(
        payload,
        frozenset({"kind", "value"}),
        field,
    )
    return LayerSelector(
        _require_text(payload["kind"], f"{field}.kind"),
        _require_text(payload["value"], f"{field}.value"),
    )


def _layer_from_payload(
    payload: object,
    index: int,
) -> ArchitectureLayer:
    field = f"layers[{index}]"
    if not isinstance(payload, Mapping):
        raise ArchitecturePolicyError(
            f"{field} must be an object"
        )
    _require_exact_keys(
        payload,
        frozenset({"name", "selectors"}),
        field,
    )
    selectors = payload["selectors"]
    if not isinstance(selectors, list):
        raise ArchitecturePolicyError(
            f"{field}.selectors must be an array"
        )
    return ArchitectureLayer(
        _require_text(payload["name"], f"{field}.name"),
        tuple(
            _selector_from_payload(
                selector,
                f"{field}.selectors[{selector_index}]",
            )
            for selector_index, selector in enumerate(selectors)
        ),
    )


def _dependency_from_payload(
    payload: object,
    index: int,
) -> DependencyRule:
    field = f"dependencies[{index}]"
    if not isinstance(payload, Mapping):
        raise ArchitecturePolicyError(
            f"{field} must be an object"
        )
    _require_exact_keys(
        payload,
        frozenset({"decision", "from", "to"}),
        field,
    )
    return DependencyRule(
        _require_text(payload["from"], f"{field}.from"),
        _require_text(payload["to"], f"{field}.to"),
        _require_text(
            payload["decision"],
            f"{field}.decision",
        ),
    )


def load_architecture_policy(
    payload: Mapping[str, Any],
) -> ArchitecturePolicy:
    """Load and strictly validate an architecture-policy/v1 mapping."""

    _require_exact_keys(
        payload,
        frozenset({"dependencies", "id", "layers", "schema"}),
        "policy",
    )
    if payload["schema"] != ARCHITECTURE_POLICY_SCHEMA:
        raise ArchitecturePolicyError(
            (
                "policy.schema must be "
                f"{ARCHITECTURE_POLICY_SCHEMA!r}"
            )
        )
    layers = payload["layers"]
    dependencies = payload["dependencies"]
    if not isinstance(layers, list):
        raise ArchitecturePolicyError(
            "policy.layers must be an array"
        )
    if not isinstance(dependencies, list):
        raise ArchitecturePolicyError(
            "policy.dependencies must be an array"
        )
    return ArchitecturePolicy(
        _require_text(payload["id"], "policy.id"),
        tuple(
            _layer_from_payload(layer, index)
            for index, layer in enumerate(layers)
        ),
        tuple(
            _dependency_from_payload(rule, index)
            for index, rule in enumerate(dependencies)
        ),
    )


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArchitecturePolicyError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ArchitecturePolicyError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def load_architecture_policy_json(text: str) -> ArchitecturePolicy:
    """Parse strict JSON and return a validated architecture policy."""

    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ArchitecturePolicyError(
            f"invalid architecture-policy JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise ArchitecturePolicyError(
            "architecture policy must be a JSON object"
        )
    return load_architecture_policy(payload)


def read_architecture_policy(
    path: str | Path,
) -> ArchitecturePolicy:
    """Read strict UTF-8 policy JSON from disk."""

    return load_architecture_policy_json(
        Path(path).read_bytes().decode("utf-8")
    )
