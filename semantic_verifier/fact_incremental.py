"""Strict content-addressed incremental translation-unit fact extraction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Protocol

from .fact_extractor import ClangFactExtractor
from .facts import (
    FACT_SCHEMA,
    FactIndex,
    FactIndexError,
    load_fact_index,
)


TRANSLATION_UNITS_SCHEMA = "codeskeptic.translation-units/v1"
CACHE_MANIFEST_SCHEMA = "codeskeptic.fact-cache-manifest/v1"
CACHE_RUN_SCHEMA = "codeskeptic.fact-cache-run/v1"
EXTRACTOR_CONTRACT = "codeskeptic.clang-fact-extractor/v1"
CACHE_ID_SCHEMA = "codeskeptic.fact-cache-identity/v1"

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DRIVE_PATTERN = re.compile(r"[A-Za-z]:")


class FactIncrementalError(ValueError):
    """Raised when incremental extraction state violates its contract."""


class FactExtractor(Protocol):
    def extract_file(
        self,
        path: str | os.PathLike[str],
        *,
        display_path: str | None = None,
    ) -> FactIndex:
        """Extract one translation unit."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _identity_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _content_id(kind: str, payload: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": CACHE_ID_SCHEMA,
        "value": payload,
    }
    return _sha256(_identity_bytes(envelope))


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise FactIncrementalError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_PATTERN.fullmatch(text) is None:
        raise FactIncrementalError(
            f"{field} must be a lowercase sha256 identity"
        )
    return text


def _require_exact_keys(
    payload: Mapping[str, Any],
    required: frozenset[str],
    field: str,
) -> None:
    keys = set(payload)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise FactIncrementalError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise FactIncrementalError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


