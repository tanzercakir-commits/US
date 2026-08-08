"""Deterministic, fail-closed C++ project manifest ingestion."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
from typing import Any


PROJECT_MANIFEST_SCHEMA = "codeskeptic.project-manifest/v1"
PROJECT_MANIFEST_ID_SCHEMA = "codeskeptic.project-manifest-identity/v1"

CPP_SUFFIXES = frozenset({".cc", ".cpp", ".cxx", ".c++", ".C"})
SKIPPED_SUFFIXES = frozenset({".c"})
COMMAND_STYLES = frozenset({"posix", "windows"})
SKIP_REASONS = frozenset({"non_cpp_language"})
REJECTION_REASONS = frozenset(
    {
        "ambiguous_command_fields",
        "command_style_required",
        "directory_missing",
        "duplicate_source_entry",
        "invalid_arguments",
        "invalid_directory",
        "invalid_entry",
        "invalid_file",
        "invalid_output",
        "malformed_command",
        "missing_command",
        "outside_project_root",
        "response_file_unsupported",
        "shell_operator_unsupported",
        "source_argument_ambiguous",
        "source_argument_missing",
        "source_missing",
        "source_unreadable",
        "unexpected_fields",
        "unsupported_source_extension",
    }
)

_ENTRY_FIELDS = frozenset({"arguments", "command", "directory", "file", "output"})
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SHELL_OPERATORS = frozenset({"&&", "||", "|", ";", ">", ">>", "<"})
_DROP_FLAGS = frozenset({"-c", "-MD", "-MMD", "-MP"})
_DROP_VALUE_FLAGS = frozenset({"-MF", "-MQ", "-MT", "-o"})


class ProjectManifestError(ValueError):
    """Raised when the project request or manifest envelope is invalid."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def _identity_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": PROJECT_MANIFEST_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _text_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _normalized_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return relative or "."


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path))


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProjectManifestError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_RE.fullmatch(text) is None:
        raise ProjectManifestError(f"{field} must be a lowercase sha256 identity")
    return text


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise ProjectManifestError(
            f"{field} fields must be exactly {sorted(expected)!r}"
        )


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
        raise ProjectManifestError(f"{field} must be project-relative")
    return text.removeprefix("./") or "."


@dataclass(frozen=True, slots=True)
class ProjectManifestRequest:
    project_root: Path
    compilation_database: Path = Path("compile_commands.json")
    command_style: str | None = None

    def __post_init__(self) -> None:
        try:
            root = Path(self.project_root)
            database = Path(self.compilation_database)
        except TypeError as error:
            raise ProjectManifestError("project request paths are invalid") from error
        if self.command_style is not None and self.command_style not in COMMAND_STYLES:
            raise ProjectManifestError(
                f"command_style must be one of {sorted(COMMAND_STYLES)!r}"
            )
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "compilation_database", database)


@dataclass(frozen=True, order=True, slots=True)
class ProjectTranslationUnit:
    file: str
    directory: str
    language: str
    content_sha256: str
    arguments: tuple[str, ...]
    id: str

    def __post_init__(self) -> None:
        normalized_file = _logical_path(self.file, "unit.file")
        normalized_directory = _logical_path(self.directory, "unit.directory")
        if normalized_file == ".":
            raise ProjectManifestError("unit.file must name a source file")
        if self.language != "c++17":
            raise ProjectManifestError("unit.language must be 'c++17'")
        _require_hash(self.content_sha256, "unit.content_sha256")
        if not self.arguments or any(
            not isinstance(argument, str) or not argument
            for argument in self.arguments
        ):
            raise ProjectManifestError("unit.arguments must be non-empty text")
        _require_hash(self.id, "unit.id")
        object.__setattr__(self, "file", normalized_file)
        object.__setattr__(self, "directory", normalized_directory)
        if self.id != _content_id("translation-unit", self.identity_dict()):
            raise ProjectManifestError("unit.id does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        file: str,
        directory: str,
        content_sha256: str,
        arguments: Sequence[str],
    ) -> "ProjectTranslationUnit":
        normalized_file = _logical_path(file, "unit.file")
        normalized_directory = _logical_path(directory, "unit.directory")
        fields: dict[str, object] = {
            "arguments": list(arguments),
            "content_sha256": content_sha256,
            "directory": normalized_directory,
            "file": normalized_file,
            "language": "c++17",
        }
        return cls(
            normalized_file,
            normalized_directory,
            "c++17",
            content_sha256,
            tuple(arguments),
            _content_id("translation-unit", fields),
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "arguments": list(self.arguments),
            "content_sha256": self.content_sha256,
            "directory": self.directory,
            "file": self.file,
            "language": self.language,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.identity_dict(), "id": self.id}


