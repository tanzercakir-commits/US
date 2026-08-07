"""Immutable assumption declarations and linked resolution evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


ASSUMPTION_MANIFEST_SCHEMA = "codeskeptic.assumption-manifest/v1"
ASSUMPTION_RESOLUTION_SCHEMA = "codeskeptic.assumption-resolution/v1"
ASSUMPTION_SUMMARY_SCHEMA = "codeskeptic.assumption-summary/v1"
ASSUMPTION_IDENTITY_SCHEMA = "codeskeptic.assumption-identity/v1"
DISPOSITIONS = ("contract", "test", "uncheckable")
RISKS = ("high", "low", "medium")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ASSUMPTION_RE = re.compile(r"asm-[0-9]{3,}\Z")


class AssumptionManifestError(ValueError):
    """Raised when declarations or evidence fail closed."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": ASSUMPTION_IDENTITY_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def normalized_text(text: str) -> str:
    if text.startswith("\ufeff") or "\x00" in text:
        raise AssumptionManifestError(
            "repository evidence must be BOM-free UTF-8 without NUL"
        )
    return text.replace("\r\n", "\n").replace("\r", "\n")


def text_sha256(text: str) -> str:
    normalized = normalized_text(text)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise AssumptionManifestError(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AssumptionManifestError(f"{field_name} must be non-empty text")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    field_name: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise AssumptionManifestError(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise AssumptionManifestError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _safe_path(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AssumptionManifestError(
            f"{field_name} must be a canonical repository-relative path"
        )
    return text


@dataclass(frozen=True, order=True, slots=True)
class SnapshotFile:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _safe_path(self.path, "snapshot.path")
        _require_hash(self.sha256, "snapshot.sha256")

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, order=True, slots=True)
class Assumption:
    id: str
    statement: str
    scope: str
    risk: str
    intended_disposition: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _ASSUMPTION_RE.fullmatch(self.id) is None:
            raise AssumptionManifestError("assumption.id is unsupported")
        _require_text(self.statement, "assumption.statement")
        _require_text(self.scope, "assumption.scope")
        if self.risk not in RISKS:
            raise AssumptionManifestError("assumption.risk is unsupported")
        if self.intended_disposition not in DISPOSITIONS:
            raise AssumptionManifestError(
                "assumption.intended_disposition is unsupported"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "intended_disposition": self.intended_disposition,
            "risk": self.risk,
            "scope": self.scope,
            "statement": self.statement,
        }


@dataclass(frozen=True, slots=True)
class AssumptionManifest:
    id: str
    subject: str
    snapshot: tuple[SnapshotFile, ...]
    assumptions: tuple[Assumption, ...]

    def __post_init__(self) -> None:
        _require_text(self.subject, "manifest.subject")
        snapshot = tuple(self.snapshot)
        assumptions = tuple(self.assumptions)
        if not snapshot or not assumptions:
            raise AssumptionManifestError(
                "manifest requires snapshot files and assumptions"
            )
        if snapshot != tuple(sorted(snapshot)):
            raise AssumptionManifestError("manifest snapshot must be sorted")
        if assumptions != tuple(sorted(assumptions, key=lambda item: item.id)):
            raise AssumptionManifestError("manifest assumptions must be sorted")
        if len({item.path for item in snapshot}) != len(snapshot):
            raise AssumptionManifestError("manifest snapshot paths duplicate")
        if len({item.id for item in assumptions}) != len(assumptions):
            raise AssumptionManifestError("manifest assumption IDs duplicate")
        object.__setattr__(self, "snapshot", snapshot)
        object.__setattr__(self, "assumptions", assumptions)
        expected = _content_id("assumption-manifest", self.content_dict())
        if _require_hash(self.id, "manifest.id") != expected:
            raise AssumptionManifestError(
                "manifest.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        subject: str,
        snapshot: Sequence[SnapshotFile],
        assumptions: Sequence[Assumption],
    ) -> "AssumptionManifest":
        ordered_snapshot = tuple(sorted(snapshot))
        ordered_assumptions = tuple(sorted(assumptions, key=lambda item: item.id))
        content = {
            "assumptions": [item.to_dict() for item in ordered_assumptions],
            "schema": ASSUMPTION_MANIFEST_SCHEMA,
            "snapshot": [item.to_dict() for item in ordered_snapshot],
            "subject": subject,
        }
        return cls(
            _content_id("assumption-manifest", content),
            subject,
            ordered_snapshot,
            ordered_assumptions,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "assumptions": [item.to_dict() for item in self.assumptions],
            "schema": ASSUMPTION_MANIFEST_SCHEMA,
            "snapshot": [item.to_dict() for item in self.snapshot],
            "subject": self.subject,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, order=True, slots=True)
class ResolutionEvidence:
    path: str
    sha256: str
    anchor: str

    def __post_init__(self) -> None:
        _safe_path(self.path, "evidence.path")
        _require_hash(self.sha256, "evidence.sha256")
        _require_text(self.anchor, "evidence.anchor")

    def to_dict(self) -> dict[str, str]:
        return {
            "anchor": self.anchor,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, order=True, slots=True)
class AssumptionResolutionRow:
    assumption: str
    disposition: str
    evidence: tuple[ResolutionEvidence, ...]
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.assumption, str)
            or _ASSUMPTION_RE.fullmatch(self.assumption) is None
        ):
            raise AssumptionManifestError(
                "resolution.assumption is unsupported"
            )
        if self.disposition not in DISPOSITIONS:
            raise AssumptionManifestError(
                "resolution.disposition is unsupported"
            )
        evidence = tuple(self.evidence)
        if evidence != tuple(sorted(evidence)):
            raise AssumptionManifestError("resolution evidence must be sorted")
        if len(evidence) != len(set(evidence)):
            raise AssumptionManifestError("resolution evidence duplicates")
        if self.disposition == "uncheckable":
            if evidence or self.reason is None:
                raise AssumptionManifestError(
                    "uncheckable resolution requires only a reason"
                )
            _require_text(self.reason, "resolution.reason")
        else:
            if not evidence or self.reason is not None:
                raise AssumptionManifestError(
                    "contract/test resolution requires evidence and null reason"
                )
        object.__setattr__(self, "evidence", evidence)

    def to_dict(self) -> dict[str, object]:
        return {
            "assumption": self.assumption,
            "disposition": self.disposition,
            "evidence": [item.to_dict() for item in self.evidence],
            "reason": self.reason,
        }

