"""Bounded repair harness with an untrusted proposal seam."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .backend import CheckerBackend
from .checker import AffineChecker
from .model import VerificationReport, VerificationStatus
from .pipeline import VerificationPipeline
from .repair_bundle import (
    RelatedContract,
    RepairBundle,
    RepairBundleBuilder,
    RepairBundleError,
    load_repair_bundle_json,
)


PATCH_PROPOSAL_SCHEMA = "codeskeptic.patch-proposal/v1"
PATCH_SCRIPT_SCHEMA = "codeskeptic.patch-script/v1"
REPAIR_LOOP_SCHEMA = "codeskeptic.repair-loop/v1"
REPAIR_LOOP_ID_SCHEMA = "codeskeptic.repair-loop-identity/v1"
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_ITERATIONS = 8


class RepairLoopError(ValueError):
    """Raised when a proposal or repair-loop artifact is invalid."""


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
    return _sha256(
        _identity_bytes(
            {
                "kind": kind,
                "schema": REPAIR_LOOP_ID_SCHEMA,
                "value": payload,
            }
        )
    )


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RepairLoopError(f"{field} must be non-empty text")
    return value


def _require_hash(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _HASH_PATTERN.fullmatch(text) is None:
        raise RepairLoopError(
            f"{field} must be a lowercase sha256 identity"
        )
    return text


def _exact_keys(
    value: Mapping[str, Any],
    required: set[str],
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required)
    if missing:
        raise RepairLoopError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise RepairLoopError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class LineEdit:
    start_line: int
    end_line: int
    replacement: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_line, bool)
            or isinstance(self.end_line, bool)
            or not isinstance(self.start_line, int)
            or not isinstance(self.end_line, int)
            or self.start_line < 1
            or self.end_line < self.start_line
        ):
            raise RepairLoopError("edit line range is invalid")
        normalized = tuple(self.replacement)
        for line in normalized:
            if (
                not isinstance(line, str)
                or "\n" in line
                or "\r" in line
                or "\x00" in line
            ):
                raise RepairLoopError(
                    "replacement lines must not contain newline or NUL"
                )
        object.__setattr__(self, "replacement", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "end_line": self.end_line,
            "replacement": list(self.replacement),
            "start_line": self.start_line,
        }


@dataclass(frozen=True, slots=True)
class PatchProposal:
    id: str
    base_source_sha256: str
    edit: LineEdit

    def __post_init__(self) -> None:
        _require_hash(
            self.base_source_sha256,
            "proposal.base_source_sha256",
        )
        if not isinstance(self.edit, LineEdit):
            raise RepairLoopError(
                "proposal.edit must be a LineEdit"
            )
        expected = _content_id(
            "patch-proposal",
            self.content_dict(),
        )
        if _require_hash(self.id, "proposal.id") != expected:
            raise RepairLoopError(
                "proposal.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        base_source_sha256: str,
        edit: LineEdit,
    ) -> "PatchProposal":
        content = {
            "base_source_sha256": base_source_sha256,
            "edit": edit.to_dict(),
            "schema": PATCH_PROPOSAL_SCHEMA,
        }
        return cls(
            _content_id("patch-proposal", content),
            base_source_sha256,
            edit,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "base_source_sha256": self.base_source_sha256,
            "edit": self.edit.to_dict(),
            "schema": PATCH_PROPOSAL_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}


class PatchProposer(ABC):
    """Untrusted seam: proposals are data, never referee decisions."""

    @abstractmethod
    def propose(
        self,
        bundle: RepairBundle,
        iteration: int,
    ) -> PatchProposal:
        """Return one untrusted proposal for this iteration."""


class ScriptedPatchProposer(PatchProposer):
    def __init__(self, proposals: Sequence[PatchProposal]) -> None:
        self.proposals = tuple(proposals)

    def propose(
        self,
        bundle: RepairBundle,
        iteration: int,
    ) -> PatchProposal:
        del bundle
        index = iteration - 1
        if index >= len(self.proposals):
            raise RepairLoopError(
                "script has no proposal for this iteration"
            )
        return self.proposals[index]


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    iteration: int
    proposal: str | None
    status: str
    candidate_source_sha256: str | None
    verification_sha256: str | None
    results: tuple[tuple[str, str], ...]
    diagnostic: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.iteration, bool)
            or not isinstance(self.iteration, int)
            or self.iteration < 1
        ):
            raise RepairLoopError(
                "attempt.iteration must be positive"
            )
        if self.proposal is not None:
            _require_hash(self.proposal, "attempt.proposal")
        if self.status not in {
            "proposal_error",
            "rejected",
            "referee_blocked",
            "verified",
            "violated",
        }:
            raise RepairLoopError(
                f"attempt.status is unsupported: {self.status!r}"
            )
        if self.status == "proposal_error":
            if self.proposal is not None:
                raise RepairLoopError(
                    "proposal_error cannot carry a proposal ID"
                )
        elif self.proposal is None:
            raise RepairLoopError(
                "non-proposer-error attempts require a proposal ID"
            )
        for value, field in (
            (
                self.candidate_source_sha256,
                "attempt.candidate_source_sha256",
            ),
            (
                self.verification_sha256,
                "attempt.verification_sha256",
            ),
        ):
            if value is not None:
                _require_hash(value, field)
        ordered = tuple(sorted(self.results))
        if len(ordered) != len(set(ordered)):
            raise RepairLoopError(
                "attempt.results must not contain duplicates"
            )
        admitted_statuses = {
            status.value for status in VerificationStatus
        }
        for obligation, status in ordered:
            _require_text(obligation, "attempt result obligation")
            if status not in admitted_statuses:
                raise RepairLoopError(
                    "attempt result status is unsupported"
                )
        if self.status in {
            "referee_blocked",
            "verified",
            "violated",
        } and (
            self.candidate_source_sha256 is None
            or self.verification_sha256 is None
            or not ordered
        ):
            raise RepairLoopError(
                "checked attempts require candidate/report/results evidence"
            )
        _require_text(self.diagnostic, "attempt.diagnostic")
        object.__setattr__(self, "results", ordered)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_source_sha256": self.candidate_source_sha256,
            "diagnostic": self.diagnostic,
            "iteration": self.iteration,
            "proposal": self.proposal,
            "results": [
                {"obligation": obligation, "status": status}
                for obligation, status in self.results
            ],
            "status": self.status,
            "verification_sha256": self.verification_sha256,
        }


@dataclass(frozen=True, slots=True)
class RepairLoopLog:
    id: str
    initial_bundle: str
    initial_source_sha256: str
    max_iterations: int
    attempts: tuple[RepairAttempt, ...]
    status: str
    accepted_proposal: str | None
    accepted_source: str | None
    accepted_source_sha256: str | None

    def __post_init__(self) -> None:
        _require_hash(self.initial_bundle, "loop.initial_bundle")
        _require_hash(
            self.initial_source_sha256,
            "loop.initial_source_sha256",
        )
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or not 1 <= self.max_iterations <= MAX_ITERATIONS
        ):
            raise RepairLoopError(
                f"max_iterations must be from 1 to {MAX_ITERATIONS}"
            )
        if len(self.attempts) > self.max_iterations:
            raise RepairLoopError(
                "loop has more attempts than max_iterations"
            )
        if tuple(
            attempt.iteration for attempt in self.attempts
        ) != tuple(range(1, len(self.attempts) + 1)):
            raise RepairLoopError(
                "attempt iterations must be contiguous"
            )
        if self.status not in {"exhausted", "verified"}:
            raise RepairLoopError("loop.status is unsupported")
        if self.status == "verified":
            if (
                not self.attempts
                or self.attempts[-1].status != "verified"
                or self.accepted_proposal
                != self.attempts[-1].proposal
                or self.accepted_source is None
                or self.accepted_source_sha256 is None
            ):
                raise RepairLoopError(
                    "verified loop requires exact accepted evidence"
                )
            _require_hash(
                self.accepted_source_sha256,
                "loop.accepted_source_sha256",
            )
            try:
                actual = _sha256(
                    self.accepted_source.encode("utf-8")
                )
            except UnicodeError as error:
                raise RepairLoopError(
                    "accepted source must be UTF-8"
                ) from error
            if actual != self.accepted_source_sha256:
                raise RepairLoopError(
                    "accepted source hash mismatch"
                )
        elif len(self.attempts) != self.max_iterations:
            raise RepairLoopError(
                "exhausted loop must record exactly max_iterations attempts"
            )
        elif any(
            value is not None
            for value in (
                self.accepted_proposal,
                self.accepted_source,
                self.accepted_source_sha256,
            )
        ):
            raise RepairLoopError(
                "exhausted loop cannot carry accepted source"
            )
        expected = _content_id("repair-loop", self.content_dict())
        if _require_hash(self.id, "loop.id") != expected:
            raise RepairLoopError(
                "loop.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        initial_bundle: str,
        initial_source_sha256: str,
        max_iterations: int,
        attempts: Sequence[RepairAttempt],
        status: str,
        accepted_proposal: str | None = None,
        accepted_source: str | None = None,
        accepted_source_sha256: str | None = None,
    ) -> "RepairLoopLog":
        attempt_tuple = tuple(attempts)
        content = {
            "accepted": (
                {
                    "proposal": accepted_proposal,
                    "source": accepted_source,
                    "source_sha256": accepted_source_sha256,
                }
                if status == "verified"
                else None
            ),
            "attempts": [
                attempt.to_dict() for attempt in attempt_tuple
            ],
            "initial_bundle": initial_bundle,
            "initial_source_sha256": initial_source_sha256,
            "max_iterations": max_iterations,
            "schema": REPAIR_LOOP_SCHEMA,
            "status": status,
        }
        return cls(
            _content_id("repair-loop", content),
            initial_bundle,
            initial_source_sha256,
            max_iterations,
            attempt_tuple,
            status,
            accepted_proposal,
            accepted_source,
            accepted_source_sha256,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "accepted": (
                {
                    "proposal": self.accepted_proposal,
                    "source": self.accepted_source,
                    "source_sha256": self.accepted_source_sha256,
                }
                if self.status == "verified"
                else None
            ),
            "attempts": [
                attempt.to_dict() for attempt in self.attempts
            ],
            "initial_bundle": self.initial_bundle,
            "initial_source_sha256": self.initial_source_sha256,
            "max_iterations": self.max_iterations,
            "schema": REPAIR_LOOP_SCHEMA,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


class RepairHarness:
    def __init__(
        self,
        proposer: PatchProposer,
        *,
        clang: str | None = None,
        checker: CheckerBackend | None = None,
        referee: str = "codeskeptic.affine/v1",
        max_iterations: int = 3,
    ) -> None:
        if not isinstance(proposer, PatchProposer):
            raise RepairLoopError(
                "proposer must implement PatchProposer"
            )
        if (
            isinstance(max_iterations, bool)
            or not isinstance(max_iterations, int)
            or not 1 <= max_iterations <= MAX_ITERATIONS
        ):
            raise RepairLoopError(
                f"max_iterations must be from 1 to {MAX_ITERATIONS}"
            )
        self.proposer = proposer
        self.checker = checker or AffineChecker()
        self.builder = RepairBundleBuilder(
            clang,
            checker=self.checker,
            referee=referee,
        )
        self.pipeline = VerificationPipeline(
            clang,
            checker=self.checker,
        )
        self.max_iterations = max_iterations

    def run(
        self,
        source: str,
        display_path: str,
        bundle: RepairBundle,
    ) -> RepairLoopLog:
        try:
            initial_hash = _sha256(source.encode("utf-8"))
        except UnicodeError as error:
            raise RepairLoopError("source must be UTF-8") from error
        if (
            bundle.source_file != display_path
            or bundle.source_sha256 != initial_hash
        ):
            raise RepairLoopError(
                "initial bundle does not match source/display path"
            )
        initial_report = self.pipeline.verify_source(
            source,
            display_path,
        )
        load_repair_bundle_json(
            bundle.to_json(),
            source=source,
            report=initial_report,
        )
        target_function = str(bundle.obligation["function"])
        current_source = source
        current_bundle = bundle
        seen: set[str] = set()
        attempts: list[RepairAttempt] = []

        for iteration in range(1, self.max_iterations + 1):
            try:
                proposal = self.proposer.propose(
                    current_bundle,
                    iteration,
                )
                if not isinstance(proposal, PatchProposal):
                    raise RepairLoopError(
                        "proposer returned a non-proposal value"
                    )
            except Exception as error:
                attempts.append(
                    RepairAttempt(
                        iteration,
                        None,
                        "proposal_error",
                        None,
                        None,
                        (),
                        (
                            "untrusted proposer error: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                )
                continue
            if proposal.id in seen:
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "rejected",
                        None,
                        None,
                        (),
                        "proposal identity was already attempted",
                    )
                )
                continue
            seen.add(proposal.id)
            current_hash = _sha256(
                current_source.encode("utf-8")
            )
            if proposal.base_source_sha256 != current_hash:
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "rejected",
                        None,
                        None,
                        (),
                        "proposal base source hash is stale",
                    )
                )
                continue
            try:
                candidate = apply_line_edit(
                    current_source,
                    proposal.edit,
                )
                candidate_hash = _sha256(
                    candidate.encode("utf-8")
                )
            except (RepairLoopError, UnicodeError) as error:
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "rejected",
                        None,
                        None,
                        (),
                        f"invalid proposal: {error}",
                    )
                )
                continue
            if candidate == current_source:
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "rejected",
                        candidate_hash,
                        None,
                        (),
                        "proposal is a no-op",
                    )
                )
                continue

            report = self.pipeline.verify_source(
                candidate,
                display_path,
            )
            report_hash = _sha256(
                report.to_json().encode("utf-8")
            )
            statuses = tuple(
                (
                    result.obligation_id,
                    result.status.value,
                )
                for result in report.results
            )
            if not self._contracts_preserved(
                report,
                target_function,
                current_bundle.contracts,
            ):
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "rejected",
                        candidate_hash,
                        report_hash,
                        statuses,
                        "candidate changed or removed target contracts",
                    )
                )
                continue
            target_results = [
                result
                for result in report.results
                if result.function == target_function
            ]
            if (
                target_results
                and not report.module.unsupported
                and all(
                    result.status == VerificationStatus.VERIFIED
                    for result in target_results
                )
            ):
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "verified",
                        candidate_hash,
                        report_hash,
                        statuses,
                        "accepted by complete target-function verification",
                    )
                )
                return RepairLoopLog.create(
                    initial_bundle=bundle.id,
                    initial_source_sha256=initial_hash,
                    max_iterations=self.max_iterations,
                    attempts=attempts,
                    status="verified",
                    accepted_proposal=proposal.id,
                    accepted_source=candidate,
                    accepted_source_sha256=candidate_hash,
                )

            violations = sorted(
                (
                    result
                    for result in target_results
                    if (
                        result.status
                        == VerificationStatus.VIOLATED
                        and result.counterexample
                    )
                ),
                key=lambda result: (
                    result.kind
                    != current_bundle.result["kind"],
                    result.obligation_id,
                ),
            )
            if violations:
                try:
                    next_bundle = self.builder.build(
                        candidate,
                        display_path,
                        report,
                        violations[0].obligation_id,
                    )
                except RepairBundleError as error:
                    attempts.append(
                        RepairAttempt(
                            iteration,
                            proposal.id,
                            "referee_blocked",
                            candidate_hash,
                            report_hash,
                            statuses,
                            f"candidate rebundle failed: {error}",
                        )
                    )
                    continue
                attempts.append(
                    RepairAttempt(
                        iteration,
                        proposal.id,
                        "violated",
                        candidate_hash,
                        report_hash,
                        statuses,
                        "replayed violation remains; continuing",
                    )
                )
                current_source = candidate
                current_bundle = next_bundle
                continue

            attempts.append(
                RepairAttempt(
                    iteration,
                    proposal.id,
                    "referee_blocked",
                    candidate_hash,
                    report_hash,
                    statuses,
                    "candidate was not completely verified or replayably violated",
                )
            )

        return RepairLoopLog.create(
            initial_bundle=bundle.id,
            initial_source_sha256=initial_hash,
            max_iterations=self.max_iterations,
            attempts=attempts,
            status="exhausted",
        )

    @staticmethod
    def _contracts_preserved(
        report: VerificationReport,
        function: str,
        expected: tuple[RelatedContract, ...],
    ) -> bool:
        try:
            actual = RepairBundleBuilder._contracts(
                report,
                function,
            )
        except RepairBundleError:
            return False
        return actual == expected


def apply_line_edit(source: str, edit: LineEdit) -> str:
    lines = source.splitlines()
    if edit.end_line > len(lines):
        raise RepairLoopError(
            "edit range is outside current source"
        )
    had_final_newline = source.endswith(("\n", "\r"))
    updated = (
        lines[: edit.start_line - 1]
        + list(edit.replacement)
        + lines[edit.end_line :]
    )
    rendered = "\n".join(updated)
    if had_final_newline:
        rendered += "\n"
    return rendered


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RepairLoopError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RepairLoopError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def load_patch_script_json(text: str) -> tuple[PatchProposal, ...]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise RepairLoopError(
            f"invalid patch-script JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise RepairLoopError(
            "patch script must be a JSON object"
        )
    _exact_keys(payload, {"proposals", "schema"}, "script")
    if payload["schema"] != PATCH_SCRIPT_SCHEMA:
        raise RepairLoopError(
            "unsupported patch-script schema"
        )
    raw_proposals = payload["proposals"]
    if not isinstance(raw_proposals, list):
        raise RepairLoopError(
            "script.proposals must be an array"
        )
    proposals: list[PatchProposal] = []
    for index, raw in enumerate(raw_proposals):
        field = f"script.proposals[{index}]"
        if not isinstance(raw, Mapping):
            raise RepairLoopError(f"{field} must be an object")
        _exact_keys(
            raw,
            {"base_source_sha256", "edit", "id", "schema"},
            field,
        )
        if raw["schema"] != PATCH_PROPOSAL_SCHEMA:
            raise RepairLoopError(
                f"{field}.schema is unsupported"
            )
        edit = raw["edit"]
        if not isinstance(edit, Mapping):
            raise RepairLoopError(f"{field}.edit must be an object")
        _exact_keys(
            edit,
            {"end_line", "replacement", "start_line"},
            f"{field}.edit",
        )
        replacement = edit["replacement"]
        if not isinstance(replacement, list):
            raise RepairLoopError(
                f"{field}.edit.replacement must be an array"
            )
        proposals.append(
            PatchProposal(
                raw["id"],
                raw["base_source_sha256"],
                LineEdit(
                    edit["start_line"],
                    edit["end_line"],
                    tuple(replacement),
                ),
            )
        )
    return tuple(proposals)

def load_repair_loop_json(text: str) -> RepairLoopLog:
    """Load a strict canonical repair-loop log."""

    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise RepairLoopError(
            f"invalid repair-loop JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise RepairLoopError(
            "repair loop must be a JSON object"
        )
    _exact_keys(
        payload,
        {
            "accepted",
            "attempts",
            "id",
            "initial_bundle",
            "initial_source_sha256",
            "max_iterations",
            "schema",
            "status",
        },
        "loop",
    )
    if payload["schema"] != REPAIR_LOOP_SCHEMA:
        raise RepairLoopError(
            "unsupported repair-loop schema"
        )
    raw_attempts = payload["attempts"]
    if not isinstance(raw_attempts, list):
        raise RepairLoopError("loop.attempts must be an array")
    attempts: list[RepairAttempt] = []
    for index, raw in enumerate(raw_attempts):
        field = f"loop.attempts[{index}]"
        if not isinstance(raw, Mapping):
            raise RepairLoopError(f"{field} must be an object")
        _exact_keys(
            raw,
            {
                "candidate_source_sha256",
                "diagnostic",
                "iteration",
                "proposal",
                "results",
                "status",
                "verification_sha256",
            },
            field,
        )
        raw_results = raw["results"]
        if not isinstance(raw_results, list):
            raise RepairLoopError(
                f"{field}.results must be an array"
            )
        results: list[tuple[str, str]] = []
        for result_index, result in enumerate(raw_results):
            result_field = (
                f"{field}.results[{result_index}]"
            )
            if not isinstance(result, Mapping):
                raise RepairLoopError(
                    f"{result_field} must be an object"
                )
            _exact_keys(
                result,
                {"obligation", "status"},
                result_field,
            )
            results.append(
                (
                    _require_text(
                        result["obligation"],
                        f"{result_field}.obligation",
                    ),
                    _require_text(
                        result["status"],
                        f"{result_field}.status",
                    ),
                )
            )
        attempts.append(
            RepairAttempt(
                raw["iteration"],
                raw["proposal"],
                raw["status"],
                raw["candidate_source_sha256"],
                raw["verification_sha256"],
                tuple(results),
                raw["diagnostic"],
            )
        )
    accepted = payload["accepted"]
    proposal = None
    source = None
    source_hash = None
    if accepted is not None:
        if not isinstance(accepted, Mapping):
            raise RepairLoopError(
                "loop.accepted must be an object or null"
            )
        _exact_keys(
            accepted,
            {"proposal", "source", "source_sha256"},
            "loop.accepted",
        )
        proposal = _require_hash(
            accepted["proposal"],
            "loop.accepted.proposal",
        )
        source = _require_text(
            accepted["source"],
            "loop.accepted.source",
        )
        source_hash = _require_hash(
            accepted["source_sha256"],
            "loop.accepted.source_sha256",
        )
    return RepairLoopLog(
        _require_hash(payload["id"], "loop.id"),
        _require_hash(
            payload["initial_bundle"],
            "loop.initial_bundle",
        ),
        _require_hash(
            payload["initial_source_sha256"],
            "loop.initial_source_sha256",
        ),
        payload["max_iterations"],
        tuple(attempts),
        _require_text(payload["status"], "loop.status"),
        proposal,
        source,
        source_hash,
    )
