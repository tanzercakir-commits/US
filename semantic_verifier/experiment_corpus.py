"""Strict seeded-bug corpus for the bounded E2 experiment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .checker import AffineChecker
from .model import VerificationStatus
from .pipeline import VerificationPipeline
from .repair_bundle import RepairBundleBuilder, RepairBundleError


EXPERIMENT_CORPUS_SCHEMA = "codeskeptic.experiment-corpus/v1"
EXPERIMENT_CONTEXT_SCHEMA = "codeskeptic.experiment-compiler-context/v1"
EXPERIMENT_ORACLE_SCHEMA = "codeskeptic.experiment-repair-oracle/v1"
EXPERIMENT_CORPUS_ID_SCHEMA = "codeskeptic.experiment-corpus-identity/v1"
EXPERIMENT_CORPUS_CHECK_SCHEMA = "codeskeptic.experiment-corpus-check/v1"
CASE_COUNT = 20
_BASE_DISPLAY = "benchmarks/experiment_e2/corpus/"
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASE_RE = re.compile(r"e2-case-(0[1-9]|1[0-9]|20)\Z")


class ExperimentCorpusError(ValueError):
    """Raised when corpus structure or semantic evidence fails closed."""


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


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_id(value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": "experiment-corpus",
        "schema": EXPERIMENT_CORPUS_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ExperimentCorpusError(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ExperimentCorpusError(f"{field_name} must be non-empty text")
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
        raise ExperimentCorpusError(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise ExperimentCorpusError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentCorpusError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ExperimentCorpusError(
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
        raise ExperimentCorpusError(
            f"invalid {field_name} JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise ExperimentCorpusError(f"{field_name} must be a JSON object")
    return value


def _read_utf8(path: Path, field_name: str) -> str:
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise ExperimentCorpusError(
            f"cannot read {field_name}: {error}"
        ) from error
    if text.startswith("\ufeff") or "\x00" in text or "\r" in text:
        raise ExperimentCorpusError(
            f"{field_name} must be BOM-free LF-only UTF-8 text"
        )
    return text


def _relative_path(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ExperimentCorpusError(
            f"{field_name} must be a safe canonical relative path"
        )
    return text


def redact_contracts(source: str) -> str:
    """Blank contract lines without changing source line numbers."""

    redacted: list[str] = []
    for line in source.splitlines(keepends=True):
        if re.match(r"^\s*//\s*cs:", line):
            redacted.append("\n" if line.endswith("\n") else "")
        else:
            redacted.append(line)
    return "".join(redacted)


@dataclass(frozen=True, slots=True)
class ExperimentCase:
    id: str
    function: str
    display_path: str
    source: str
    source_sha256: str
    compiler_context: str
    compiler_context_sha256: str
    oracle: str
    oracle_sha256: str
    source_text: str = field(repr=False, compare=False)
    redacted_source: str = field(repr=False, compare=False)
    diagnostic: str = field(repr=False, compare=False)
    oracle_line: int = field(repr=False, compare=False)
    oracle_replacement: str = field(repr=False, compare=False)
    repaired_source_sha256: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _CASE_RE.fullmatch(self.id) is None:
            raise ExperimentCorpusError("case.id is unsupported")
        suffix = self.id[-2:]
        if self.function != f"e2_case_{suffix}":
            raise ExperimentCorpusError("case.function does not match case ID")
        expected_source = f"cases/{self.id}.cpp"
        expected_context = f"contexts/{self.id}.context.json"
        expected_oracle = f"oracles/{self.id}.oracle.json"
        if self.source != expected_source:
            raise ExperimentCorpusError("case.source does not match case ID")
        if self.compiler_context != expected_context:
            raise ExperimentCorpusError(
                "case.compiler_context does not match case ID"
            )
        if self.oracle != expected_oracle:
            raise ExperimentCorpusError("case.oracle does not match case ID")
        if self.display_path != _BASE_DISPLAY + expected_source:
            raise ExperimentCorpusError("case.display_path is not canonical")
        for value, name in (
            (self.source_sha256, "case.source_sha256"),
            (self.compiler_context_sha256, "case.compiler_context_sha256"),
            (self.oracle_sha256, "case.oracle_sha256"),
            (self.repaired_source_sha256, "oracle.repaired_source_sha256"),
        ):
            _require_hash(value, name)
        _require_text(self.diagnostic, "context.diagnostic")
        if not self.source_text.endswith("\n") or "\r" in self.source_text:
            raise ExperimentCorpusError("case source must be LF-only and final-newline")
        if self.redacted_source != redact_contracts(self.source_text):
            raise ExperimentCorpusError("context source is not exact contract redaction")
        if "// cs:" in self.redacted_source:
            raise ExperimentCorpusError("compiler context leaks contract text")
        if (
            isinstance(self.oracle_line, bool)
            or not isinstance(self.oracle_line, int)
            or self.oracle_line < 1
        ):
            raise ExperimentCorpusError("oracle.line must be a positive integer")
        if (
            not isinstance(self.oracle_replacement, str)
            or not self.oracle_replacement
            or "\n" in self.oracle_replacement
            or "\r" in self.oracle_replacement
            or "\x00" in self.oracle_replacement
        ):
            raise ExperimentCorpusError(
                "oracle.replacement must be one non-empty source line"
            )

    def metadata_dict(self) -> dict[str, str]:
        return {
            "compiler_context": self.compiler_context,
            "compiler_context_sha256": self.compiler_context_sha256,
            "display_path": self.display_path,
            "function": self.function,
            "id": self.id,
            "oracle": self.oracle,
            "oracle_sha256": self.oracle_sha256,
            "source": self.source,
            "source_sha256": self.source_sha256,
        }

    def compiler_context_dict(self) -> dict[str, object]:
        return {
            "case": self.id,
            "diagnostic": self.diagnostic,
            "redacted_source": self.redacted_source,
            "schema": EXPERIMENT_CONTEXT_SCHEMA,
            "target_source": self.source_sha256,
        }

    def oracle_dict(self) -> dict[str, object]:
        return {
            "case": self.id,
            "line": self.oracle_line,
            "repaired_source": self.repaired_source_sha256,
            "replacement": self.oracle_replacement,
            "schema": EXPERIMENT_ORACLE_SCHEMA,
            "target_source": self.source_sha256,
        }

    def repaired_source(self) -> str:
        lines = self.source_text.splitlines()
        if self.oracle_line > len(lines):
            raise ExperimentCorpusError("oracle line is outside source")
        index = self.oracle_line - 1
        if re.match(r"^\s*//\s*cs:", lines[index]):
            raise ExperimentCorpusError("oracle may not edit a contract line")
        lines[index] = self.oracle_replacement
        repaired = "\n".join(lines) + "\n"
        if _sha256_text(repaired) != self.repaired_source_sha256:
            raise ExperimentCorpusError("oracle repaired-source hash is stale")
        return repaired


@dataclass(frozen=True, slots=True)
class ExperimentCorpus:
    id: str
    cases: tuple[ExperimentCase, ...]
    root: Path = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.cases) != CASE_COUNT:
            raise ExperimentCorpusError(
                f"corpus must contain exactly {CASE_COUNT} cases"
            )
        ids = [case.id for case in self.cases]
        functions = [case.function for case in self.cases]
        displays = [case.display_path for case in self.cases]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ExperimentCorpusError("corpus case IDs must be unique and sorted")
        if len(functions) != len(set(functions)):
            raise ExperimentCorpusError("corpus functions must be unique")
        if len(displays) != len(set(displays)):
            raise ExperimentCorpusError("corpus display paths must be unique")
        expected = _content_id(self.content_dict())
        if _require_hash(self.id, "corpus.id") != expected:
            raise ExperimentCorpusError(
                "corpus.id does not match canonical content"
            )

    def content_dict(self) -> dict[str, object]:
        return {
            "cases": [case.metadata_dict() for case in self.cases],
            "schema": EXPERIMENT_CORPUS_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExperimentCorpusCheck:
    corpus: str
    case_count: int
    original_violated: int
    original_replayed: int
    repaired_verified: int

    def to_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "corpus": self.corpus,
            "original_replayed": self.original_replayed,
            "original_violated": self.original_violated,
            "repaired_verified": self.repaired_verified,
            "schema": EXPERIMENT_CORPUS_CHECK_SCHEMA,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _load_case(root: Path, payload: Mapping[str, Any]) -> ExperimentCase:
    _exact_keys(
        payload,
        {
            "compiler_context",
            "compiler_context_sha256",
            "display_path",
            "function",
            "id",
            "oracle",
            "oracle_sha256",
            "source",
            "source_sha256",
        },
        "case",
    )
    case_id = _require_text(payload["id"], "case.id")
    source_rel = _relative_path(payload["source"], "case.source")
    context_rel = _relative_path(
        payload["compiler_context"], "case.compiler_context"
    )
    oracle_rel = _relative_path(payload["oracle"], "case.oracle")
    source_text = _read_utf8(root / source_rel, f"source {case_id}")
    context_text = _read_utf8(root / context_rel, f"context {case_id}")
    oracle_text = _read_utf8(root / oracle_rel, f"oracle {case_id}")
    if _sha256_text(source_text) != payload["source_sha256"]:
        raise ExperimentCorpusError(f"source hash is stale for {case_id}")
    if _sha256_text(context_text) != payload["compiler_context_sha256"]:
        raise ExperimentCorpusError(f"context hash is stale for {case_id}")
    if _sha256_text(oracle_text) != payload["oracle_sha256"]:
        raise ExperimentCorpusError(f"oracle hash is stale for {case_id}")

    context = _parse_json(context_text, f"context {case_id}")
    _exact_keys(
        context,
        {"case", "diagnostic", "redacted_source", "schema", "target_source"},
        f"context {case_id}",
    )
    if context["schema"] != EXPERIMENT_CONTEXT_SCHEMA:
        raise ExperimentCorpusError(f"unsupported context schema for {case_id}")
    if _canonical_json(context) != context_text:
        raise ExperimentCorpusError(f"context is not canonical for {case_id}")
    if context["case"] != case_id:
        raise ExperimentCorpusError(f"context case link is stale for {case_id}")
    if context["target_source"] != payload["source_sha256"]:
        raise ExperimentCorpusError(f"context source link is stale for {case_id}")

    oracle = _parse_json(oracle_text, f"oracle {case_id}")
    _exact_keys(
        oracle,
        {
            "case",
            "line",
            "repaired_source",
            "replacement",
            "schema",
            "target_source",
        },
        f"oracle {case_id}",
    )
    if oracle["schema"] != EXPERIMENT_ORACLE_SCHEMA:
        raise ExperimentCorpusError(f"unsupported oracle schema for {case_id}")
    if _canonical_json(oracle) != oracle_text:
        raise ExperimentCorpusError(f"oracle is not canonical for {case_id}")
    if oracle["case"] != case_id:
        raise ExperimentCorpusError(f"oracle case link is stale for {case_id}")
    if oracle["target_source"] != payload["source_sha256"]:
        raise ExperimentCorpusError(f"oracle source link is stale for {case_id}")

    return ExperimentCase(
        id=case_id,
        function=_require_text(payload["function"], "case.function"),
        display_path=_require_text(payload["display_path"], "case.display_path"),
        source=source_rel,
        source_sha256=_require_hash(payload["source_sha256"], "case.source_sha256"),
        compiler_context=context_rel,
        compiler_context_sha256=_require_hash(
            payload["compiler_context_sha256"],
            "case.compiler_context_sha256",
        ),
        oracle=oracle_rel,
        oracle_sha256=_require_hash(payload["oracle_sha256"], "case.oracle_sha256"),
        source_text=source_text,
        redacted_source=_require_text(
            context["redacted_source"], "context.redacted_source"
        ),
        diagnostic=_require_text(context["diagnostic"], "context.diagnostic"),
        oracle_line=oracle["line"],
        oracle_replacement=oracle["replacement"],
        repaired_source_sha256=_require_hash(
            oracle["repaired_source"], "oracle.repaired_source"
        ),
    )


def load_experiment_corpus(root: str | Path) -> ExperimentCorpus:
    corpus_root = Path(root).resolve()
    manifest_path = corpus_root / "manifest.json"
    manifest_text = _read_utf8(manifest_path, "experiment corpus manifest")
    payload = _parse_json(manifest_text, "experiment corpus manifest")
    _exact_keys(payload, {"cases", "id", "schema"}, "corpus")
    if payload["schema"] != EXPERIMENT_CORPUS_SCHEMA:
        raise ExperimentCorpusError("unsupported experiment corpus schema")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise ExperimentCorpusError("corpus.cases must be an array")
    cases: list[ExperimentCase] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, Mapping):
            raise ExperimentCorpusError(
                f"corpus.cases[{index}] must be an object"
            )
        cases.append(_load_case(corpus_root, item))
    corpus = ExperimentCorpus(
        id=payload["id"],
        cases=tuple(cases),
        root=corpus_root,
    )

    expected_files = {".gitattributes", "manifest.json"}
    for case in corpus.cases:
        expected_files.update(
            {case.source, case.compiler_context, case.oracle}
        )
    actual_files = {
        path.relative_to(corpus_root).as_posix()
        for path in corpus_root.rglob("*")
        if path.is_file()
    }
    missing = sorted(expected_files - actual_files)
    extra = sorted(actual_files - expected_files)
    if missing:
        raise ExperimentCorpusError(
            f"corpus is missing files: {', '.join(missing)}"
        )
    if extra:
        raise ExperimentCorpusError(
            f"corpus has undeclared files: {', '.join(extra)}"
        )
    for case in corpus.cases:
        case.repaired_source()
    return corpus


def check_experiment_corpus(
    corpus: ExperimentCorpus,
) -> ExperimentCorpusCheck:
    original_violated = 0
    original_replayed = 0
    repaired_verified = 0
    for case in corpus.cases:
        checker = AffineChecker()
        pipeline = VerificationPipeline(checker=checker)
        report = pipeline.verify_source(case.source_text, case.display_path)
        if report.module.unsupported:
            raise ExperimentCorpusError(
                f"original case {case.id} has unsupported lowering"
            )
        functions = [
            function for function in report.module.functions
            if function.name == case.function and function.has_body
        ]
        if len(functions) != 1 or len(report.module.functions) != 1:
            raise ExperimentCorpusError(
                f"original case {case.id} does not define exactly its target"
            )
        violated = [
            result
            for result in report.results
            if result.status == VerificationStatus.VIOLATED
            and result.counterexample
            and result.function == case.function
            and result.kind == "postcondition"
        ]
        non_verified = [
            result
            for result in report.results
            if result.status != VerificationStatus.VERIFIED
        ]
        if len(violated) != 1 or non_verified != violated:
            raise ExperimentCorpusError(
                f"original case {case.id} is not one isolated violation"
            )
        original_violated += 1
        try:
            bundle = RepairBundleBuilder(checker=checker).build(
                case.source_text,
                case.display_path,
                report,
                violated[0].obligation_id,
            )
        except RepairBundleError as error:
            raise ExperimentCorpusError(
                f"original case {case.id} did not replay: {error}"
            ) from error
        if bundle.result["status"] != "violated":
            raise ExperimentCorpusError(
                f"original case {case.id} bundle is not violated"
            )
        original_replayed += 1

        repaired = case.repaired_source()
        original_contracts = [
            line for line in case.source_text.splitlines()
            if re.match(r"^\s*//\s*cs:", line)
        ]
        repaired_contracts = [
            line for line in repaired.splitlines()
            if re.match(r"^\s*//\s*cs:", line)
        ]
        if original_contracts != repaired_contracts:
            raise ExperimentCorpusError(
                f"repair oracle changes contracts for {case.id}"
            )
        repaired_report = pipeline.verify_source(repaired, case.display_path)
        target_results = [
            result for result in repaired_report.results
            if result.function == case.function
        ]
        if (
            repaired_report.module.unsupported
            or not target_results
            or any(
                result.status != VerificationStatus.VERIFIED
                for result in repaired_report.results
            )
        ):
            raise ExperimentCorpusError(
                f"repair oracle is not fully verified for {case.id}"
            )
        repaired_verified += 1

    return ExperimentCorpusCheck(
        corpus=corpus.id,
        case_count=len(corpus.cases),
        original_violated=original_violated,
        original_replayed=original_replayed,
        repaired_verified=repaired_verified,
    )