def _normalized_path(value: object, field: str) -> str:
    text = _require_text(value, field)
    parts = text.split("/")
    if (
        text.startswith("/")
        or _DRIVE_PATTERN.match(text)
        or chr(92) in text
        or "//" in text
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise FactIncrementalError(
            f"{field} must be a normalized relative POSIX path"
        )
    return text


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FactIncrementalError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FactIncrementalError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def _strict_json(text: str, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise FactIncrementalError(
            f"invalid {label} JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise FactIncrementalError(f"{label} must be a JSON object")
    return payload


@dataclass(frozen=True, order=True, slots=True)
class TranslationUnit:
    source: str
    display_path: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _normalized_path(self.source, "unit.source"),
        )
        object.__setattr__(
            self,
            "display_path",
            _normalized_path(
                self.display_path,
                "unit.display_path",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "display_path": self.display_path,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class TranslationUnitManifest:
    units: tuple[TranslationUnit, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.units))
        if not ordered:
            raise FactIncrementalError(
                "translation-unit manifest must declare at least one unit"
            )
        sources = [unit.source for unit in ordered]
        displays = [unit.display_path for unit in ordered]
        if len(sources) != len(set(sources)):
            raise FactIncrementalError(
                "translation-unit sources must not contain duplicates"
            )
        if len(displays) != len(set(displays)):
            raise FactIncrementalError(
                "translation-unit display paths must not contain duplicates"
            )
        object.__setattr__(self, "units", ordered)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": TRANSLATION_UNITS_SCHEMA,
            "units": [unit.to_dict() for unit in self.units],
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, order=True, slots=True)
class FactCacheEntry:
    source: str
    display_path: str
    source_sha256: str
    cache_key: str
    fact_index_id: str
    index: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _normalized_path(self.source, "cache unit.source"),
        )
        object.__setattr__(
            self,
            "display_path",
            _normalized_path(
                self.display_path,
                "cache unit.display_path",
            ),
        )
        _require_hash(self.source_sha256, "cache unit.source_sha256")
        key = _require_hash(self.cache_key, "cache unit.cache_key")
        _require_hash(self.fact_index_id, "cache unit.fact_index_id")
        expected_key = _cache_key(
            self.display_path,
            self.source_sha256,
        )
        if key != expected_key:
            raise FactIncrementalError(
                "cache unit.cache_key does not match canonical inputs"
            )
        expected_index = (
            f"units/{key.removeprefix('sha256:')}.fact-index.json"
        )
        normalized_index = _normalized_path(
            self.index,
            "cache unit.index",
        )
        if normalized_index != expected_index:
            raise FactIncrementalError(
                "cache unit.index does not match cache_key"
            )
        object.__setattr__(self, "index", normalized_index)

    def to_dict(self) -> dict[str, str]:
        return {
            "cache_key": self.cache_key,
            "display_path": self.display_path,
            "fact_index_id": self.fact_index_id,
            "index": self.index,
            "source": self.source,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class FactCacheManifest:
    manifest_id: str
    units: tuple[FactCacheEntry, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.units))
        sources = [entry.source for entry in ordered]
        displays = [entry.display_path for entry in ordered]
        keys = [entry.cache_key for entry in ordered]
        if len(sources) != len(set(sources)):
            raise FactIncrementalError(
                "cache sources must not contain duplicates"
            )
        if len(displays) != len(set(displays)):
            raise FactIncrementalError(
                "cache display paths must not contain duplicates"
            )
        if len(keys) != len(set(keys)):
            raise FactIncrementalError(
                "cache keys must not contain duplicates"
            )
        object.__setattr__(self, "units", ordered)
        expected = _content_id("fact-cache-manifest", self.content_dict())
        if _require_hash(
            self.manifest_id,
            "cache manifest_id",
        ) != expected:
            raise FactIncrementalError(
                "cache manifest_id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        units: Sequence[FactCacheEntry],
    ) -> "FactCacheManifest":
        ordered = tuple(sorted(units))
        content = {
            "extractor_contract": EXTRACTOR_CONTRACT,
            "fact_schema": FACT_SCHEMA,
            "schema": CACHE_MANIFEST_SCHEMA,
            "units": [entry.to_dict() for entry in ordered],
        }
        return cls(
            _content_id("fact-cache-manifest", content),
            ordered,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "extractor_contract": EXTRACTOR_CONTRACT,
            "fact_schema": FACT_SCHEMA,
            "schema": CACHE_MANIFEST_SCHEMA,
            "units": [entry.to_dict() for entry in self.units],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.content_dict(),
            "manifest_id": self.manifest_id,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class IncrementalRun:
    mode: str
    status: str
    manifest_id: str | None
    added: tuple[str, ...]
    extracted: tuple[str, ...]
    removed: tuple[str, ...]
    reused: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode not in {"check", "write"}:
            raise FactIncrementalError("run mode must be check or write")
        if self.status not in {"current", "stale", "updated"}:
            raise FactIncrementalError(
                "run status must be current, stale, or updated"
            )
        for field in ("added", "extracted", "removed", "reused"):
            values = tuple(sorted(getattr(self, field)))
            if len(values) != len(set(values)):
                raise FactIncrementalError(
                    f"run {field} must not contain duplicates"
                )
            object.__setattr__(self, field, values)
        if self.manifest_id is not None:
            _require_hash(self.manifest_id, "run manifest_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "added": list(self.added),
            "extracted": list(self.extracted),
            "manifest_id": self.manifest_id,
            "mode": self.mode,
            "removed": list(self.removed),
            "reused": list(self.reused),
            "schema": CACHE_RUN_SCHEMA,
            "status": self.status,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def load_translation_units_json(text: str) -> TranslationUnitManifest:
    payload = _strict_json(text, "translation-unit manifest")
    _require_exact_keys(
        payload,
        frozenset({"schema", "units"}),
        "translation-unit manifest",
    )
    if payload["schema"] != TRANSLATION_UNITS_SCHEMA:
        raise FactIncrementalError(
            "unsupported translation-unit manifest schema"
        )
    raw_units = payload["units"]
    if not isinstance(raw_units, list):
        raise FactIncrementalError(
            "translation-unit manifest.units must be an array"
        )
    units: list[TranslationUnit] = []
    for index, raw in enumerate(raw_units):
        if not isinstance(raw, Mapping):
            raise FactIncrementalError(
                f"translation-unit manifest.units[{index}] must be an object"
            )
        _require_exact_keys(
            raw,
            frozenset({"display_path", "source"}),
            f"translation-unit manifest.units[{index}]",
        )
        units.append(
            TranslationUnit(
                raw["source"],
                raw["display_path"],
            )
        )
    return TranslationUnitManifest(tuple(units))


def load_cache_manifest_json(text: str) -> FactCacheManifest:
    payload = _strict_json(text, "fact-cache manifest")
    _require_exact_keys(
        payload,
        frozenset(
            {
                "extractor_contract",
                "fact_schema",
                "manifest_id",
                "schema",
                "units",
            }
        ),
        "fact-cache manifest",
    )
    if payload["schema"] != CACHE_MANIFEST_SCHEMA:
        raise FactIncrementalError(
            "unsupported fact-cache manifest schema"
        )
    if payload["extractor_contract"] != EXTRACTOR_CONTRACT:
        raise FactIncrementalError(
            "unsupported fact-cache extractor contract"
        )
    if payload["fact_schema"] != FACT_SCHEMA:
        raise FactIncrementalError(
            "unsupported fact-cache fact schema"
        )
    raw_units = payload["units"]
    if not isinstance(raw_units, list):
        raise FactIncrementalError(
            "fact-cache manifest.units must be an array"
        )
    entries: list[FactCacheEntry] = []
    required = frozenset(
        {
            "cache_key",
            "display_path",
            "fact_index_id",
            "index",
            "source",
            "source_sha256",
        }
    )
    for index, raw in enumerate(raw_units):
        if not isinstance(raw, Mapping):
            raise FactIncrementalError(
                f"fact-cache manifest.units[{index}] must be an object"
            )
        _require_exact_keys(
            raw,
            required,
            f"fact-cache manifest.units[{index}]",
        )
        entries.append(
            FactCacheEntry(
                raw["source"],
                raw["display_path"],
                raw["source_sha256"],
                raw["cache_key"],
                raw["fact_index_id"],
                raw["index"],
            )
        )
    return FactCacheManifest(
        _require_hash(payload["manifest_id"], "cache manifest_id"),
        tuple(entries),
    )


def _cache_key(display_path: str, source_sha256: str) -> str:
    payload = {
        "display_path": display_path,
        "extractor_contract": EXTRACTOR_CONTRACT,
        "fact_schema": FACT_SCHEMA,
        "source_sha256": source_sha256,
    }
    return _content_id("translation-unit-cache-key", payload)


def _read_source(
    workspace: Path,
    unit: TranslationUnit,
) -> tuple[Path, str, str]:
    root = workspace.resolve()
    physical = (root / Path(unit.source)).resolve()
    try:
        physical.relative_to(root)
    except ValueError as error:
        raise FactIncrementalError(
            f"unit source escapes workspace: {unit.source}"
        ) from error
    try:
        raw = physical.read_bytes()
        source = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise FactIncrementalError(
            f"cannot read unit {unit.source}: {error}"
        ) from error
    return physical, source, _sha256(raw)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _strict_fact_index(data: bytes, entry: FactCacheEntry) -> FactIndex:
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise FactIncrementalError(
            f"cached index is not UTF-8: {entry.index}"
        ) from error
    payload = _strict_json(text, "cached fact-index")
    try:
        fact_index = load_fact_index(payload)
    except FactIndexError as error:
        raise FactIncrementalError(
            f"invalid cached fact-index {entry.index}: {error}"
        ) from error
    if fact_index.to_json().encode("utf-8") != data:
        raise FactIncrementalError(
            f"cached fact-index is not canonical: {entry.index}"
        )
    if fact_index.id != entry.fact_index_id:
        raise FactIncrementalError(
            f"cached fact-index identity mismatch: {entry.index}"
        )
    if fact_index.source.file != entry.display_path:
        raise FactIncrementalError(
            f"cached fact-index display path mismatch: {entry.index}"
        )
    if fact_index.source.content_sha256 != entry.source_sha256:
        raise FactIncrementalError(
            f"cached fact-index source hash mismatch: {entry.index}"
        )
    return fact_index


def _load_previous(cache_dir: Path) -> FactCacheManifest | None:
    path = cache_dir / "current.json"
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise FactIncrementalError(
            f"cannot read current cache manifest: {error}"
        ) from error
    manifest = load_cache_manifest_json(text)
    if manifest.to_json().encode("utf-8") != data:
        raise FactIncrementalError(
            "current cache manifest is not canonical"
        )
    return manifest


def extract_incrementally(
    workspace: str | os.PathLike[str],
    declaration: TranslationUnitManifest,
    cache_dir: str | os.PathLike[str],
    *,
    extractor: FactExtractor | None = None,
    clang: str | None = None,
    check: bool = False,
) -> IncrementalRun:
    """Check or update the exact current translation-unit fact cache."""

    workspace_path = Path(workspace)
    cache_path = Path(cache_dir)
    previous = _load_previous(cache_path)
    prior_entries = (
        {entry.source: entry for entry in previous.units}
        if previous is not None
        else {}
    )
    current_sources = {unit.source for unit in declaration.units}
    prior_sources = set(prior_entries)
    added = tuple(sorted(current_sources - prior_sources))
    removed = tuple(sorted(prior_sources - current_sources))
    reused: list[str] = []
    missing: list[
        tuple[TranslationUnit, Path, str, str, FactCacheEntry | None]
    ] = []
    entries: list[FactCacheEntry] = []

    for unit in declaration.units:
        physical, source, source_sha256 = _read_source(
            workspace_path,
            unit,
        )
        if _sha256(source.encode("utf-8")) != source_sha256:
            raise FactIncrementalError(
                f"unit UTF-8 hash mismatch: {unit.source}"
            )
        key = _cache_key(unit.display_path, source_sha256)
        prior = prior_entries.get(unit.source)
        if prior is not None and prior.cache_key == key:
            index_path = cache_path / Path(prior.index)
            try:
                data = index_path.read_bytes()
            except OSError as error:
                raise FactIncrementalError(
                    f"cannot read cached index {prior.index}: {error}"
                ) from error
            _strict_fact_index(data, prior)
            entries.append(prior)
            reused.append(unit.source)
        else:
            missing.append(
                (unit, physical, source_sha256, key, prior)
            )

    extracted = tuple(item[0].source for item in missing)
    stale = bool(extracted or removed)
    if check:
        return IncrementalRun(
            "check",
            "stale" if stale else "current",
            previous.manifest_id if previous is not None else None,
            added,
            extracted,
            removed,
            tuple(reused),
        )

    active_extractor = extractor
    for unit, physical, source_sha256, key, _prior in missing:
        if active_extractor is None:
            active_extractor = ClangFactExtractor(clang)
        try:
            fact_index = active_extractor.extract_file(
                physical,
                display_path=unit.display_path,
            )
        except Exception as error:
            if isinstance(error, FactIncrementalError):
                raise
            raise FactIncrementalError(
                f"fact extraction failed for {unit.source}: {error}"
            ) from error
        if fact_index.source.file != unit.display_path:
            raise FactIncrementalError(
                f"extractor returned wrong display path for {unit.source}"
            )
        if fact_index.source.content_sha256 != source_sha256:
            raise FactIncrementalError(
                f"extractor returned wrong source hash for {unit.source}"
            )
        relative_index = (
            f"units/{key.removeprefix('sha256:')}.fact-index.json"
        )
        entry = FactCacheEntry(
            unit.source,
            unit.display_path,
            source_sha256,
            key,
            fact_index.id,
            relative_index,
        )
        rendered = fact_index.to_json().encode("utf-8")
        _strict_fact_index(rendered, entry)
        _atomic_write(cache_path / Path(relative_index), rendered)
        entries.append(entry)

    manifest = FactCacheManifest.create(entries)
    rendered_manifest = manifest.to_json().encode("utf-8")
    current_path = cache_path / "current.json"
    try:
        actual_manifest = current_path.read_bytes()
    except FileNotFoundError:
        actual_manifest = None
    except OSError as error:
        raise FactIncrementalError(
            f"cannot read current cache manifest: {error}"
        ) from error
    if actual_manifest != rendered_manifest:
        _atomic_write(current_path, rendered_manifest)
    return IncrementalRun(
        "write",
        "updated" if stale else "current",
        manifest.manifest_id,
        added,
        extracted,
        removed,
        tuple(reused),
    )


def read_translation_units(path: str | os.PathLike[str]) -> TranslationUnitManifest:
    try:
        return load_translation_units_json(
            Path(path).read_bytes().decode("utf-8")
        )
    except (OSError, UnicodeError) as error:
        raise FactIncrementalError(
            f"cannot read translation-unit manifest: {error}"
        ) from error