@dataclass(frozen=True, slots=True)
class AssumptionResolution:
    id: str
    manifest: str
    resolutions: tuple[AssumptionResolutionRow, ...]

    def __post_init__(self) -> None:
        _require_hash(self.manifest, "resolution.manifest")
        rows = tuple(self.resolutions)
        if not rows:
            raise AssumptionManifestError("resolution requires rows")
        if rows != tuple(sorted(rows, key=lambda item: item.assumption)):
            raise AssumptionManifestError("resolution rows must be sorted")
        if len({item.assumption for item in rows}) != len(rows):
            raise AssumptionManifestError("resolution assumptions duplicate")
        object.__setattr__(self, "resolutions", rows)
        expected = _content_id("assumption-resolution", self.content_dict())
        if _require_hash(self.id, "resolution.id") != expected:
            raise AssumptionManifestError(
                "resolution.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        manifest: str,
        resolutions: Sequence[AssumptionResolutionRow],
    ) -> "AssumptionResolution":
        rows = tuple(sorted(resolutions, key=lambda item: item.assumption))
        content = {
            "manifest": manifest,
            "resolutions": [item.to_dict() for item in rows],
            "schema": ASSUMPTION_RESOLUTION_SCHEMA,
        }
        return cls(
            _content_id("assumption-resolution", content),
            manifest,
            rows,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest,
            "resolutions": [item.to_dict() for item in self.resolutions],
            "schema": ASSUMPTION_RESOLUTION_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssumptionManifestError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AssumptionManifestError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def _parse_json(text: str, field_name: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise AssumptionManifestError(
            f"invalid {field_name} JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise AssumptionManifestError(f"{field_name} must be an object")
    return value


def load_assumption_manifest_json(text: str) -> AssumptionManifest:
    payload = _parse_json(text, "assumption manifest")
    _exact_keys(
        payload,
        {"assumptions", "id", "schema", "snapshot", "subject"},
        "manifest",
    )
    if payload["schema"] != ASSUMPTION_MANIFEST_SCHEMA:
        raise AssumptionManifestError("unsupported assumption manifest schema")
    raw_snapshot = payload["snapshot"]
    raw_assumptions = payload["assumptions"]
    if not isinstance(raw_snapshot, list) or not isinstance(raw_assumptions, list):
        raise AssumptionManifestError(
            "manifest snapshot and assumptions must be arrays"
        )
    snapshot: list[SnapshotFile] = []
    for index, raw in enumerate(raw_snapshot):
        field_name = f"manifest.snapshot[{index}]"
        if not isinstance(raw, Mapping):
            raise AssumptionManifestError(f"{field_name} must be an object")
        _exact_keys(raw, {"path", "sha256"}, field_name)
        snapshot.append(SnapshotFile(raw["path"], raw["sha256"]))
    assumptions: list[Assumption] = []
    for index, raw in enumerate(raw_assumptions):
        field_name = f"manifest.assumptions[{index}]"
        if not isinstance(raw, Mapping):
            raise AssumptionManifestError(f"{field_name} must be an object")
        _exact_keys(
            raw,
            {"id", "intended_disposition", "risk", "scope", "statement"},
            field_name,
        )
        assumptions.append(
            Assumption(
                raw["id"],
                raw["statement"],
                raw["scope"],
                raw["risk"],
                raw["intended_disposition"],
            )
        )
    manifest = AssumptionManifest.create(
        subject=payload["subject"],
        snapshot=snapshot,
        assumptions=assumptions,
    )
    if payload["id"] != manifest.id:
        raise AssumptionManifestError("manifest identity is stale")
    return manifest


def load_assumption_resolution_json(text: str) -> AssumptionResolution:
    payload = _parse_json(text, "assumption resolution")
    _exact_keys(payload, {"id", "manifest", "resolutions", "schema"}, "resolution")
    if payload["schema"] != ASSUMPTION_RESOLUTION_SCHEMA:
        raise AssumptionManifestError("unsupported assumption resolution schema")
    raw_rows = payload["resolutions"]
    if not isinstance(raw_rows, list):
        raise AssumptionManifestError("resolution.resolutions must be an array")
    rows: list[AssumptionResolutionRow] = []
    for index, raw in enumerate(raw_rows):
        field_name = f"resolution.resolutions[{index}]"
        if not isinstance(raw, Mapping):
            raise AssumptionManifestError(f"{field_name} must be an object")
        _exact_keys(
            raw,
            {"assumption", "disposition", "evidence", "reason"},
            field_name,
        )
        raw_evidence = raw["evidence"]
        if not isinstance(raw_evidence, list):
            raise AssumptionManifestError(
                f"{field_name}.evidence must be an array"
            )
        evidence: list[ResolutionEvidence] = []
        for evidence_index, item in enumerate(raw_evidence):
            evidence_field = f"{field_name}.evidence[{evidence_index}]"
            if not isinstance(item, Mapping):
                raise AssumptionManifestError(
                    f"{evidence_field} must be an object"
                )
            _exact_keys(item, {"anchor", "path", "sha256"}, evidence_field)
            evidence.append(
                ResolutionEvidence(
                    item["path"],
                    item["sha256"],
                    item["anchor"],
                )
            )
        rows.append(
            AssumptionResolutionRow(
                raw["assumption"],
                raw["disposition"],
                tuple(sorted(evidence)),
                raw["reason"],
            )
        )
    resolution = AssumptionResolution.create(
        manifest=payload["manifest"],
        resolutions=rows,
    )
    if payload["id"] != resolution.id:
        raise AssumptionManifestError("resolution identity is stale")
    return resolution


def _rooted_file(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    candidate = root_resolved.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise AssumptionManifestError(
            f"repository evidence is missing: {relative}: {error}"
        ) from error
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise AssumptionManifestError(
            f"repository evidence escapes root: {relative}"
        ) from error
    if not resolved.is_file():
        raise AssumptionManifestError(
            f"repository evidence is not a file: {relative}"
        )
    return resolved


def repository_text(root: str | Path, relative: str) -> str:
    path = _rooted_file(Path(root), _safe_path(relative, "repository.path"))
    try:
        return normalized_text(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError) as error:
        raise AssumptionManifestError(
            f"cannot read UTF-8 repository evidence {relative}: {error}"
        ) from error


def snapshot_file(root: str | Path, relative: str) -> SnapshotFile:
    canonical = _safe_path(relative, "snapshot.path")
    return SnapshotFile(canonical, text_sha256(repository_text(root, canonical)))


def validate_assumption_resolution(
    manifest: AssumptionManifest,
    resolution: AssumptionResolution,
    root: str | Path,
) -> dict[str, object]:
    if resolution.manifest != manifest.id:
        raise AssumptionManifestError(
            "resolution does not link the supplied manifest"
        )
    declared = {item.id: item for item in manifest.assumptions}
    resolved = {item.assumption: item for item in resolution.resolutions}
    if set(resolved) != set(declared):
        missing = sorted(set(declared) - set(resolved))
        extra = sorted(set(resolved) - set(declared))
        raise AssumptionManifestError(
            f"resolution coverage differs; missing={missing!r}, extra={extra!r}"
        )
    for item in manifest.snapshot:
        actual = text_sha256(repository_text(root, item.path))
        if actual != item.sha256:
            raise AssumptionManifestError(
                f"manifest snapshot hash is stale: {item.path}"
            )
    counts = {disposition: 0 for disposition in DISPOSITIONS}
    for assumption_id in sorted(declared):
        assumption = declared[assumption_id]
        row = resolved[assumption_id]
        if row.disposition != assumption.intended_disposition:
            raise AssumptionManifestError(
                f"resolution disposition differs for {assumption_id}"
            )
        counts[row.disposition] += 1
        for evidence in row.evidence:
            text = repository_text(root, evidence.path)
            if text_sha256(text) != evidence.sha256:
                raise AssumptionManifestError(
                    f"resolution evidence hash is stale: {evidence.path}"
                )
            if evidence.anchor not in text:
                raise AssumptionManifestError(
                    f"resolution evidence anchor is absent: {evidence.path}"
                )
    return {
        "contract": counts["contract"],
        "declared": len(declared),
        "manifest": manifest.id,
        "resolution": resolution.id,
        "resolved_checkable": counts["contract"] + counts["test"],
        "schema": ASSUMPTION_SUMMARY_SCHEMA,
        "test": counts["test"],
        "uncheckable": counts["uncheckable"],
    }


def summary_json(summary: Mapping[str, object]) -> str:
    return _canonical_json(summary)
