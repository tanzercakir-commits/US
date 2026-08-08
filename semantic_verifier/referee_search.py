"""Exhaustive referee-guided patch search over a frozen candidate set."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import gcd
import hashlib
import json
import re
from typing import Any

from .checker import AffineChecker
from .experiment_corpus import ExperimentCorpus
from .model import VerificationStatus
from .pipeline import VerificationPipeline
from .repair_loop import LineEdit, PatchProposal, apply_line_edit


CANDIDATE_SET_SCHEMA = "codeskeptic.referee-search-candidates/v1"
SEARCH_REPORT_SCHEMA = "codeskeptic.referee-search-report/v1"
SEARCH_IDENTITY_SCHEMA = "codeskeptic.referee-search-identity/v1"
PROVENANCE = "recorded-oracle-seeded-scripted-proxy"
CASE_COUNT = 20
CANDIDATES_PER_CASE = 4
TOTAL_EVALUATIONS = CASE_COUNT * CANDIDATES_PER_CASE
UPLIFT_THRESHOLD = (2, 5)
LIMITATIONS = (
    "The candidates are an oracle-seeded recorded scripted proxy, not model output.",
    "The result does not establish model-proposer or general model behavior.",
    "The calibration does not establish consciousness, causality, or model search uplift.",
)
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASE_RE = re.compile(r"e2-case-(0[1-9]|1[0-9]|20)\Z")


class RefereeSearchError(ValueError):
    """Raised when a search artifact or evaluation fails closed."""


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


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    try:
        return _sha256_bytes(value.encode("utf-8"))
    except UnicodeError as error:
        raise RefereeSearchError("search text must be UTF-8") from error


def _content_id(kind: str, value: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        _identity_bytes(
            {
                "kind": kind,
                "schema": SEARCH_IDENTITY_SCHEMA,
                "value": value,
            }
        )
    )


def _require_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise RefereeSearchError(f"{field} must be a lowercase sha256 identity")
    return value


def _require_case(value: object, field: str) -> str:
    if not isinstance(value, str) or _CASE_RE.fullmatch(value) is None:
        raise RefereeSearchError(f"{field} is unsupported")
    return value


def _require_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RefereeSearchError(f"{field} must be an integer >= {minimum}")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise RefereeSearchError(f"{field} is missing fields: {', '.join(missing)}")
    if unknown:
        raise RefereeSearchError(f"{field} has unknown fields: {', '.join(unknown)}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RefereeSearchError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RefereeSearchError(f"non-finite JSON number {value!r} is not allowed")


def _parse_json(text: str, field: str) -> Mapping[str, Any]:
    if text.startswith("\ufeff") or "\x00" in text or "\r" in text:
        raise RefereeSearchError(f"{field} must be BOM-free LF-only UTF-8")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise RefereeSearchError(f"invalid {field} JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise RefereeSearchError(f"{field} must be an object")
    return value


def _fraction(numerator: int, denominator: int) -> dict[str, int]:
    if denominator <= 0:
        raise RefereeSearchError("fraction denominator must be positive")
    divisor = gcd(numerator, denominator)
    return {
        "denominator": denominator // divisor,
        "numerator": numerator // divisor,
    }


def _parse_fraction(value: object, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise RefereeSearchError(f"{field} must be an object")
    _exact_keys(value, {"denominator", "numerator"}, field)
    numerator = _require_int(value["numerator"], f"{field}.numerator")
    denominator = _require_int(
        value["denominator"], f"{field}.denominator", minimum=1
    )
    reduced = _fraction(numerator, denominator)
    if dict(value) != reduced:
        raise RefereeSearchError(f"{field} must be a reduced non-negative fraction")
    return reduced


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    rank: int
    proposal: PatchProposal

    def __post_init__(self) -> None:
        if not 1 <= _require_int(self.rank, "candidate.rank", minimum=1) <= CANDIDATES_PER_CASE:
            raise RefereeSearchError("candidate.rank is outside the fixed N")
        if not isinstance(self.proposal, PatchProposal):
            raise RefereeSearchError("candidate.proposal must be a PatchProposal")

    def to_dict(self) -> dict[str, object]:
        return {"proposal": self.proposal.to_dict(), "rank": self.rank}


@dataclass(frozen=True, slots=True)
class SearchCase:
    case: str
    candidates: tuple[RankedCandidate, ...]

    def __post_init__(self) -> None:
        _require_case(self.case, "search case")
        candidates = tuple(self.candidates)
        if tuple(item.rank for item in candidates) != (1, 2, 3, 4):
            raise RefereeSearchError("search case ranks must be exactly 1..4")
        identities = [item.proposal.id for item in candidates]
        if len(identities) != len(set(identities)):
            raise RefereeSearchError("search case proposal identities duplicate")
        object.__setattr__(self, "candidates", candidates)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "case": self.case,
        }


@dataclass(frozen=True, slots=True)
class CandidateSet:
    id: str
    corpus: str
    n: int
    provenance: str
    cases: tuple[SearchCase, ...]

    def __post_init__(self) -> None:
        _require_hash(self.corpus, "candidate set corpus")
        if self.n != CANDIDATES_PER_CASE:
            raise RefereeSearchError("candidate set N must be four")
        if self.provenance != PROVENANCE:
            raise RefereeSearchError("candidate set provenance is unsupported")
        cases = tuple(self.cases)
        expected = tuple(f"e2-case-{index:02d}" for index in range(1, 21))
        if tuple(item.case for item in cases) != expected:
            raise RefereeSearchError("candidate set cases must be the complete sorted corpus")
        identities = [
            candidate.proposal.id
            for item in cases
            for candidate in item.candidates
        ]
        if len(identities) != TOTAL_EVALUATIONS or len(identities) != len(set(identities)):
            raise RefereeSearchError("candidate set must have eighty unique proposals")
        object.__setattr__(self, "cases", cases)
        expected_id = _content_id("referee-search-candidates", self.content_dict())
        if _require_hash(self.id, "candidate set id") != expected_id:
            raise RefereeSearchError("candidate set identity is stale")

    @classmethod
    def create(cls, *, corpus: str, cases: Sequence[SearchCase]) -> "CandidateSet":
        ordered = tuple(cases)
        content = {
            "cases": [item.to_dict() for item in ordered],
            "corpus": corpus,
            "n": CANDIDATES_PER_CASE,
            "provenance": PROVENANCE,
            "schema": CANDIDATE_SET_SCHEMA,
        }
        return cls(
            _content_id("referee-search-candidates", content),
            corpus,
            CANDIDATES_PER_CASE,
            PROVENANCE,
            ordered,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "cases": [item.to_dict() for item in self.cases],
            "corpus": self.corpus,
            "n": self.n,
            "provenance": self.provenance,
            "schema": CANDIDATE_SET_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, order=True, slots=True)
class EvaluationResult:
    obligation: str
    kind: str
    status: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.obligation, "evaluation obligation"),
            (self.kind, "evaluation kind"),
        ):
            if not isinstance(value, str) or not value or "\x00" in value:
                raise RefereeSearchError(f"{field} must be non-empty text")
        admitted = {item.value for item in VerificationStatus}
        if self.status not in admitted:
            raise RefereeSearchError("evaluation result status is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "obligation": self.obligation,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    rank: int
    proposal: str
    candidate_source_sha256: str
    verification_sha256: str
    results: tuple[EvaluationResult, ...]
    status: str

    def __post_init__(self) -> None:
        if not 1 <= _require_int(self.rank, "evaluation rank", minimum=1) <= 4:
            raise RefereeSearchError("evaluation rank is outside the fixed N")
        _require_hash(self.proposal, "evaluation proposal")
        _require_hash(self.candidate_source_sha256, "candidate source hash")
        _require_hash(self.verification_sha256, "verification hash")
        results = tuple(sorted(self.results))
        if not results or len(results) != len(set(results)):
            raise RefereeSearchError("evaluation results must be non-empty and unique")
        statuses = {item.status for item in results}
        expected = (
            "verified"
            if statuses == {VerificationStatus.VERIFIED.value}
            else "violated"
            if VerificationStatus.VIOLATED.value in statuses
            else "blocked"
        )
        if self.status != expected:
            raise RefereeSearchError("evaluation aggregate status is inconsistent")
        object.__setattr__(self, "results", results)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_source_sha256": self.candidate_source_sha256,
            "proposal": self.proposal,
            "rank": self.rank,
            "results": [item.to_dict() for item in self.results],
            "status": self.status,
            "verification_sha256": self.verification_sha256,
        }


@dataclass(frozen=True, slots=True)
class SearchCaseResult:
    case: str
    evaluations: tuple[CandidateEvaluation, ...]
    selected_rank: int | None
    selected_proposal: str | None
    single_shot_verified: bool

    def __post_init__(self) -> None:
        _require_case(self.case, "search result case")
        evaluations = tuple(self.evaluations)
        if tuple(item.rank for item in evaluations) != (1, 2, 3, 4):
            raise RefereeSearchError("search result must retain all four ranks")
        passing = [item for item in evaluations if item.status == "verified"]
        expected_rank = passing[0].rank if passing else None
        expected_proposal = passing[0].proposal if passing else None
        if (self.selected_rank, self.selected_proposal) != (
            expected_rank,
            expected_proposal,
        ):
            raise RefereeSearchError("selected candidate is not lowest-rank verified")
        if self.single_shot_verified is not (evaluations[0].status == "verified"):
            raise RefereeSearchError("single-shot result does not match rank one")
        object.__setattr__(self, "evaluations", evaluations)

    def to_dict(self) -> dict[str, object]:
        return {
            "case": self.case,
            "evaluations": [item.to_dict() for item in self.evaluations],
            "selected": (
                {
                    "proposal": self.selected_proposal,
                    "rank": self.selected_rank,
                }
                if self.selected_rank is not None
                else None
            ),
            "single_shot_verified": self.single_shot_verified,
        }


@dataclass(frozen=True, slots=True)
class SearchReport:
    id: str
    candidates: str
    corpus: str
    n: int
    provenance: str
    cases: tuple[SearchCaseResult, ...]

    def __post_init__(self) -> None:
        _require_hash(self.candidates, "report candidates")
        _require_hash(self.corpus, "report corpus")
        if self.n != 4 or self.provenance != PROVENANCE:
            raise RefereeSearchError("report protocol metadata is unsupported")
        cases = tuple(self.cases)
        expected = tuple(f"e2-case-{index:02d}" for index in range(1, 21))
        if tuple(item.case for item in cases) != expected:
            raise RefereeSearchError("report cases must be complete and sorted")
        object.__setattr__(self, "cases", cases)
        expected_id = _content_id("referee-search-report", self.content_dict())
        if _require_hash(self.id, "report id") != expected_id:
            raise RefereeSearchError("report identity is stale")

    @classmethod
    def create(
        cls,
        *,
        candidates: str,
        corpus: str,
        cases: Sequence[SearchCaseResult],
    ) -> "SearchReport":
        rows = tuple(cases)
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "id", "sha256:" + "0" * 64)
        object.__setattr__(provisional, "candidates", candidates)
        object.__setattr__(provisional, "corpus", corpus)
        object.__setattr__(provisional, "n", 4)
        object.__setattr__(provisional, "provenance", PROVENANCE)
        object.__setattr__(provisional, "cases", rows)
        content = provisional.content_dict()
        return cls(
            _content_id("referee-search-report", content),
            candidates,
            corpus,
            4,
            PROVENANCE,
            rows,
        )

    def _metrics(self) -> dict[str, object]:
        total = len(self.cases)
        single = sum(item.single_shot_verified for item in self.cases)
        best = sum(item.selected_rank is not None for item in self.cases)
        uplift_numerator = best - single
        threshold_numerator, threshold_denominator = UPLIFT_THRESHOLD
        outcome = (
            "passed"
            if uplift_numerator * threshold_denominator
            >= threshold_numerator * total
            else "failed"
        )
        return {
            "arms": {
                "best_of_n": {
                    "rate": _fraction(best, total),
                    "successes": best,
                    "total": total,
                },
                "single_shot": {
                    "rate": _fraction(single, total),
                    "successes": single,
                    "total": total,
                },
            },
            "outcome": outcome,
            "threshold": _fraction(*UPLIFT_THRESHOLD),
            "uplift": _fraction(uplift_numerator, total),
        }

    def content_dict(self) -> dict[str, object]:
        metrics = self._metrics()
        return {
            "arms": metrics["arms"],
            "candidates": self.candidates,
            "cases": [item.to_dict() for item in self.cases],
            "corpus": self.corpus,
            "evaluated": sum(len(item.evaluations) for item in self.cases),
            "limitations": list(LIMITATIONS),
            "n": self.n,
            "outcome": metrics["outcome"],
            "provenance": self.provenance,
            "schema": SEARCH_REPORT_SCHEMA,
            "threshold": metrics["threshold"],
            "uplift": metrics["uplift"],
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _proposal_from_json(value: object, field: str) -> PatchProposal:
    if not isinstance(value, Mapping):
        raise RefereeSearchError(f"{field} must be an object")
    _exact_keys(
        value,
        {"base_source_sha256", "edit", "id", "schema"},
        field,
    )
    if value["schema"] != "codeskeptic.patch-proposal/v1":
        raise RefereeSearchError(f"{field}.schema is unsupported")
    edit = value["edit"]
    if not isinstance(edit, Mapping):
        raise RefereeSearchError(f"{field}.edit must be an object")
    _exact_keys(edit, {"end_line", "replacement", "start_line"}, f"{field}.edit")
    replacement = edit["replacement"]
    if not isinstance(replacement, list):
        raise RefereeSearchError(f"{field}.edit.replacement must be an array")
    try:
        proposal = PatchProposal.create(
            base_source_sha256=value["base_source_sha256"],
            edit=LineEdit(
                edit["start_line"],
                edit["end_line"],
                tuple(replacement),
            ),
        )
    except (TypeError, ValueError) as error:
        raise RefereeSearchError(f"invalid {field}: {error}") from error
    if proposal.id != value["id"]:
        raise RefereeSearchError(f"{field} identity is stale")
    return proposal


def _validate_candidate_set(candidates: CandidateSet, corpus: ExperimentCorpus) -> None:
    if candidates.corpus != corpus.id:
        raise RefereeSearchError("candidate set does not link the supplied corpus")
    by_case = {case.id: case for case in corpus.cases}
    for row in candidates.cases:
        case = by_case[row.case]
        for ranked in row.candidates:
            proposal = ranked.proposal
            if proposal.base_source_sha256 != case.source_sha256:
                raise RefereeSearchError(f"candidate source link is stale for {row.case}")
            targeted = case.source_text.splitlines()[
                proposal.edit.start_line - 1 : proposal.edit.end_line
            ]
            if any(re.match(r"^\s*//\s*cs:", line) for line in targeted):
                raise RefereeSearchError(f"candidate edits a contract for {row.case}")
            try:
                changed = apply_line_edit(case.source_text, proposal.edit)
            except ValueError as error:
                raise RefereeSearchError(f"invalid candidate edit for {row.case}: {error}") from error
            if changed == case.source_text:
                raise RefereeSearchError(f"candidate is a no-op for {row.case}")
            before = [
                line
                for line in case.source_text.splitlines()
                if re.match(r"^\s*//\s*cs:", line)
            ]
            after = [
                line
                for line in changed.splitlines()
                if re.match(r"^\s*//\s*cs:", line)
            ]
            if before != after:
                raise RefereeSearchError(f"candidate changes contracts for {row.case}")


def build_frozen_candidate_set(corpus: ExperimentCorpus) -> CandidateSet:
    """Build the explicitly oracle-seeded scripted calibration candidates."""

    correct_rank = {
        **{index: 1 for index in range(1, 5)},
        **{index: 2 for index in range(5, 10)},
        **{index: 3 for index in range(10, 15)},
        **{index: 4 for index in range(15, 19)},
    }
    cases: list[SearchCase] = []
    for index, case in enumerate(corpus.cases, 1):
        ranked: list[RankedCandidate] = []
        for rank in range(1, 5):
            replacement = (
                case.oracle_replacement
                if correct_rank.get(index) == rank
                else f"  return value * {100 + index * 4 + rank};"
            )
            proposal = PatchProposal.create(
                base_source_sha256=case.source_sha256,
                edit=LineEdit(
                    case.oracle_line,
                    case.oracle_line,
                    (replacement,),
                ),
            )
            ranked.append(RankedCandidate(rank, proposal))
        cases.append(SearchCase(case.id, tuple(ranked)))
    result = CandidateSet.create(corpus=corpus.id, cases=cases)
    _validate_candidate_set(result, corpus)
    return result


def load_candidate_set_json(text: str, corpus: ExperimentCorpus) -> CandidateSet:
    payload = _parse_json(text, "candidate set")
    _exact_keys(payload, {"cases", "corpus", "id", "n", "provenance", "schema"}, "candidate set")
    if payload["schema"] != CANDIDATE_SET_SCHEMA:
        raise RefereeSearchError("candidate set schema is unsupported")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise RefereeSearchError("candidate set cases must be an array")
    cases: list[SearchCase] = []
    for case_index, raw_case in enumerate(raw_cases):
        field = f"candidate set cases[{case_index}]"
        if not isinstance(raw_case, Mapping):
            raise RefereeSearchError(f"{field} must be an object")
        _exact_keys(raw_case, {"candidates", "case"}, field)
        raw_candidates = raw_case["candidates"]
        if not isinstance(raw_candidates, list):
            raise RefereeSearchError(f"{field}.candidates must be an array")
        ranked: list[RankedCandidate] = []
        for rank_index, raw_ranked in enumerate(raw_candidates):
            ranked_field = f"{field}.candidates[{rank_index}]"
            if not isinstance(raw_ranked, Mapping):
                raise RefereeSearchError(f"{ranked_field} must be an object")
            _exact_keys(raw_ranked, {"proposal", "rank"}, ranked_field)
            ranked.append(
                RankedCandidate(
                    raw_ranked["rank"],
                    _proposal_from_json(raw_ranked["proposal"], f"{ranked_field}.proposal"),
                )
            )
        cases.append(SearchCase(raw_case["case"], tuple(ranked)))
    candidate_set = CandidateSet.create(corpus=payload["corpus"], cases=cases)
    if payload["id"] != candidate_set.id:
        raise RefereeSearchError("candidate set identity is stale")
    if payload["n"] != candidate_set.n or payload["provenance"] != candidate_set.provenance:
        raise RefereeSearchError("candidate set protocol metadata is stale")
    if candidate_set.to_json() != text:
        raise RefereeSearchError("candidate set JSON is not canonical")
    _validate_candidate_set(candidate_set, corpus)
    return candidate_set


def evaluate_candidate_set(
    corpus: ExperimentCorpus,
    candidates: CandidateSet,
) -> SearchReport:
    _validate_candidate_set(candidates, corpus)
    by_case = {case.id: case for case in corpus.cases}
    combined: list[str] = []
    prepared: dict[tuple[str, int], tuple[str, str, str]] = {}
    for row in candidates.cases:
        case = by_case[row.case]
        for ranked in row.candidates:
            candidate = apply_line_edit(case.source_text, ranked.proposal.edit)
            function = f"e4_{row.case.replace('-', '_')}_r{ranked.rank}"
            signature = f"int {case.function}("
            if candidate.count(signature) != 1:
                raise RefereeSearchError(f"candidate function is ambiguous for {row.case}")
            renamed = candidate.replace(signature, f"int {function}(", 1)
            combined.append(renamed.rstrip("\n"))
            prepared[(row.case, ranked.rank)] = (
                candidate,
                function,
                ranked.proposal.id,
            )
    if len(combined) != TOTAL_EVALUATIONS:
        raise RefereeSearchError("candidate preparation omitted evaluations")
    pipeline = VerificationPipeline(checker=AffineChecker())
    verification = pipeline.verify_source(
        "\n".join(combined) + "\n",
        "benchmarks/referee_search/combined.cpp",
    )
    if verification.module.unsupported:
        raise RefereeSearchError(
            "candidate batch has unsupported lowering: "
            + "; ".join(node.reason for node in verification.module.unsupported)
        )
    expected_functions = {value[1] for value in prepared.values()}
    actual_functions = {
        function.name for function in verification.module.functions if function.has_body
    }
    if actual_functions != expected_functions:
        raise RefereeSearchError("candidate batch function set differs")
    case_results: list[SearchCaseResult] = []
    for row in candidates.cases:
        evaluations: list[CandidateEvaluation] = []
        for ranked in row.candidates:
            candidate, function, proposal_id = prepared[(row.case, ranked.rank)]
            target = [result for result in verification.results if result.function == function]
            if not target:
                raise RefereeSearchError(f"candidate has no referee results for {row.case}")
            results = tuple(
                sorted(
                    EvaluationResult(
                        result.obligation_id,
                        result.kind,
                        result.status.value,
                    )
                    for result in target
                )
            )
            statuses = {item.status for item in results}
            aggregate = (
                "verified"
                if statuses == {VerificationStatus.VERIFIED.value}
                else "violated"
                if VerificationStatus.VIOLATED.value in statuses
                else "blocked"
            )
            evidence = {
                "candidate_source_sha256": _sha256_text(candidate),
                "function": function,
                "results": [result.to_dict() for result in target],
            }
            evaluations.append(
                CandidateEvaluation(
                    ranked.rank,
                    proposal_id,
                    _sha256_text(candidate),
                    _sha256_bytes(_identity_bytes(evidence)),
                    results,
                    aggregate,
                )
            )
        passing = [item for item in evaluations if item.status == "verified"]
        case_results.append(
            SearchCaseResult(
                row.case,
                tuple(evaluations),
                passing[0].rank if passing else None,
                passing[0].proposal if passing else None,
                evaluations[0].status == "verified",
            )
        )
    return SearchReport.create(
        candidates=candidates.id,
        corpus=corpus.id,
        cases=case_results,
    )


def _evaluation_from_json(value: object, field: str) -> CandidateEvaluation:
    if not isinstance(value, Mapping):
        raise RefereeSearchError(f"{field} must be an object")
    _exact_keys(
        value,
        {
            "candidate_source_sha256",
            "proposal",
            "rank",
            "results",
            "status",
            "verification_sha256",
        },
        field,
    )
    raw_results = value["results"]
    if not isinstance(raw_results, list):
        raise RefereeSearchError(f"{field}.results must be an array")
    results: list[EvaluationResult] = []
    for index, raw in enumerate(raw_results):
        result_field = f"{field}.results[{index}]"
        if not isinstance(raw, Mapping):
            raise RefereeSearchError(f"{result_field} must be an object")
        _exact_keys(raw, {"kind", "obligation", "status"}, result_field)
        results.append(EvaluationResult(raw["obligation"], raw["kind"], raw["status"]))
    return CandidateEvaluation(
        value["rank"],
        value["proposal"],
        value["candidate_source_sha256"],
        value["verification_sha256"],
        tuple(results),
        value["status"],
    )


def load_search_report_json(text: str, candidates: CandidateSet) -> SearchReport:
    payload = _parse_json(text, "search report")
    expected_keys = {
        "arms",
        "candidates",
        "cases",
        "corpus",
        "evaluated",
        "id",
        "limitations",
        "n",
        "outcome",
        "provenance",
        "schema",
        "threshold",
        "uplift",
    }
    _exact_keys(payload, expected_keys, "search report")
    if payload["schema"] != SEARCH_REPORT_SCHEMA:
        raise RefereeSearchError("search report schema is unsupported")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise RefereeSearchError("search report cases must be an array")
    cases: list[SearchCaseResult] = []
    for case_index, raw_case in enumerate(raw_cases):
        field = f"search report cases[{case_index}]"
        if not isinstance(raw_case, Mapping):
            raise RefereeSearchError(f"{field} must be an object")
        _exact_keys(raw_case, {"case", "evaluations", "selected", "single_shot_verified"}, field)
        raw_evaluations = raw_case["evaluations"]
        if not isinstance(raw_evaluations, list):
            raise RefereeSearchError(f"{field}.evaluations must be an array")
        evaluations = tuple(
            _evaluation_from_json(item, f"{field}.evaluations[{index}]")
            for index, item in enumerate(raw_evaluations)
        )
        selected = raw_case["selected"]
        if selected is None:
            selected_rank = None
            selected_proposal = None
        else:
            if not isinstance(selected, Mapping):
                raise RefereeSearchError(f"{field}.selected must be an object or null")
            _exact_keys(selected, {"proposal", "rank"}, f"{field}.selected")
            selected_rank = selected["rank"]
            selected_proposal = selected["proposal"]
        if not isinstance(raw_case["single_shot_verified"], bool):
            raise RefereeSearchError(f"{field}.single_shot_verified must be boolean")
        cases.append(
            SearchCaseResult(
                raw_case["case"],
                evaluations,
                selected_rank,
                selected_proposal,
                raw_case["single_shot_verified"],
            )
        )
    report = SearchReport.create(
        candidates=payload["candidates"],
        corpus=payload["corpus"],
        cases=cases,
    )
    if report.candidates != candidates.id or report.corpus != candidates.corpus:
        raise RefereeSearchError("search report linkage is stale")
    for candidate_row, result_row in zip(candidates.cases, report.cases):
        expected = [
            (item.rank, item.proposal.id) for item in candidate_row.candidates
        ]
        actual = [
            (item.rank, item.proposal) for item in result_row.evaluations
        ]
        if actual != expected:
            raise RefereeSearchError(
                f"search report proposal linkage is stale for {result_row.case}"
            )
    if payload["id"] != report.id:
        raise RefereeSearchError("search report identity is stale")
    if payload["n"] != report.n or payload["provenance"] != report.provenance:
        raise RefereeSearchError("search report protocol metadata is stale")
    if payload["evaluated"] != TOTAL_EVALUATIONS:
        raise RefereeSearchError("search report did not evaluate all candidates")
    if payload["limitations"] != list(LIMITATIONS):
        raise RefereeSearchError("search report limitations are stale")
    _parse_fraction(payload["threshold"], "search report threshold")
    _parse_fraction(payload["uplift"], "search report uplift")
    if report.to_json() != text:
        raise RefereeSearchError("search report JSON is not canonical or is inconsistent")
    return report
