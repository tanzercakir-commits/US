"""Deterministic paired-arm execution for the bounded E2 experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .checker import AffineChecker
from .experiment_corpus import ExperimentCase, ExperimentCorpus
from .model import VerificationStatus
from .pipeline import VerificationPipeline
from .repair_bundle import RepairBundle, RepairBundleBuilder, RepairBundleError
from .repair_loop import (
    PATCH_SCRIPT_SCHEMA,
    PatchProposal,
    RepairHarness,
    RepairLoopError,
    RepairLoopLog,
    ScriptedPatchProposer,
    apply_line_edit,
    load_patch_script_json,
    load_repair_loop_json,
)


EXPERIMENT_CONTEXT_SCHEMA = "codeskeptic.experiment-context/v1"
EXPERIMENT_SCRIPT_SCHEMA = "codeskeptic.experiment-proposal-script/v1"
EXPERIMENT_TRIAL_SCHEMA = "codeskeptic.experiment-trial/v1"
EXPERIMENT_TRIALS_SCHEMA = "codeskeptic.experiment-trials/v1"
EXPERIMENT_ID_SCHEMA = "codeskeptic.experiment-identity/v1"
ARM_COMPILER = "compiler_test"
ARM_SEMANTIC = "semantic_bundle"
ARMS = (ARM_COMPILER, ARM_SEMANTIC)
MAX_PROPOSALS = 4
REFEREE = "codeskeptic.affine/v1"
PROPOSER = "codeskeptic.recorded-scripted-proxy/v1"
EVIDENCE_SCOPE = "recorded-scripted-proxy"
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ExperimentE2Error(ValueError):
    """Raised when paired experiment evidence fails closed."""


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


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    envelope = {
        "kind": kind,
        "schema": EXPERIMENT_ID_SCHEMA,
        "value": value,
    }
    return "sha256:" + hashlib.sha256(_identity_bytes(envelope)).hexdigest()


def _require_hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ExperimentE2Error(
            f"{field_name} must be a lowercase sha256 identity"
        )
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ExperimentE2Error(f"{field_name} must be non-empty text")
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
        raise ExperimentE2Error(
            f"{field_name} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise ExperimentE2Error(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentE2Error(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ExperimentE2Error(
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
        raise ExperimentE2Error(
            f"invalid {field_name} JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise ExperimentE2Error(f"{field_name} must be a JSON object")
    return value


def _read_json_text(path: Path, field_name: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ExperimentE2Error(
            f"cannot read {field_name}: {error}"
        ) from error
    if text.startswith("\ufeff") or "\x00" in text:
        raise ExperimentE2Error(
            f"{field_name} must be BOM-free UTF-8 text"
        )
    return text.replace("\r\n", "\n")


@dataclass(frozen=True, slots=True)
class ExperimentContext:
    id: str
    arm: str
    case: str
    corpus: str
    evidence_scope: str
    target_source: str
    redacted_source: str | None
    diagnostic: str | None
    bundle: RepairBundle | None

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ExperimentE2Error("context.arm is unsupported")
        _require_text(self.case, "context.case")
        _require_hash(self.corpus, "context.corpus")
        _require_hash(self.target_source, "context.target_source")
        if self.arm == ARM_COMPILER:
            if (
                self.evidence_scope != "compiler-test-only"
                or self.redacted_source is None
                or self.diagnostic is None
                or self.bundle is not None
            ):
                raise ExperimentE2Error(
                    "compiler context has forbidden or missing evidence"
                )
            _require_text(self.redacted_source, "context.redacted_source")
            _require_text(self.diagnostic, "context.diagnostic")
            exposed = (self.redacted_source + "\n" + self.diagnostic).lower()
            forbidden = (
                "// cs:",
                "requires",
                "ensures",
                "obligation",
                "semantic_ir",
                "counterexample",
                "repair-bundle",
                "oracle",
            )
            leaked = [token for token in forbidden if token in exposed]
            if leaked:
                raise ExperimentE2Error(
                    "compiler context leaks forbidden semantic evidence: "
                    + ", ".join(leaked)
                )
        else:
            if (
                self.evidence_scope != "semantic-repair-bundle"
                or self.redacted_source is not None
                or self.diagnostic is not None
                or not isinstance(self.bundle, RepairBundle)
            ):
                raise ExperimentE2Error(
                    "semantic context must contain exactly one repair bundle"
                )
            if self.bundle.source_sha256 != self.target_source:
                raise ExperimentE2Error(
                    "semantic context bundle/source link is stale"
                )
        expected = _content_id("experiment-context", self.content_dict())
        if _require_hash(self.id, "context.id") != expected:
            raise ExperimentE2Error(
                "context.id does not match canonical content"
            )

    @classmethod
    def compiler(
        cls,
        corpus: ExperimentCorpus,
        case: ExperimentCase,
    ) -> "ExperimentContext":
        content = {
            "arm": ARM_COMPILER,
            "case": case.id,
            "corpus": corpus.id,
            "evidence": {
                "diagnostic": case.diagnostic,
                "redacted_source": case.redacted_source,
            },
            "evidence_scope": "compiler-test-only",
            "schema": EXPERIMENT_CONTEXT_SCHEMA,
            "target_source": case.source_sha256,
        }
        return cls(
            _content_id("experiment-context", content),
            ARM_COMPILER,
            case.id,
            corpus.id,
            "compiler-test-only",
            case.source_sha256,
            case.redacted_source,
            case.diagnostic,
            None,
        )

    @classmethod
    def semantic(
        cls,
        corpus: ExperimentCorpus,
        case: ExperimentCase,
        bundle: RepairBundle,
    ) -> "ExperimentContext":
        content = {
            "arm": ARM_SEMANTIC,
            "case": case.id,
            "corpus": corpus.id,
            "evidence": {"bundle": bundle.to_dict()},
            "evidence_scope": "semantic-repair-bundle",
            "schema": EXPERIMENT_CONTEXT_SCHEMA,
            "target_source": case.source_sha256,
        }
        return cls(
            _content_id("experiment-context", content),
            ARM_SEMANTIC,
            case.id,
            corpus.id,
            "semantic-repair-bundle",
            case.source_sha256,
            None,
            None,
            bundle,
        )

    def content_dict(self) -> dict[str, object]:
        if self.arm == ARM_COMPILER:
            evidence: dict[str, object] = {
                "diagnostic": self.diagnostic,
                "redacted_source": self.redacted_source,
            }
        else:
            assert self.bundle is not None
            evidence = {"bundle": self.bundle.to_dict()}
        return {
            "arm": self.arm,
            "case": self.case,
            "corpus": self.corpus,
            "evidence": evidence,
            "evidence_scope": self.evidence_scope,
            "schema": EXPERIMENT_CONTEXT_SCHEMA,
            "target_source": self.target_source,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

@dataclass(frozen=True, slots=True)
class ExperimentProposalScript:
    id: str
    arm: str
    case: str
    context: str
    proposer: str
    evidence_scope: str
    proposals: tuple[PatchProposal, ...]

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ExperimentE2Error("script.arm is unsupported")
        _require_text(self.case, "script.case")
        _require_hash(self.context, "script.context")
        if self.proposer != PROPOSER:
            raise ExperimentE2Error("script.proposer is unsupported")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise ExperimentE2Error("script.evidence_scope is unsupported")
        normalized = tuple(self.proposals)
        if not 1 <= len(normalized) <= MAX_PROPOSALS:
            raise ExperimentE2Error(
                "script must contain from one through four proposals"
            )
        if any(not isinstance(item, PatchProposal) for item in normalized):
            raise ExperimentE2Error("script contains a non-proposal")
        ids = [item.id for item in normalized]
        if len(ids) != len(set(ids)):
            raise ExperimentE2Error("script reuses a proposal identity")
        object.__setattr__(self, "proposals", normalized)
        expected = _content_id(
            "experiment-proposal-script", self.content_dict()
        )
        if _require_hash(self.id, "script.id") != expected:
            raise ExperimentE2Error(
                "script.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        arm: str,
        case: str,
        context: str,
        proposals: Sequence[PatchProposal],
    ) -> "ExperimentProposalScript":
        proposal_tuple = tuple(proposals)
        content = {
            "arm": arm,
            "case": case,
            "context": context,
            "evidence_scope": EVIDENCE_SCOPE,
            "proposals": [item.to_dict() for item in proposal_tuple],
            "proposer": PROPOSER,
            "schema": EXPERIMENT_SCRIPT_SCHEMA,
        }
        return cls(
            _content_id("experiment-proposal-script", content),
            arm,
            case,
            context,
            PROPOSER,
            EVIDENCE_SCOPE,
            proposal_tuple,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "case": self.case,
            "context": self.context,
            "evidence_scope": self.evidence_scope,
            "proposals": [item.to_dict() for item in self.proposals],
            "proposer": self.proposer,
            "schema": EXPERIMENT_SCRIPT_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExperimentTrial:
    id: str
    arm: str
    case: str
    context: str
    script: str
    bundle: str
    attempts: int
    status: str
    score: int
    loop: RepairLoopLog

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ExperimentE2Error("trial.arm is unsupported")
        _require_text(self.case, "trial.case")
        for value, name in (
            (self.context, "trial.context"),
            (self.script, "trial.script"),
            (self.bundle, "trial.bundle"),
        ):
            _require_hash(value, name)
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or not 1 <= self.attempts <= MAX_PROPOSALS
        ):
            raise ExperimentE2Error("trial.attempts is invalid")
        if self.status not in {"exhausted", "verified"}:
            raise ExperimentE2Error("trial.status is unsupported")
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, int)
            or not 1 <= self.score <= MAX_PROPOSALS + 1
        ):
            raise ExperimentE2Error("trial.score is invalid")
        expected_score = (
            self.attempts
            if self.status == "verified"
            else MAX_PROPOSALS + 1
        )
        if self.score != expected_score:
            raise ExperimentE2Error(
                "trial score does not follow censoring rule"
            )
        if not isinstance(self.loop, RepairLoopLog):
            raise ExperimentE2Error("trial.loop must be a repair loop")
        if (
            self.loop.status != self.status
            or len(self.loop.attempts) != self.attempts
            or self.loop.max_iterations != MAX_PROPOSALS
            or self.loop.initial_bundle != self.bundle
        ):
            raise ExperimentE2Error("trial and repair loop disagree")
        expected = _content_id("experiment-trial", self.content_dict())
        if _require_hash(self.id, "trial.id") != expected:
            raise ExperimentE2Error(
                "trial.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        arm: str,
        case: str,
        context: str,
        script: str,
        bundle: str,
        loop: RepairLoopLog,
    ) -> "ExperimentTrial":
        attempts = len(loop.attempts)
        score = (
            attempts
            if loop.status == "verified"
            else MAX_PROPOSALS + 1
        )
        content = {
            "arm": arm,
            "attempts": attempts,
            "bundle": bundle,
            "case": case,
            "context": context,
            "loop": loop.to_dict(),
            "schema": EXPERIMENT_TRIAL_SCHEMA,
            "score": score,
            "script": script,
            "status": loop.status,
        }
        return cls(
            _content_id("experiment-trial", content),
            arm,
            case,
            context,
            script,
            bundle,
            attempts,
            loop.status,
            score,
            loop,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "attempts": self.attempts,
            "bundle": self.bundle,
            "case": self.case,
            "context": self.context,
            "loop": self.loop.to_dict(),
            "schema": EXPERIMENT_TRIAL_SCHEMA,
            "score": self.score,
            "script": self.script,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}


@dataclass(frozen=True, slots=True)
class ExperimentTrials:
    id: str
    corpus: str
    max_proposals: int
    referee: str
    proposer: str
    evidence_scope: str
    trials: tuple[ExperimentTrial, ...]

    def __post_init__(self) -> None:
        _require_hash(self.corpus, "trials.corpus")
        if self.max_proposals != MAX_PROPOSALS:
            raise ExperimentE2Error(
                "trials.max_proposals must be four"
            )
        if self.referee != REFEREE:
            raise ExperimentE2Error("trials.referee is unsupported")
        if self.proposer != PROPOSER:
            raise ExperimentE2Error("trials.proposer is unsupported")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise ExperimentE2Error(
                "trials.evidence_scope is unsupported"
            )
        normalized = tuple(self.trials)
        keys = [
            (trial.case, ARMS.index(trial.arm))
            for trial in normalized
        ]
        if keys != sorted(keys):
            raise ExperimentE2Error(
                "trials must be sorted by case and arm"
            )
        if len(normalized) != 40 or len(set(keys)) != 40:
            raise ExperimentE2Error(
                "trials must contain forty unique rows"
            )
        cases: dict[str, set[str]] = {}
        for trial in normalized:
            cases.setdefault(trial.case, set()).add(trial.arm)
        if len(cases) != 20 or any(
            arms != set(ARMS) for arms in cases.values()
        ):
            raise ExperimentE2Error(
                "trials must contain twenty complete pairs"
            )
        ids = [trial.id for trial in normalized]
        if len(ids) != len(set(ids)):
            raise ExperimentE2Error(
                "trial identities must be unique"
            )
        object.__setattr__(self, "trials", normalized)
        expected = _content_id("experiment-trials", self.content_dict())
        if _require_hash(self.id, "trials.id") != expected:
            raise ExperimentE2Error(
                "trials.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        corpus: ExperimentCorpus,
        trials: Sequence[ExperimentTrial],
    ) -> "ExperimentTrials":
        ordered = tuple(
            sorted(
                trials,
                key=lambda trial: (
                    trial.case,
                    ARMS.index(trial.arm),
                ),
            )
        )
        content = {
            "corpus": corpus.id,
            "evidence_scope": EVIDENCE_SCOPE,
            "max_proposals": MAX_PROPOSALS,
            "proposer": PROPOSER,
            "referee": REFEREE,
            "schema": EXPERIMENT_TRIALS_SCHEMA,
            "trials": [trial.to_dict() for trial in ordered],
        }
        return cls(
            _content_id("experiment-trials", content),
            corpus.id,
            MAX_PROPOSALS,
            REFEREE,
            PROPOSER,
            EVIDENCE_SCOPE,
            ordered,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "corpus": self.corpus,
            "evidence_scope": self.evidence_scope,
            "max_proposals": self.max_proposals,
            "proposer": self.proposer,
            "referee": self.referee,
            "schema": EXPERIMENT_TRIALS_SCHEMA,
            "trials": [trial.to_dict() for trial in self.trials],
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExperimentInputs:
    corpus: ExperimentCorpus
    contexts: tuple[ExperimentContext, ...]
    scripts: tuple[ExperimentProposalScript, ...]
    bundles: tuple[tuple[str, RepairBundle], ...] = field(repr=False)

    def context_for(self, case: str, arm: str) -> ExperimentContext:
        matches = [
            item
            for item in self.contexts
            if item.case == case and item.arm == arm
        ]
        if len(matches) != 1:
            raise ExperimentE2Error(
                "experiment context lookup is ambiguous"
            )
        return matches[0]

    def script_for(
        self, case: str, arm: str
    ) -> ExperimentProposalScript:
        matches = [
            item
            for item in self.scripts
            if item.case == case and item.arm == arm
        ]
        if len(matches) != 1:
            raise ExperimentE2Error(
                "experiment script lookup is ambiguous"
            )
        return matches[0]

    def bundle_for(self, case: str) -> RepairBundle:
        matches = [
            value for key, value in self.bundles if key == case
        ]
        if len(matches) != 1:
            raise ExperimentE2Error(
                "experiment bundle lookup is ambiguous"
            )
        return matches[0]

def _build_bundle(case: ExperimentCase) -> RepairBundle:
    checker = AffineChecker()
    report = VerificationPipeline(checker=checker).verify_source(
        case.source_text,
        case.display_path,
    )
    violated = [
        result
        for result in report.results
        if result.function == case.function
        and result.kind == "postcondition"
        and result.status == VerificationStatus.VIOLATED
        and result.counterexample
    ]
    if len(violated) != 1:
        raise ExperimentE2Error(
            f"case {case.id} does not have one replayable target"
        )
    try:
        return RepairBundleBuilder(checker=checker).build(
            case.source_text,
            case.display_path,
            report,
            violated[0].obligation_id,
        )
    except RepairBundleError as error:
        raise ExperimentE2Error(
            f"case {case.id} bundle failed: {error}"
        ) from error


def expected_contexts(
    corpus: ExperimentCorpus,
) -> tuple[
    tuple[ExperimentContext, ...],
    tuple[tuple[str, RepairBundle], ...],
]:
    contexts: list[ExperimentContext] = []
    bundles: list[tuple[str, RepairBundle]] = []
    for case in corpus.cases:
        bundle = _build_bundle(case)
        bundles.append((case.id, bundle))
        contexts.extend(
            (
                ExperimentContext.compiler(corpus, case),
                ExperimentContext.semantic(corpus, case, bundle),
            )
        )
    return tuple(contexts), tuple(bundles)


def load_experiment_context_json(
    text: str,
    expected: ExperimentContext,
) -> ExperimentContext:
    payload = _parse_json(text, "experiment context")
    _exact_keys(
        payload,
        {
            "arm",
            "case",
            "corpus",
            "evidence",
            "evidence_scope",
            "id",
            "schema",
            "target_source",
        },
        "context",
    )
    if payload["schema"] != EXPERIMENT_CONTEXT_SCHEMA:
        raise ExperimentE2Error(
            "unsupported experiment context schema"
        )
    if payload != expected.to_dict():
        raise ExperimentE2Error(
            "experiment context differs from isolated evidence"
        )
    if text != expected.to_json():
        raise ExperimentE2Error(
            "experiment context bytes are not canonical"
        )
    return expected


def load_experiment_script_json(
    text: str,
) -> ExperimentProposalScript:
    payload = _parse_json(text, "experiment proposal script")
    _exact_keys(
        payload,
        {
            "arm",
            "case",
            "context",
            "evidence_scope",
            "id",
            "proposals",
            "proposer",
            "schema",
        },
        "script",
    )
    if payload["schema"] != EXPERIMENT_SCRIPT_SCHEMA:
        raise ExperimentE2Error(
            "unsupported experiment script schema"
        )
    try:
        proposals = load_patch_script_json(
            _canonical_json(
                {
                    "proposals": payload["proposals"],
                    "schema": PATCH_SCRIPT_SCHEMA,
                }
            )
        )
    except RepairLoopError as error:
        raise ExperimentE2Error(
            f"invalid experiment proposal: {error}"
        ) from error
    script = ExperimentProposalScript(
        payload["id"],
        payload["arm"],
        payload["case"],
        payload["context"],
        payload["proposer"],
        payload["evidence_scope"],
        proposals,
    )
    if script.to_json() != text:
        raise ExperimentE2Error(
            "experiment script bytes are not canonical"
        )
    return script


def _validate_script_chain(
    case: ExperimentCase,
    script: ExperimentProposalScript,
) -> None:
    current = case.source_text
    for index, proposal in enumerate(script.proposals, start=1):
        if proposal.base_source_sha256 != _sha256_text(current):
            raise ExperimentE2Error(
                f"script {case.id}/{script.arm} proposal "
                f"{index} is stale"
            )
        try:
            current = apply_line_edit(current, proposal.edit)
        except RepairLoopError as error:
            raise ExperimentE2Error(
                f"script {case.id}/{script.arm} proposal "
                f"{index} is invalid: {error}"
            ) from error


def load_experiment_inputs(
    corpus: ExperimentCorpus,
    contexts_root: str | Path,
    proposals_root: str | Path,
) -> ExperimentInputs:
    context_root = Path(contexts_root).resolve()
    proposal_root = Path(proposals_root).resolve()
    expected, bundles = expected_contexts(corpus)
    contexts: list[ExperimentContext] = []
    scripts: list[ExperimentProposalScript] = []
    expected_context_files: set[str] = set()
    expected_script_files: set[str] = set()
    for context in expected:
        context_rel = f"{context.arm}/{context.case}.json"
        script_rel = (
            f"{context.arm}/{context.case}.script.json"
        )
        expected_context_files.add(context_rel)
        expected_script_files.add(script_rel)
        context_text = _read_json_text(
            context_root / context_rel,
            f"context {context.case}/{context.arm}",
        )
        contexts.append(
            load_experiment_context_json(context_text, context)
        )
        script_text = _read_json_text(
            proposal_root / script_rel,
            f"script {context.case}/{context.arm}",
        )
        script = load_experiment_script_json(script_text)
        if (
            script.arm != context.arm
            or script.case != context.case
            or script.context != context.id
        ):
            raise ExperimentE2Error(
                "script/context link differs for "
                f"{context.case}/{context.arm}"
            )
        case = next(
            item
            for item in corpus.cases
            if item.id == context.case
        )
        _validate_script_chain(case, script)
        scripts.append(script)

    actual_context_files = {
        path.relative_to(context_root).as_posix()
        for path in context_root.rglob("*")
        if path.is_file()
    }
    actual_script_files = {
        path.relative_to(proposal_root).as_posix()
        for path in proposal_root.rglob("*")
        if path.is_file()
    }
    if actual_context_files != expected_context_files:
        missing = sorted(
            expected_context_files - actual_context_files
        )
        extra = sorted(
            actual_context_files - expected_context_files
        )
        raise ExperimentE2Error(
            "context file set differs; missing="
            + repr(missing)
            + ", extra="
            + repr(extra)
        )
    if actual_script_files != expected_script_files:
        missing = sorted(
            expected_script_files - actual_script_files
        )
        extra = sorted(
            actual_script_files - expected_script_files
        )
        raise ExperimentE2Error(
            "script file set differs; missing="
            + repr(missing)
            + ", extra="
            + repr(extra)
        )
    return ExperimentInputs(
        corpus,
        tuple(contexts),
        tuple(scripts),
        bundles,
    )


def run_experiment(inputs: ExperimentInputs) -> ExperimentTrials:
    trials: list[ExperimentTrial] = []
    for case in inputs.corpus.cases:
        bundle = inputs.bundle_for(case.id)
        for arm in ARMS:
            context = inputs.context_for(case.id, arm)
            script = inputs.script_for(case.id, arm)
            try:
                loop = RepairHarness(
                    ScriptedPatchProposer(script.proposals),
                    checker=AffineChecker(),
                    max_iterations=MAX_PROPOSALS,
                ).run(
                    case.source_text,
                    case.display_path,
                    bundle,
                )
            except RepairLoopError as error:
                raise ExperimentE2Error(
                    f"trial {case.id}/{arm} failed: {error}"
                ) from error
            trials.append(
                ExperimentTrial.create(
                    arm=arm,
                    case=case.id,
                    context=context.id,
                    script=script.id,
                    bundle=bundle.id,
                    loop=loop,
                )
            )
    result = ExperimentTrials.create(inputs.corpus, trials)
    validate_trials(result, inputs)
    return result


def validate_trials(
    result: ExperimentTrials,
    inputs: ExperimentInputs,
) -> None:
    if result.corpus != inputs.corpus.id:
        raise ExperimentE2Error(
            "trial artifact cites a different corpus"
        )
    cases = {case.id: case for case in inputs.corpus.cases}
    for trial in result.trials:
        case = cases.get(trial.case)
        if case is None:
            raise ExperimentE2Error(
                "trial cites an unknown corpus case"
            )
        context = inputs.context_for(trial.case, trial.arm)
        script = inputs.script_for(trial.case, trial.arm)
        bundle = inputs.bundle_for(trial.case)
        if (
            trial.context != context.id
            or trial.script != script.id
            or trial.bundle != bundle.id
            or trial.loop.initial_source_sha256
            != case.source_sha256
        ):
            raise ExperimentE2Error(
                "trial links are stale for "
                f"{trial.case}/{trial.arm}"
            )
        if trial.attempts > len(script.proposals):
            raise ExperimentE2Error(
                "trial has attempts beyond its script"
            )
        current = case.source_text
        for index, attempt in enumerate(trial.loop.attempts):
            proposal = script.proposals[index]
            if attempt.proposal != proposal.id:
                raise ExperimentE2Error(
                    "trial attempt/proposal link is stale"
                )
            current = apply_line_edit(current, proposal.edit)
            if (
                attempt.candidate_source_sha256
                != _sha256_text(current)
            ):
                raise ExperimentE2Error(
                    "trial candidate-source link is stale"
                )
        if trial.status == "verified":
            if trial.loop.accepted_source != current:
                raise ExperimentE2Error(
                    "trial accepted source differs from script"
                )
        elif len(script.proposals) != MAX_PROPOSALS:
            raise ExperimentE2Error(
                "exhausted trial must consume four proposals"
            )


def _load_trial(
    payload: Mapping[str, Any],
    index: int,
) -> ExperimentTrial:
    field_name = f"trials.trials[{index}]"
    _exact_keys(
        payload,
        {
            "arm",
            "attempts",
            "bundle",
            "case",
            "context",
            "id",
            "loop",
            "schema",
            "score",
            "script",
            "status",
        },
        field_name,
    )
    if payload["schema"] != EXPERIMENT_TRIAL_SCHEMA:
        raise ExperimentE2Error(
            f"{field_name}.schema is unsupported"
        )
    if not isinstance(payload["loop"], Mapping):
        raise ExperimentE2Error(
            f"{field_name}.loop must be an object"
        )
    try:
        loop = load_repair_loop_json(
            _canonical_json(payload["loop"])
        )
    except RepairLoopError as error:
        raise ExperimentE2Error(
            f"{field_name}.loop is invalid: {error}"
        ) from error
    return ExperimentTrial(
        payload["id"],
        payload["arm"],
        payload["case"],
        payload["context"],
        payload["script"],
        payload["bundle"],
        payload["attempts"],
        payload["status"],
        payload["score"],
        loop,
    )


def load_experiment_trials_json(
    text: str,
    inputs: ExperimentInputs,
) -> ExperimentTrials:
    payload = _parse_json(text, "experiment trials")
    _exact_keys(
        payload,
        {
            "corpus",
            "evidence_scope",
            "id",
            "max_proposals",
            "proposer",
            "referee",
            "schema",
            "trials",
        },
        "trials",
    )
    if payload["schema"] != EXPERIMENT_TRIALS_SCHEMA:
        raise ExperimentE2Error(
            "unsupported experiment trials schema"
        )
    raw_trials = payload["trials"]
    if not isinstance(raw_trials, list):
        raise ExperimentE2Error(
            "trials.trials must be an array"
        )
    trials: list[ExperimentTrial] = []
    for index, raw in enumerate(raw_trials):
        if not isinstance(raw, Mapping):
            raise ExperimentE2Error(
                f"trials.trials[{index}] must be an object"
            )
        trials.append(_load_trial(raw, index))
    result = ExperimentTrials.create(inputs.corpus, trials)
    if (
        payload["id"] != result.id
        or payload["corpus"] != result.corpus
        or payload["max_proposals"] != result.max_proposals
        or payload["referee"] != result.referee
        or payload["proposer"] != result.proposer
        or payload["evidence_scope"] != result.evidence_scope
    ):
        raise ExperimentE2Error(
            "experiment trial envelope differs from canonical evidence"
        )
    validate_trials(result, inputs)
    return result