@dataclass(frozen=True, slots=True)
class ProjectEntryDisposition:
    file: str | None
    reason: str
    count: int

    def __post_init__(self) -> None:
        if self.file is not None:
            object.__setattr__(
                self,
                "file",
                _logical_path(self.file, "disposition.file"),
            )
        reason = _require_text(self.reason, "disposition.reason")
        if reason not in SKIP_REASONS | REJECTION_REASONS:
            raise ProjectManifestError(
                f"disposition.reason has unsupported value {reason!r}"
            )
        object.__setattr__(self, "reason", reason)
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise ProjectManifestError("disposition.count must be an integer")
        if self.count < 1:
            raise ProjectManifestError("disposition.count must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "file": self.file,
            "reason": self.reason,
        }


def _disposition_key(
    item: ProjectEntryDisposition,
) -> tuple[str, str, int]:
    return (item.file or "", item.reason, item.count)


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    entry_count: int
    selected: tuple[ProjectTranslationUnit, ...]
    skipped: tuple[ProjectEntryDisposition, ...]
    rejected: tuple[ProjectEntryDisposition, ...]
    status: str
    id: str
    schema: str = PROJECT_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROJECT_MANIFEST_SCHEMA:
            raise ProjectManifestError("unsupported project manifest schema")
        if isinstance(self.entry_count, bool) or not isinstance(
            self.entry_count, int
        ):
            raise ProjectManifestError("entry_count must be an integer")
        if self.entry_count < 0:
            raise ProjectManifestError("entry_count must be non-negative")
        if self.selected != tuple(sorted(self.selected)):
            raise ProjectManifestError("selected units must be sorted")
        if self.skipped != tuple(sorted(self.skipped, key=_disposition_key)):
            raise ProjectManifestError("skipped entries must be sorted")
        if self.rejected != tuple(sorted(self.rejected, key=_disposition_key)):
            raise ProjectManifestError("rejected entries must be sorted")
        if any(item.reason not in SKIP_REASONS for item in self.skipped):
            raise ProjectManifestError("skipped entry has a rejection reason")
        if any(item.reason not in REJECTION_REASONS for item in self.rejected):
            raise ProjectManifestError("rejected entry has a skip reason")
        selected_files = [unit.file for unit in self.selected]
        if len(selected_files) != len(set(selected_files)):
            raise ProjectManifestError("selected unit files must be unique")
        accounted = len(self.selected)
        accounted += sum(item.count for item in self.skipped)
        accounted += sum(item.count for item in self.rejected)
        if accounted != self.entry_count:
            raise ProjectManifestError("manifest entry counts do not reconcile")
        expected_status = "invalid" if self.rejected else "valid"
        if self.status != expected_status:
            raise ProjectManifestError("manifest status does not match rejections")
        _require_hash(self.id, "manifest.id")
        if self.id != _content_id("project-manifest", self.identity_dict()):
            raise ProjectManifestError("manifest.id does not match canonical content")

    @property
    def valid(self) -> bool:
        return self.status == "valid"

    @classmethod
    def create(
        cls,
        *,
        entry_count: int,
        selected: Sequence[ProjectTranslationUnit],
        skipped: Sequence[ProjectEntryDisposition],
        rejected: Sequence[ProjectEntryDisposition],
    ) -> "ProjectManifest":
        selected_items = tuple(sorted(selected))
        skipped_items = tuple(sorted(skipped, key=_disposition_key))
        rejected_items = tuple(sorted(rejected, key=_disposition_key))
        status = "invalid" if rejected_items else "valid"
        fields: dict[str, object] = {
            "entry_count": entry_count,
            "rejected": [item.to_dict() for item in rejected_items],
            "schema": PROJECT_MANIFEST_SCHEMA,
            "selected": [item.to_dict() for item in selected_items],
            "skipped": [item.to_dict() for item in skipped_items],
            "status": status,
        }
        return cls(
            entry_count,
            selected_items,
            skipped_items,
            rejected_items,
            status,
            _content_id("project-manifest", fields),
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "entry_count": self.entry_count,
            "rejected": [item.to_dict() for item in self.rejected],
            "schema": self.schema,
            "selected": [item.to_dict() for item in self.selected],
            "skipped": [item.to_dict() for item in self.skipped],
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.identity_dict(), "id": self.id}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _split_windows_command(command: str) -> tuple[str, ...]:
    arguments: list[str] = []
    current: list[str] = []
    argument_started = False
    in_quotes = False
    index = 0
    while index < len(command):
        if command[index].isspace() and not in_quotes:
            if argument_started:
                arguments.append("".join(current))
                current = []
                argument_started = False
            index += 1
            continue
        if command[index] == "\\":
            start = index
            while index < len(command) and command[index] == "\\":
                index += 1
            slash_count = index - start
            argument_started = True
            if index < len(command) and command[index] == '"':
                current.extend("\\" * (slash_count // 2))
                if slash_count % 2:
                    current.append('"')
                else:
                    in_quotes = not in_quotes
                index += 1
                continue
            current.extend("\\" * slash_count)
            continue
        if command[index] == '"':
            argument_started = True
            in_quotes = not in_quotes
            index += 1
            continue
        current.append(command[index])
        argument_started = True
        index += 1
    if in_quotes:
        raise ValueError("unterminated quote")
    if argument_started:
        arguments.append("".join(current))
    return tuple(arguments)


def _parse_command(command: str, style: str) -> tuple[str, ...]:
    if style == "posix":
        return tuple(shlex.split(command, posix=True))
    if style == "windows":
        return _split_windows_command(command)
    raise ProjectManifestError(f"unsupported command style {style!r}")


def _argument_path(argument: str, directory: Path) -> Path | None:
    if not argument or argument.startswith("-") or argument.startswith("@"):
        return None
    candidate = Path(argument)
    if not candidate.is_absolute():
        candidate = directory / candidate
    return candidate.resolve()


def _replace_root(argument: str, root: Path) -> str:
    normalized = argument.replace("\\", "/")
    root_text = root.as_posix().rstrip("/")
    flags = re.IGNORECASE if os.name == "nt" else 0
    pattern = re.escape(root_text) + r"(?=/|$)"
    return re.sub(pattern, "$ROOT", normalized, flags=flags)


def _canonical_arguments(
    arguments: Sequence[str],
    *,
    directory: Path,
    source: Path,
    root: Path,
) -> tuple[tuple[str, ...] | None, str | None]:
    if not arguments or any(
        not isinstance(argument, str) or not argument for argument in arguments
    ):
        return None, "invalid_arguments"
    if any(argument.startswith("@") for argument in arguments):
        return None, "response_file_unsupported"
    if any(argument in _SHELL_OPERATORS for argument in arguments):
        return None, "shell_operator_unsupported"

    source_matches = [
        index
        for index, argument in enumerate(arguments)
        if (
            (candidate := _argument_path(argument, directory)) is not None
            and _path_key(candidate) == _path_key(source)
        )
    ]
    if not source_matches:
        return None, "source_argument_missing"
    if len(source_matches) != 1:
        return None, "source_argument_ambiguous"
    source_like_paths = {
        _path_key(candidate)
        for argument in arguments
        if (candidate := _argument_path(argument, directory)) is not None
        and (
            candidate.suffix in CPP_SUFFIXES
            or candidate.suffix.lower() in SKIPPED_SUFFIXES
        )
    }
    if source_like_paths != {_path_key(source)}:
        return None, "source_argument_ambiguous"
    source_index = source_matches[0]

    canonical: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if index == 0:
            canonical.append(argument.replace("\\", "/").rsplit("/", 1)[-1])
            index += 1
            continue
        if argument in _DROP_FLAGS:
            index += 1
            continue
        if argument in _DROP_VALUE_FLAGS:
            if index + 1 >= len(arguments):
                return None, "invalid_arguments"
            index += 2
            continue
        if (
            argument.startswith("-MF")
            or argument.startswith("-MQ")
            or argument.startswith("-MT")
            or argument.startswith("/Fo")
            or argument.startswith("/Fd")
        ):
            index += 1
            continue
        if index == source_index:
            canonical.append("$SOURCE")
        else:
            canonical.append(_replace_root(argument, root))
        index += 1
    return tuple(canonical), None


def _disposition(
    counts: Counter[tuple[str | None, str]],
) -> tuple[ProjectEntryDisposition, ...]:
    items = (
        ProjectEntryDisposition(file, reason, count)
        for (file, reason), count in counts.items()
    )
    return tuple(sorted(items, key=_disposition_key))


def build_project_manifest(
    project_root: str | os.PathLike[str],
    compilation_database: str | os.PathLike[str] = "compile_commands.json",
    *,
    command_style: str | None = None,
) -> ProjectManifest:
    request = ProjectManifestRequest(
        Path(project_root),
        Path(compilation_database),
        command_style,
    )

    root = request.project_root.resolve()
    if not root.is_dir():
        raise ProjectManifestError("project root must be an existing directory")
    database_path = request.compilation_database
    if not database_path.is_absolute():
        database_path = root / database_path
    database_path = database_path.resolve()
    if not _inside(root, database_path):
        raise ProjectManifestError("compilation database is outside project root")
    try:
        payload = json.loads(database_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectManifestError(
            f"cannot read compilation database: {error}"
        ) from error
    if not isinstance(payload, list):
        raise ProjectManifestError("compilation database must be a JSON array")

    candidates: dict[str, list[ProjectTranslationUnit]] = defaultdict(list)
    source_occurrences: Counter[str] = Counter()
    occurrence_files: dict[str, str] = {}
    skipped: Counter[tuple[str | None, str]] = Counter()
    rejected: Counter[tuple[str | None, str]] = Counter()

    for raw in payload:
        logical_file: str | None = None
        if not isinstance(raw, dict):
            rejected[(None, "invalid_entry")] += 1
            continue
        if set(raw) - _ENTRY_FIELDS:
            rejected[(None, "unexpected_fields")] += 1
            continue
        if "directory" not in raw:
            rejected[(None, "invalid_directory")] += 1
            continue
        if "file" not in raw:
            rejected[(None, "invalid_file")] += 1
            continue
        if "output" in raw and not isinstance(raw["output"], str):
            rejected[(None, "invalid_output")] += 1
            continue
        try:
            directory_text = _require_text(raw["directory"], "entry.directory")
            file_text = _require_text(raw["file"], "entry.file")
        except ProjectManifestError:
            rejected[(None, "invalid_entry")] += 1
            continue
        directory = Path(directory_text)
        if not directory.is_absolute():
            directory = database_path.parent / directory
        directory = directory.resolve()
        if not _inside(root, directory):
            rejected[(None, "outside_project_root")] += 1
            continue
        if not directory.is_dir():
            rejected[(None, "directory_missing")] += 1
            continue
        source = Path(file_text)
        if not source.is_absolute():
            source = directory / source
        source = source.resolve()
        if not _inside(root, source):
            rejected[(None, "outside_project_root")] += 1
            continue
        logical_file = _normalized_path(source, root)
        occurrence_key = os.path.normcase(logical_file)
        source_occurrences[occurrence_key] += 1
        occurrence_files.setdefault(occurrence_key, logical_file)
        if not source.is_file():
            rejected[(logical_file, "source_missing")] += 1
            continue

        has_arguments = "arguments" in raw
        has_command = "command" in raw
        if has_arguments and has_command:
            rejected[(logical_file, "ambiguous_command_fields")] += 1
            continue
        if not has_arguments and not has_command:
            rejected[(logical_file, "missing_command")] += 1
            continue
        if has_arguments:
            raw_arguments = raw["arguments"]
            if (
                not isinstance(raw_arguments, list)
                or any(not isinstance(item, str) for item in raw_arguments)
            ):
                rejected[(logical_file, "invalid_arguments")] += 1
                continue
            arguments = tuple(raw_arguments)
        else:
            if request.command_style is None:
                rejected[(logical_file, "command_style_required")] += 1
                continue
            if not isinstance(raw["command"], str) or not raw["command"]:
                rejected[(logical_file, "malformed_command")] += 1
                continue
            try:
                arguments = _parse_command(
                    raw["command"],
                    request.command_style,
                )
            except ValueError:
                rejected[(logical_file, "malformed_command")] += 1
                continue

        suffix = source.suffix
        normalized_suffix = suffix if suffix == ".C" else suffix.lower()
        if (
            normalized_suffix not in CPP_SUFFIXES
            and normalized_suffix not in SKIPPED_SUFFIXES
        ):
            rejected[(logical_file, "unsupported_source_extension")] += 1
            continue

        canonical_arguments, argument_error = _canonical_arguments(
            arguments,
            directory=directory,
            source=source,
            root=root,
        )
        if argument_error is not None:
            rejected[(logical_file, argument_error)] += 1
            continue
        assert canonical_arguments is not None

        if normalized_suffix in SKIPPED_SUFFIXES:
            skipped[(logical_file, "non_cpp_language")] += 1
            continue

        try:
            source_bytes = source.read_bytes()
        except OSError:
            rejected[(logical_file, "source_unreadable")] += 1
            continue
        unit = ProjectTranslationUnit.create(
            file=logical_file,
            directory=_normalized_path(directory, root),
            content_sha256=_text_hash(source_bytes),
            arguments=canonical_arguments,
        )
        candidates[occurrence_key].append(unit)

    selected: list[ProjectTranslationUnit] = []
    for key, count in source_occurrences.items():
        units = candidates.get(key, [])
        if count == 1 and len(units) == 1:
            selected.append(units[0])
            continue
        if count == 1:
            continue
        file = occurrence_files[key]
        for dispositions in (skipped, rejected):
            for disposition in tuple(dispositions):
                disposition_file, _ = disposition
                if (
                    disposition_file is not None
                    and os.path.normcase(disposition_file) == key
                ):
                    del dispositions[disposition]
        rejected[(file, "duplicate_source_entry")] += count

    return ProjectManifest.create(
        entry_count=len(payload),
        selected=selected,
        skipped=_disposition(skipped),
        rejected=_disposition(rejected),
    )


def load_project_manifest_json(text: str) -> ProjectManifest:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectManifestError(
            f"invalid project manifest JSON: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ProjectManifestError("project manifest must be an object")
    _require_exact_keys(
        raw,
        {
            "entry_count",
            "id",
            "rejected",
            "schema",
            "selected",
            "skipped",
            "status",
        },
        "manifest",
    )

    selected_raw = raw["selected"]
    skipped_raw = raw["skipped"]
    rejected_raw = raw["rejected"]
    if not isinstance(selected_raw, list):
        raise ProjectManifestError("manifest.selected must be an array")
    if not isinstance(skipped_raw, list):
        raise ProjectManifestError("manifest.skipped must be an array")
    if not isinstance(rejected_raw, list):
        raise ProjectManifestError("manifest.rejected must be an array")

    selected: list[ProjectTranslationUnit] = []
    for index, item in enumerate(selected_raw):
        if not isinstance(item, dict):
            raise ProjectManifestError(f"selected[{index}] must be an object")
        _require_exact_keys(
            item,
            {
                "arguments",
                "content_sha256",
                "directory",
                "file",
                "id",
                "language",
            },
            f"selected[{index}]",
        )
        arguments = item["arguments"]
        if not isinstance(arguments, list):
            raise ProjectManifestError(
                f"selected[{index}].arguments must be an array"
            )
        selected.append(
            ProjectTranslationUnit(
                item["file"],
                item["directory"],
                item["language"],
                item["content_sha256"],
                tuple(arguments),
                item["id"],
            )
        )

    def dispositions(
        values: list[object],
        field: str,
    ) -> list[ProjectEntryDisposition]:
        parsed: list[ProjectEntryDisposition] = []
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                raise ProjectManifestError(f"{field}[{index}] must be an object")
            _require_exact_keys(
                item,
                {"count", "file", "reason"},
                f"{field}[{index}]",
            )
            parsed.append(
                ProjectEntryDisposition(
                    item["file"],
                    item["reason"],
                    item["count"],
                )
            )
        return parsed

    manifest = ProjectManifest(
        raw["entry_count"],
        tuple(selected),
        tuple(dispositions(skipped_raw, "skipped")),
        tuple(dispositions(rejected_raw, "rejected")),
        raw["status"],
        raw["id"],
        raw["schema"],
    )
    if manifest.to_json() != text:
        raise ProjectManifestError("project manifest JSON is not canonical")
    return manifest
