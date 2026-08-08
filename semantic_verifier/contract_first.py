"""Executable, deterministic contract-first workflow artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .backend import CheckerBackend
from .checker import DeterministicChecker
from .model import VerificationReport, VerificationStatus
from .pipeline import VerificationPipeline


TASK_SCHEMA = "codeskeptic.contract-first-task/v1"
RUN_SCHEMA = "codeskeptic.contract-first-run/v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTRACT = re.compile(
    r"^// cs: (?P<ai>ai )?(?P<kind>requires|ensures|modifies)"
    r"(?: (?P<expression>.*))?$"
)


class ContractFirstInputError(ValueError):
    """Raised when a workflow artifact or transition fails closed."""


def _expect_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractFirstInputError(f"{label} must be an object")
    return value


def _expect_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        raise ContractFirstInputError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise ContractFirstInputError(f"{label} has unknown fields: {', '.join(unknown)}")


def _expect_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractFirstInputError(f"{label} must be a non-empty string")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ContractFirstTask:
    task_id: str
    request: str
    proposed: ArtifactReference
    accepted: ArtifactReference
    implemented: ArtifactReference
    function: str
    expected_summary: Mapping[str, int]

    def identity_dict(self) -> dict[str, Any]:
        return {
            "artifacts": {
                "accepted": self.accepted.to_dict(),
                "implemented": self.implemented.to_dict(),
                "proposed": self.proposed.to_dict(),
            },
            "request": self.request,
            "schema": TASK_SCHEMA,
            "task_id": self.task_id,
            "verification": {
                "expected_summary": dict(self.expected_summary),
                "function": self.function,
            },
        }


@dataclass(frozen=True, slots=True)
class ContractLine:
    text: str
    kind: str
    machine_proposed: bool


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    name: str
    status: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_sha256": self.evidence_sha256,
            "name": self.name,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ContractFirstRun:
    workflow_id: str
    task_id: str
    request_sha256: str
    artifact_hashes: Mapping[str, str]
    accepted_contracts_sha256: str
    transitions: tuple[WorkflowStep, ...]
    function: str
    verification_summary: Mapping[str, int]
    verification_report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_contracts_sha256": self.accepted_contracts_sha256,
            "artifact_hashes": dict(self.artifact_hashes),
            "function": self.function,
            "human_attestation_required": True,
            "request_sha256": self.request_sha256,
            "schema": RUN_SCHEMA,
            "state": "complete",
            "task_id": self.task_id,
            "transitions": [step.to_dict() for step in self.transitions],
            "verification_report_sha256": self.verification_report_sha256,
            "verification_summary": dict(self.verification_summary),
            "workflow_id": self.workflow_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _artifact_reference(value: Any, label: str) -> ArtifactReference:
    payload = _expect_object(value, label)
    _expect_fields(payload, {"path", "sha256"}, label)
    path = _expect_text(payload["path"], f"{label}.path")
    digest = _expect_text(payload["sha256"], f"{label}.sha256")
    if _HASH.fullmatch(digest) is None:
        raise ContractFirstInputError(f"{label}.sha256 is not canonical SHA-256")
    return ArtifactReference(path, digest)


def load_task(payload: Mapping[str, Any]) -> ContractFirstTask:
    root = _expect_object(payload, "task")
    _expect_fields(
        root, {"schema", "task_id", "request", "artifacts", "verification"}, "task"
    )
    if root["schema"] != TASK_SCHEMA:
        raise ContractFirstInputError(
            f"unsupported task schema: expected {TASK_SCHEMA!r}, got {root['schema']!r}"
        )
    artifacts = _expect_object(root["artifacts"], "task.artifacts")
    _expect_fields(artifacts, {"proposed", "accepted", "implemented"}, "task.artifacts")
    verification = _expect_object(root["verification"], "task.verification")
    _expect_fields(
        verification, {"function", "expected_summary"}, "task.verification"
    )
    summary = _expect_object(
        verification["expected_summary"], "task.verification.expected_summary"
    )
    statuses = {status.value for status in VerificationStatus}
    _expect_fields(summary, statuses, "task.verification.expected_summary")
    normalized_summary: dict[str, int] = {}
    for status in sorted(statuses):
        count = summary[status]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ContractFirstInputError(
                f"task.verification.expected_summary.{status} must be non-negative"
            )
        normalized_summary[status] = count
    return ContractFirstTask(
        task_id=_expect_text(root["task_id"], "task.task_id"),
        request=_expect_text(root["request"], "task.request"),
        proposed=_artifact_reference(artifacts["proposed"], "task.artifacts.proposed"),
        accepted=_artifact_reference(artifacts["accepted"], "task.artifacts.accepted"),
        implemented=_artifact_reference(
            artifacts["implemented"], "task.artifacts.implemented"
        ),
        function=_expect_text(verification["function"], "task.verification.function"),
        expected_summary=normalized_summary,
    )


def read_task(path: Path) -> ContractFirstTask:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractFirstInputError(f"cannot read task {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ContractFirstInputError(f"task is not valid JSON: {error.msg}") from error
    return load_task(_expect_object(payload, "task"))


def _safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ContractFirstInputError(f"artifact path is unsafe: {relative!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ContractFirstInputError(f"artifact escapes task root: {relative!r}") from error
    if not resolved.is_file():
        raise ContractFirstInputError(f"artifact is missing: {relative!r}")
    return resolved


def _read_artifact(root: Path, reference: ArtifactReference, label: str) -> str:
    path = _safe_artifact_path(root, reference.path)
    try:
        content = path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ContractFirstInputError(f"cannot read UTF-8 {label}: {error}") from error
    actual = _sha256_bytes(content)
    if actual != reference.sha256:
        raise ContractFirstInputError(
            f"{label} hash drift: expected {reference.sha256}, got {actual}"
        )
    return text


def _split_contract_source(
    source: str, label: str
) -> tuple[tuple[ContractLine, ...], tuple[str, ...]]:
    lines = source.splitlines()
    contracts: list[ContractLine] = []
    index = 0
    while index < len(lines) and lines[index].startswith("// cs: "):
        match = _CONTRACT.fullmatch(lines[index])
        if match is None:
            raise ContractFirstInputError(f"{label} has malformed contract line {index + 1}")
        expression = (match.group("expression") or "").strip()
        if match.group("kind") != "modifies" and not expression:
            raise ContractFirstInputError(f"{label} has empty contract line {index + 1}")
        contracts.append(
            ContractLine(
                text=lines[index],
                kind=match.group("kind"),
                machine_proposed=bool(match.group("ai")),
            )
        )
        index += 1
    if not contracts:
        raise ContractFirstInputError(f"{label} has no leading contract set")
    if index >= len(lines) or not any(line.strip() for line in lines[index:]):
        raise ContractFirstInputError(f"{label} has no declaration or implementation")
    return tuple(contracts), tuple(lines[index:])


def _require_verified(report: VerificationReport, label: str) -> None:
    if not report.results:
        raise ContractFirstInputError(f"{label} produced no verification obligations")
    failure = next(
        (result for result in report.results if result.status != VerificationStatus.VERIFIED),
        None,
    )
    if failure is not None:
        raise ContractFirstInputError(
            f"{label} verification {failure.status.value}: {failure.kind}: {failure.message}"
        )


def run_contract_first(
    manifest_path: Path,
    *,
    checker: CheckerBackend | None = None,
    clang: str | None = None,
) -> ContractFirstRun:
    task = read_task(manifest_path)
    root = manifest_path.resolve().parent
    proposed = _read_artifact(root, task.proposed, "proposed artifact")
    accepted = _read_artifact(root, task.accepted, "accepted artifact")
    implemented = _read_artifact(root, task.implemented, "implemented artifact")

    proposed_contracts, proposed_tail = _split_contract_source(proposed, "proposed")
    accepted_contracts, accepted_tail = _split_contract_source(accepted, "accepted")
    implementation_contracts, implementation_tail = _split_contract_source(
        implemented, "implemented"
    )
    if not all(contract.machine_proposed for contract in proposed_contracts):
        raise ContractFirstInputError("every proposed contract must retain cs: ai")
    if any(contract.machine_proposed for contract in accepted_contracts):
        raise ContractFirstInputError("accepted contracts must be marker-free")
    if len(proposed_contracts) != len(accepted_contracts):
        raise ContractFirstInputError("proposal and approval contract counts differ")
    if [item.kind for item in proposed_contracts] != [
        item.kind for item in accepted_contracts
    ]:
        raise ContractFirstInputError("proposal and approval contract kinds differ")
    if proposed_tail != accepted_tail:
        raise ContractFirstInputError("proposal and approval declarations differ")
    if tuple(item.text for item in implementation_contracts) != tuple(
        item.text for item in accepted_contracts
    ):
        raise ContractFirstInputError(
            "implementation contracts differ from the accepted contract set"
        )
    declaration = "\n".join(accepted_tail).strip()
    signature = declaration.removesuffix(";").strip()
    implementation_text = "\n".join(implementation_tail).lstrip()
    if not declaration.endswith(";") or not implementation_text.startswith(signature):
        raise ContractFirstInputError(
            "implementation signature differs from the accepted declaration"
        )
    suffix = implementation_text[len(signature) :].lstrip()
    if not suffix.startswith("{"):
        raise ContractFirstInputError("implemented artifact has no function body")

    selected_checker = checker or DeterministicChecker()
    proposal_report = VerificationPipeline(
        clang, checker=selected_checker
    ).verify_source(proposed, "contract-first-proposed.cpp")
    _require_verified(proposal_report, "proposal")
    accepted_report = VerificationPipeline(
        clang, checker=selected_checker
    ).verify_source(accepted, "contract-first-accepted.cpp")
    _require_verified(accepted_report, "approval")
    implementation_report = VerificationPipeline(
        clang, checker=selected_checker
    ).verify_source(implemented, "contract-first-implemented.cpp")
    _require_verified(implementation_report, "implementation")
    if not any(
        function.name == task.function for function in implementation_report.module.functions
    ):
        raise ContractFirstInputError("verified implementation omitted the target function")
    summary = implementation_report.summary()
    if summary != dict(task.expected_summary):
        raise ContractFirstInputError(
            "verification summary differs from the task manifest: "
            f"expected {dict(task.expected_summary)}, got {summary}"
        )

    artifact_hashes = {
        "accepted": task.accepted.sha256,
        "implemented": task.implemented.sha256,
        "proposed": task.proposed.sha256,
    }
    accepted_contract_text = "\n".join(
        contract.text for contract in accepted_contracts
    ) + "\n"
    report_hash = _sha256_text(implementation_report.to_json(include_ir=False))
    workflow_identity = {
        "artifact_hashes": artifact_hashes,
        "request_sha256": _sha256_text(task.request),
        "schema": RUN_SCHEMA,
        "task": task.identity_dict(),
        "verification_report_sha256": report_hash,
    }
    transitions = (
        WorkflowStep(
            "request_to_proposed", "verified", _sha256_text(proposed)
        ),
        WorkflowStep(
            "proposed_to_accepted", "verified", _sha256_text(accepted_contract_text)
        ),
        WorkflowStep(
            "accepted_to_implementation", "verified", _sha256_text(implemented)
        ),
        WorkflowStep(
            "implementation_to_verification", "verified", report_hash
        ),
    )
    return ContractFirstRun(
        workflow_id=_sha256_text(_canonical_json(workflow_identity)),
        task_id=task.task_id,
        request_sha256=_sha256_text(task.request),
        artifact_hashes=artifact_hashes,
        accepted_contracts_sha256=_sha256_text(accepted_contract_text),
        transitions=transitions,
        function=task.function,
        verification_summary=summary,
        verification_report_sha256=report_hash,
    )