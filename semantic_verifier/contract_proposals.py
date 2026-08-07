"""Deterministic offline prompt packs for untrusted contract proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
from typing import Any

from .backend import CheckerBackend
from .checker import DeterministicChecker
from .model import VerificationStatus
from .pipeline import VerificationPipeline


REQUEST_SCHEMA = "codeskeptic.contract-proposal-request/v1"
PROMPT_SCHEMA = "codeskeptic.contract-proposal-prompt/v1"
RESPONSE_SCHEMA = "codeskeptic.contract-proposal-response/v1"
PRE_SCREEN_SCHEMA = "codeskeptic.contract-proposal-pre-screen/v1"
_MACHINE_MARKER = "cs: ai"
_PACK_PARTS = ("prompt_packs", "contract_proposal", "v1")
_ALLOWED_ROLES = frozenset({"global", "local", "parameter", "result"})


class ProposalInputError(ValueError):
    """Raised when an offline proposal request is malformed or ambiguous."""


def _expect_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProposalInputError(f"{label} must be an object")
    return value


def _expect_fields(
    value: Mapping[str, Any], required: set[str], label: str
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ProposalInputError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise ProposalInputError(f"{label} has unknown fields: {', '.join(unknown)}")


def _expect_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProposalInputError(f"{label} must be a non-empty string")
    return value


def _expect_text_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProposalInputError(f"{label} must be an array")
    items = tuple(_expect_text(item, f"{label} item") for item in value)
    if len(set(items)) != len(items):
        raise ProposalInputError(f"{label} contains duplicates")
    return tuple(sorted(items))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pack_resource(name: str) -> str:
    resource = files("semantic_verifier")
    for part in (*_PACK_PARTS, name):
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class ProposalSymbol:
    name: str
    type: str
    role: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "role": self.role, "type": self.type}


@dataclass(frozen=True, slots=True)
class ProposalTarget:
    language: str
    function: str
    signature: str
    body: str

    def to_dict(self) -> dict[str, str]:
        return {
            "body": self.body,
            "function": self.function,
            "language": self.language,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class ProposalContext:
    symbols: tuple[ProposalSymbol, ...]
    existing_contracts: tuple[str, ...]
    callee_contracts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "callee_contracts": list(self.callee_contracts),
            "existing_contracts": list(self.existing_contracts),
            "symbols": [symbol.to_dict() for symbol in self.symbols],
        }


@dataclass(frozen=True, slots=True)
class ProposalSource:
    file: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line}


@dataclass(frozen=True, slots=True)
class ContractProposalRequest:
    target: ProposalTarget
    context: ProposalContext
    source: ProposalSource

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "schema": REQUEST_SCHEMA,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
        }

    def identity_dict(self) -> dict[str, Any]:
        """Logical identity deliberately excludes checkout path and source line."""

        return {
            "context": self.context.to_dict(),
            "schema": REQUEST_SCHEMA,
            "target": self.target.to_dict(),
        }


def load_request(payload: Mapping[str, Any]) -> ContractProposalRequest:
    root = _expect_object(payload, "request")
    _expect_fields(root, {"schema", "target", "context", "source"}, "request")
    if root["schema"] != REQUEST_SCHEMA:
        raise ProposalInputError(
            f"unsupported request schema: expected {REQUEST_SCHEMA!r}, "
            f"got {root['schema']!r}"
        )

    target_payload = _expect_object(root["target"], "target")
    _expect_fields(
        target_payload, {"language", "function", "signature", "body"}, "target"
    )
    language = _expect_text(target_payload["language"], "target.language")
    if language != "c++17":
        raise ProposalInputError("target.language must be 'c++17'")
    target = ProposalTarget(
        language=language,
        function=_expect_text(target_payload["function"], "target.function"),
        signature=_expect_text(target_payload["signature"], "target.signature"),
        body=_expect_text(target_payload["body"], "target.body"),
    )

    context_payload = _expect_object(root["context"], "context")
    _expect_fields(
        context_payload,
        {"symbols", "existing_contracts", "callee_contracts"},
        "context",
    )
    raw_symbols = context_payload["symbols"]
    if not isinstance(raw_symbols, list):
        raise ProposalInputError("context.symbols must be an array")
    symbols: list[ProposalSymbol] = []
    for index, raw_symbol in enumerate(raw_symbols):
        symbol_payload = _expect_object(raw_symbol, f"context.symbols[{index}]")
        _expect_fields(
            symbol_payload, {"name", "type", "role"}, f"context.symbols[{index}]"
        )
        role = _expect_text(symbol_payload["role"], f"context.symbols[{index}].role")
        if role not in _ALLOWED_ROLES:
            raise ProposalInputError(
                f"context.symbols[{index}].role is unsupported: {role!r}"
            )
        symbols.append(
            ProposalSymbol(
                name=_expect_text(
                    symbol_payload["name"], f"context.symbols[{index}].name"
                ),
                type=_expect_text(
                    symbol_payload["type"], f"context.symbols[{index}].type"
                ),
                role=role,
            )
        )
    names = [symbol.name for symbol in symbols]
    if len(set(names)) != len(names):
        raise ProposalInputError("context.symbols contains duplicate names")
    context = ProposalContext(
        symbols=tuple(sorted(symbols, key=lambda item: (item.name, item.role, item.type))),
        existing_contracts=_expect_text_list(
            context_payload["existing_contracts"], "context.existing_contracts"
        ),
        callee_contracts=_expect_text_list(
            context_payload["callee_contracts"], "context.callee_contracts"
        ),
    )

    source_payload = _expect_object(root["source"], "source")
    _expect_fields(source_payload, {"file", "line"}, "source")
    line = source_payload["line"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise ProposalInputError("source.line must be a positive integer")
    source = ProposalSource(
        file=_expect_text(source_payload["file"], "source.file"), line=line
    )
    return ContractProposalRequest(target=target, context=context, source=source)


def load_request_json(text: str) -> ContractProposalRequest:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProposalInputError(f"request is not valid JSON: {error.msg}") from error
    return load_request(_expect_object(payload, "request"))


def read_request(path: Path) -> ContractProposalRequest:
    try:
        return load_request_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProposalInputError(f"cannot read request {path}: {error}") from error


def request_id(request: ContractProposalRequest) -> str:
    digest = hashlib.sha256(_canonical_json(request.identity_dict()).encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def response_schema() -> dict[str, Any]:
    try:
        payload = json.loads(_pack_resource("response.schema.json"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("bundled response schema is unavailable or malformed") from error
    if not isinstance(payload, dict) or payload.get("$id") != RESPONSE_SCHEMA:
        raise RuntimeError("bundled response schema has the wrong identity")
    return payload


def build_prompt_pack(request: ContractProposalRequest) -> dict[str, Any]:
    logical_id = request_id(request)
    system_prompt = _pack_resource("system.md").rstrip("\n")
    user_payload = {
        "request": request.to_dict(),
        "request_id": logical_id,
    }
    user_prompt = (
        "Propose candidate contracts for the request below. Echo request_id "
        "exactly and return one JSON object matching response_schema.\n"
        + _canonical_json(user_payload)
    )
    return {
        "messages": [
            {"content": system_prompt, "role": "system"},
            {"content": user_prompt, "role": "user"},
        ],
        "request_id": logical_id,
        "response_schema": response_schema(),
        "schema": PROMPT_SCHEMA,
        "trust_boundary": {
            "accepted_intent": False,
            "generator": "untrusted",
            "machine_marker": _MACHINE_MARKER,
            "referee_required": True,
        },
    }


def render_prompt_pack(request: ContractProposalRequest) -> str:
    return json.dumps(
        build_prompt_pack(request), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"

_RESPONSE_COMMENT = re.compile(
    r"^// cs: ai (?:(?:requires|ensures|invariant) .+|modifies(?: .*)?)$"
)
_CONTRACT_COMMENT = re.compile(
    r"^// cs: (?P<ai>ai )?(?P<kind>requires|ensures|modifies|invariant)"
    r"(?: (?P<expression>.*))?$"
)
_CPP_SCALAR_TYPES = {
    "bool": "bool",
    "i32": "int",
    "i64": "long long",
    "u32": "unsigned int",
    "u64": "unsigned long long",
}
_STATUS_PRIORITY = {
    VerificationStatus.VIOLATED.value: 1,
    VerificationStatus.UNKNOWN.value: 2,
    VerificationStatus.UNSUPPORTED.value: 3,
    VerificationStatus.SOLVER_ERROR.value: 4,
}


@dataclass(frozen=True, slots=True)
class ProposalAnchor:
    kind: str
    body_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": self.kind}
        if self.body_line is not None:
            result["body_line"] = self.body_line
        return result


@dataclass(frozen=True, slots=True)
class CandidateContract:
    anchor: ProposalAnchor
    comment: str
    evidence: tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_dict(),
            "comment": self.comment,
            "evidence": list(self.evidence),
            "machine_proposed": True,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class ContractProposalResponse:
    request_id: str
    outcome: str
    proposals: tuple[CandidateContract, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes": list(self.notes),
            "outcome": self.outcome,
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "request_id": self.request_id,
            "schema": RESPONSE_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class PreScreenCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"message": self.message, "name": self.name, "status": self.status}


@dataclass(frozen=True, slots=True)
class PreScreenReport:
    request_id: str
    response_sha256: str
    outcome: str
    status: str
    reason: str
    checks: tuple[PreScreenCheck, ...]
    candidate_comments: tuple[str, ...] = ()
    overlay_sha256: str | None = None
    verification_summary: Mapping[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        summary = {status.value: 0 for status in VerificationStatus}
        summary.update(self.verification_summary or {})
        result: dict[str, Any] = {
            "candidate_comments": list(self.candidate_comments),
            "checks": [check.to_dict() for check in self.checks],
            "outcome": self.outcome,
            "reason": self.reason,
            "request_id": self.request_id,
            "response_sha256": self.response_sha256,
            "schema": PRE_SCREEN_SCHEMA,
            "status": self.status,
            "verification_summary": summary,
        }
        if self.overlay_sha256 is not None:
            result["overlay_sha256"] = self.overlay_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _expect_true(value: Any, label: str) -> None:
    if value is not True:
        raise ProposalInputError(f"{label} must be true")


def load_response(
    payload: Mapping[str, Any], expected_request_id: str
) -> ContractProposalResponse:
    root = _expect_object(payload, "response")
    _expect_fields(
        root,
        {"schema", "request_id", "outcome", "proposals", "notes"},
        "response",
    )
    if root["schema"] != RESPONSE_SCHEMA:
        raise ProposalInputError(
            f"unsupported response schema: expected {RESPONSE_SCHEMA!r}, "
            f"got {root['schema']!r}"
        )
    response_request_id = _expect_text(root["request_id"], "response.request_id")
    if response_request_id != expected_request_id:
        raise ProposalInputError("response.request_id does not match the logical request")
    outcome = _expect_text(root["outcome"], "response.outcome")
    if outcome not in {"candidate", "declined"}:
        raise ProposalInputError(f"response.outcome is unsupported: {outcome!r}")
    notes = _expect_text_list(root["notes"], "response.notes")
    raw_proposals = root["proposals"]
    if not isinstance(raw_proposals, list):
        raise ProposalInputError("response.proposals must be an array")
    if len(raw_proposals) > 16:
        raise ProposalInputError("response.proposals exceeds the 16-item limit")

    proposals: list[CandidateContract] = []
    for index, raw_proposal in enumerate(raw_proposals):
        label = f"response.proposals[{index}]"
        proposal = _expect_object(raw_proposal, label)
        _expect_fields(
            proposal,
            {"anchor", "comment", "evidence", "machine_proposed", "rationale"},
            label,
        )
        _expect_true(proposal["machine_proposed"], f"{label}.machine_proposed")
        comment = _expect_text(proposal["comment"], f"{label}.comment")
        if _RESPONSE_COMMENT.fullmatch(comment) is None:
            raise ProposalInputError(f"{label}.comment must retain the '// cs: ai' marker")
        match = _CONTRACT_COMMENT.fullmatch(comment)
        assert match is not None
        anchor_payload = _expect_object(proposal["anchor"], f"{label}.anchor")
        anchor_kind = anchor_payload.get("kind")
        if anchor_kind == "function":
            _expect_fields(anchor_payload, {"kind"}, f"{label}.anchor")
            body_line = None
        elif anchor_kind == "loop":
            _expect_fields(anchor_payload, {"kind", "body_line"}, f"{label}.anchor")
            body_line = anchor_payload["body_line"]
            if (
                isinstance(body_line, bool)
                or not isinstance(body_line, int)
                or body_line < 1
            ):
                raise ProposalInputError(f"{label}.anchor.body_line must be positive")
        else:
            raise ProposalInputError(f"{label}.anchor.kind is unsupported")
        is_invariant = match.group("kind") == "invariant"
        if is_invariant != (anchor_kind == "loop"):
            raise ProposalInputError(
                f"{label}.anchor must be loop exactly for invariant comments"
            )
        proposals.append(
            CandidateContract(
                anchor=ProposalAnchor(str(anchor_kind), body_line),
                comment=comment,
                evidence=_expect_text_list(proposal["evidence"], f"{label}.evidence"),
                rationale=_expect_text(proposal["rationale"], f"{label}.rationale"),
            )
        )

    if outcome == "candidate" and not proposals:
        raise ProposalInputError("candidate response must contain at least one proposal")
    if outcome == "declined" and proposals:
        raise ProposalInputError("declined response cannot contain proposals")
    canonical = sorted(
        proposals,
        key=lambda item: (
            item.anchor.kind,
            item.anchor.body_line or 0,
            item.comment,
            item.rationale,
            item.evidence,
        ),
    )
    keys = [_canonical_json(item.to_dict()) for item in canonical]
    if len(set(keys)) != len(keys):
        raise ProposalInputError("response.proposals contains duplicates")
    return ContractProposalResponse(
        request_id=response_request_id,
        outcome=outcome,
        proposals=tuple(canonical),
        notes=notes,
    )


def load_response_json(
    text: str, expected_request_id: str
) -> ContractProposalResponse:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProposalInputError(f"response is not valid JSON: {error.msg}") from error
    return load_response(_expect_object(payload, "response"), expected_request_id)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _contract_match(comment: str, label: str) -> re.Match[str]:
    match = _CONTRACT_COMMENT.fullmatch(comment)
    if match is None:
        raise ProposalInputError(f"{label} is not a supported cs: contract comment")
    kind = match.group("kind")
    expression = (match.group("expression") or "").strip()
    if kind != "modifies" and not expression:
        raise ProposalInputError(f"{label} has an empty {kind} expression")
    return match


def _definition_parts(request: ContractProposalRequest) -> tuple[str, list[str]]:
    signature = request.target.signature.strip().removesuffix(";").strip()
    if not signature or "{" in signature or "}" in signature:
        raise ProposalInputError("target.signature must not contain a function body")
    body_lines = request.target.body.splitlines()
    if not body_lines or body_lines[0].strip() != "{" or body_lines[-1].strip() != "}":
        raise ProposalInputError("target.body must start with '{' and end with '}'")
    return signature, body_lines


def candidate_overlay(
    request: ContractProposalRequest, response: ContractProposalResponse
) -> str:
    if response.outcome != "candidate":
        raise ProposalInputError("only candidate responses have a source overlay")
    signature, body_lines = _definition_parts(request)
    function_comments: list[str] = []
    for index, comment in enumerate(request.context.existing_contracts):
        match = _contract_match(comment, f"context.existing_contracts[{index}]")
        if match.group("kind") == "invariant":
            raise ProposalInputError("existing invariants must already be present in target.body")
        function_comments.append(comment)
    function_comments.extend(
        proposal.comment
        for proposal in response.proposals
        if proposal.anchor.kind == "function"
    )

    loop_comments: dict[int, list[str]] = {}
    for proposal in response.proposals:
        if proposal.anchor.kind != "loop":
            continue
        assert proposal.anchor.body_line is not None
        index = proposal.anchor.body_line - 1
        if index < 0 or index >= len(body_lines):
            raise ProposalInputError("loop anchor body_line is outside target.body")
        if re.match(r"\s*while\b", body_lines[index]) is None:
            raise ProposalInputError("loop anchor body_line must identify a while statement")
        loop_comments.setdefault(index, []).append(proposal.comment)

    rendered_body: list[str] = []
    for index, line in enumerate(body_lines):
        indentation = line[: len(line) - len(line.lstrip())]
        rendered_body.extend(
            indentation + comment for comment in sorted(loop_comments.get(index, ()))
        )
        rendered_body.append(line)
    lines = (
        *function_comments,
        f"{signature} {rendered_body[0]}",
        *rendered_body[1:],
    )
    return "\n".join(lines) + "\n"


def _candidate_declaration(
    request: ContractProposalRequest, response: ContractProposalResponse
) -> tuple[str, tuple[str, ...]]:
    signature, _ = _definition_parts(request)
    comments = tuple(
        proposal.comment
        for proposal in response.proposals
        if proposal.anchor.kind == "function"
    )
    return "\n".join((*comments, signature + ";")) + "\n", comments


def _machine_contract_texts(report: Any) -> tuple[str, ...]:
    texts: list[str] = []
    for function in report.module.functions:
        texts.extend(
            contract.text for contract in function.contracts if contract.machine_proposed
        )
        if function.frame is not None and function.frame.machine_proposed:
            texts.append(function.frame.text)
    return tuple(sorted(texts))


def _comment_contract_text(comment: str) -> str:
    match = _contract_match(comment, "candidate comment")
    expression = (match.group("expression") or "").strip()
    return f"{match.group('kind')} {expression}".rstrip()


def _consistency_probe(
    request: ContractProposalRequest, response: ContractProposalResponse
) -> str | None:
    logical_comments: list[str] = []
    for index, comment in enumerate(request.context.existing_contracts):
        match = _contract_match(comment, f"context.existing_contracts[{index}]")
        if match.group("kind") != "modifies":
            logical_comments.append(comment)
    for proposal in response.proposals:
        match = _contract_match(proposal.comment, "candidate comment")
        if match.group("kind") != "modifies":
            logical_comments.append(proposal.comment)
    if not logical_comments:
        return None

    parameters: list[str] = []
    name_map: dict[str, str] = {}
    used_names = {symbol.name for symbol in request.context.symbols}
    for symbol in request.context.symbols:
        cpp_type = _CPP_SCALAR_TYPES.get(symbol.type)
        if cpp_type is None:
            raise ProposalInputError(
                f"proposal consistency does not support symbol type {symbol.type!r}"
            )
        rendered_name = symbol.name
        if rendered_name == "result":
            rendered_name = "csk_proposal_result"
            while rendered_name in used_names:
                rendered_name += "_value"
        name_map[symbol.name] = rendered_name
        parameters.append(f"{cpp_type} {rendered_name}")

    requires: list[str] = []
    for comment in logical_comments:
        match = _contract_match(comment, "logical contract")
        expression = (match.group("expression") or "").strip()
        for source_name, rendered_name in sorted(
            name_map.items(), key=lambda item: (-len(item[0]), item[0])
        ):
            expression = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(source_name)}(?![A-Za-z0-9_])",
                rendered_name,
                expression,
            )
        requires.append(f"// cs: ai requires {expression}")
    signature = "bool csk_contract_proposal_consistency(" + ", ".join(parameters) + ");"
    return "\n".join((*sorted(requires), signature)) + "\n"


def _check_from_result(prefix: str, index: int, result: Any) -> PreScreenCheck:
    return PreScreenCheck(
        name=f"{prefix}/{result.kind}/{index}",
        status=result.status.value,
        message=result.message,
    )


def _malformed_report(
    request: ContractProposalRequest, response_text: str, reason: str
) -> PreScreenReport:
    return PreScreenReport(
        request_id=request_id(request),
        response_sha256=_sha256_text(response_text),
        outcome="rejected",
        status="malformed",
        reason=reason,
        checks=(PreScreenCheck("response", "malformed", reason),),
    )


def pre_screen_response(
    request: ContractProposalRequest,
    response_text: str,
    *,
    checker: CheckerBackend | None = None,
    clang: str | None = None,
) -> PreScreenReport:
    logical_request_id = request_id(request)
    try:
        response = load_response_json(response_text, logical_request_id)
    except ProposalInputError as error:
        return _malformed_report(request, response_text, str(error))

    canonical_response = _canonical_json(response.to_dict())
    response_hash = _sha256_text(canonical_response)
    if response.outcome == "declined":
        return PreScreenReport(
            request_id=logical_request_id,
            response_sha256=response_hash,
            outcome="declined",
            status="declined",
            reason="the untrusted generator declined to propose a contract",
            checks=(
                PreScreenCheck(
                    "response", "verified", "response schema and request identity match"
                ),
            ),
        )

    try:
        overlay = candidate_overlay(request, response)
        declaration, function_comments = _candidate_declaration(request, response)
        consistency_source = _consistency_probe(request, response)
    except ProposalInputError as error:
        return _malformed_report(request, response_text, str(error))

    selected_checker = checker or DeterministicChecker()
    checks: list[PreScreenCheck] = [
        PreScreenCheck(
            "response", "verified", "response schema and request identity match"
        )
    ]
    candidate_report = VerificationPipeline(
        clang, checker=selected_checker
    ).verify_source(declaration, "codeskeptic-proposal-candidate.cpp")
    expected_texts = tuple(sorted(_comment_contract_text(item) for item in function_comments))
    actual_texts = _machine_contract_texts(candidate_report)
    if expected_texts == actual_texts:
        checks.append(
            PreScreenCheck(
                "candidate_parse",
                "verified",
                "ordinary contract parser retained every function candidate",
            )
        )
    else:
        checks.append(
            PreScreenCheck(
                "candidate_parse",
                VerificationStatus.UNSUPPORTED.value,
                "ordinary contract parser did not retain every function candidate",
            )
        )
    checks.extend(
        _check_from_result("candidate_referee", index, result)
        for index, result in enumerate(candidate_report.results, 1)
    )

    if consistency_source is not None:
        consistency_report = VerificationPipeline(
            clang, checker=selected_checker
        ).verify_source(consistency_source, "codeskeptic-proposal-consistency.cpp")
        consistency_results = tuple(
            result
            for result in consistency_report.results
            if result.kind == "contract_consistency"
        )
        if consistency_results:
            checks.extend(
                _check_from_result("combined", index, result)
                for index, result in enumerate(consistency_results, 1)
            )
        else:
            failure = next(
                (
                    result
                    for result in consistency_report.results
                    if result.status != VerificationStatus.VERIFIED
                ),
                None,
            )
            checks.append(
                PreScreenCheck(
                    "combined/contract_consistency/1",
                    (
                        failure.status.value
                        if failure is not None
                        else VerificationStatus.UNSUPPORTED.value
                    ),
                    (
                        failure.message
                        if failure is not None
                        else "ordinary referee produced no consistency obligation"
                    ),
                )
            )

    overlay_report = VerificationPipeline(
        clang, checker=selected_checker
    ).verify_source(overlay, "codeskeptic-proposal-overlay.cpp")
    target_found = any(
        function.name == request.target.function for function in overlay_report.module.functions
    )
    if target_found:
        checks.append(
            PreScreenCheck(
                "source_parse", "verified", "target overlay parsed without source mutation"
            )
        )
    else:
        failure = next(iter(overlay_report.results), None)
        checks.append(
            PreScreenCheck(
                "source_parse",
                (
                    failure.status.value
                    if failure is not None
                    else VerificationStatus.SOLVER_ERROR.value
                ),
                (
                    failure.message
                    if failure is not None
                    else "ordinary frontend did not retain the target function"
                ),
            )
        )

    incomplete_overlay = tuple(
        result
        for result in overlay_report.results
        if result.status
        in {
            VerificationStatus.UNKNOWN,
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.SOLVER_ERROR,
        }
    )
    checks.extend(
        _check_from_result("overlay_referee", index, result)
        for index, result in enumerate(incomplete_overlay, 1)
    )

    invariant_candidates = tuple(
        proposal for proposal in response.proposals if proposal.anchor.kind == "loop"
    )
    if invariant_candidates:
        invariant_results = tuple(
            result
            for result in overlay_report.results
            if result.kind
            in {"loop_invariant_entry", "loop_invariant_preservation"}
        )
        if invariant_results:
            checks.extend(
                _check_from_result("invariant_referee", index, result)
                for index, result in enumerate(invariant_results, 1)
            )
        else:
            checks.append(
                PreScreenCheck(
                    "invariant_referee",
                    VerificationStatus.UNSUPPORTED.value,
                    "ordinary referee produced no invariant entry/preservation obligation",
                )
            )

    failures = [check for check in checks if check.status != "verified"]
    comments = tuple(proposal.comment for proposal in response.proposals)
    overlay_hash = _sha256_text(overlay)
    if not failures:
        return PreScreenReport(
            request_id=logical_request_id,
            response_sha256=response_hash,
            overlay_sha256=overlay_hash,
            outcome="eligible",
            status="eligible",
            reason="all deterministic proposal pre-screen checks passed",
            checks=tuple(checks),
            candidate_comments=comments,
            verification_summary=overlay_report.summary(),
        )

    selected = max(
        failures,
        key=lambda item: (_STATUS_PRIORITY.get(item.status, 5), item.name),
    )
    return PreScreenReport(
        request_id=logical_request_id,
        response_sha256=response_hash,
        overlay_sha256=overlay_hash,
        outcome="rejected",
        status=selected.status,
        reason=f"{selected.name}: {selected.message}",
        checks=tuple(checks),
        candidate_comments=comments,
        verification_summary=overlay_report.summary(),
    )