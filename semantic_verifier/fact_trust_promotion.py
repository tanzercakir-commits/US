"""One-parse referee-backed promotion of D1 pure fact claims."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping

from .backend import (
    CheckerBackend,
    CrossCheckBackend,
    Z3Checker,
)
from .checker import AffineChecker
from .fact_extractor import ClangFactExtractor
from .fact_trust import (
    FACT_TRUST_SCHEMA,
    REFEREE_IDS,
    FactTrustClaim,
    FactTrustIndex,
    ProofEvidence,
    verification_sha256,
)
from .facts import FactIndex, FactLocation, FactSymbol
from .frontend import FrontendUnit
from .lowering import SemanticLowerer
from .model import (
    FunctionIR,
    VerificationReport,
    VerificationStatus,
)
from .vc import VerificationConditionGenerator


PROMOTION_RUN_SCHEMA = "codeskeptic.fact-trust-promotion-run/v1"


class FactTrustPromotionError(RuntimeError):
    """Raised when the promotion pipeline cannot produce linked artifacts."""


@dataclass(frozen=True, slots=True)
class FactTrustPromotionResult:
    fact_index: FactIndex
    verification: VerificationReport
    trust: FactTrustIndex

    def __post_init__(self) -> None:
        self.trust.validate_against(self.fact_index)
        if self.verification.module.source != self.fact_index.source.file:
            raise FactTrustPromotionError(
                "verification and fact index use different display paths"
            )

    def summary(self) -> dict[str, object]:
        proved = sum(
            claim.trust == "proved"
            for claim in self.trust.claims
        )
        return {
            "derived": len(self.trust.claims) - proved,
            "proved": proved,
            "schema": PROMOTION_RUN_SCHEMA,
            "trust_id": self.trust.id,
        }

    def summary_json(self) -> str:
        return (
            json.dumps(
                self.summary(),
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    def artifacts(self) -> Mapping[str, bytes]:
        return {
            "fact-index.json": self.fact_index.to_json().encode("utf-8"),
            "fact-trust.json": self.trust.to_json().encode("utf-8"),
            "verification.json": self.verification.to_json().encode("utf-8"),
        }


class FactTrustPromotionPipeline:
    """Derive facts and verifier evidence from one parsed FrontendUnit."""

    def __init__(
        self,
        clang: str | None = None,
        *,
        checker: CheckerBackend | None = None,
        referee: str = "codeskeptic.affine/v1",
    ) -> None:
        selected = checker or AffineChecker()
        derived_referee = self._referee_for_checker(selected)
        if referee != derived_referee:
            raise FactTrustPromotionError(
                "referee ID does not match the exact checker implementation"
            )
        self.extractor = ClangFactExtractor(clang)
        self.checker = selected
        self.referee = derived_referee

    @staticmethod
    def _referee_for_checker(checker: CheckerBackend) -> str:
        exact = {
            AffineChecker: "codeskeptic.affine/v1",
            Z3Checker: "codeskeptic.z3/v1",
            CrossCheckBackend: "codeskeptic.both/v1",
        }
        referee = exact.get(type(checker))
        if referee is None or referee not in REFEREE_IDS:
            raise FactTrustPromotionError(
                "checker implementation is not an admitted proof referee"
            )
        return referee
    def promote_file(
        self,
        path: str | os.PathLike[str],
        *,
        display_path: str,
    ) -> FactTrustPromotionResult:
        unit = self.extractor.frontend.parse_file(
            path,
            display_path=display_path,
        )
        return self.promote_unit(unit)

    def promote_source(
        self,
        source: str,
        display_path: str = "input.cpp",
    ) -> FactTrustPromotionResult:
        unit = self.extractor.frontend.parse_source(
            source,
            display_path,
        )
        return self.promote_unit(unit)

    def promote_unit(
        self,
        unit: FrontendUnit,
    ) -> FactTrustPromotionResult:
        fact_index = self.extractor.extract_unit(unit)
        module = SemanticLowerer(unit).lower()
        obligations = VerificationConditionGenerator(module).generate()
        results = self.checker.check_all(obligations)
        report = VerificationReport(module, obligations, results)
        trust = self._promote(fact_index, report)
        return FactTrustPromotionResult(
            fact_index,
            report,
            trust,
        )

    def _promote(
        self,
        fact_index: FactIndex,
        report: VerificationReport,
    ) -> FactTrustIndex:
        report_bytes = report.to_json().encode("utf-8")
        report_hash = verification_sha256(report_bytes)
        purity = {
            row.function: row
            for row in fact_index.purity
        }
        functions = {
            symbol.id: symbol
            for symbol in fact_index.symbols
            if symbol.kind == "function"
        }
        direct_callees: dict[str, tuple[str, ...]] = {
            function: tuple(
                sorted(
                    {
                        call.callee
                        for call in fact_index.calls
                        if call.caller == function
                    }
                )
            )
            for function in purity
        }
        blocked_contexts = {
            limitation.context
            for limitation in fact_index.limitations
            if limitation.context is not None
        }
        module_blocked = bool(
            report.module.unsupported
            or any(
                limitation.context is None
                for limitation in fact_index.limitations
            )
        )
        matches = self._ir_matches(functions, report)
        eligible: dict[
            str,
            tuple[FunctionIR, tuple[str, ...]],
        ] = {}
        if not module_blocked:
            for function, row in purity.items():
                if row.status != "pure":
                    continue
                if function in blocked_contexts:
                    continue
                match = matches.get(function)
                if match is None:
                    continue
                obligation_ids = self._verified_obligations(
                    match,
                    report,
                )
                if obligation_ids is None:
                    continue
                if (
                    match.frame is None
                    or match.frame.targets
                    or match.frame.machine_proposed
                ):
                    continue
                eligible[function] = (match, obligation_ids)

        proved: set[str] = set()
        evidence: dict[str, ProofEvidence] = {}
        changed = True
        while changed:
            changed = False
            for function in sorted(eligible):
                if function in proved:
                    continue
                callees = direct_callees[function]
                if any(callee not in proved for callee in callees):
                    continue
                match, obligation_ids = eligible[function]
                assert match.frame is not None
                frame = match.frame.location
                evidence[function] = ProofEvidence(
                    fact_index.source.content_sha256,
                    report_hash,
                    report.module.schema,
                    self.referee,
                    obligation_ids,
                    FactLocation(
                        frame.file,
                        frame.line,
                        frame.column,
                    ),
                    callees,
                )
                proved.add(function)
                changed = True

        claims = tuple(
            FactTrustClaim.create(
                function=row.function,
                value=row.status,
                trust=(
                    "proved"
                    if row.function in proved
                    else "derived"
                ),
                evidence=evidence.get(row.function),
            )
            for row in fact_index.purity
        )
        return FactTrustIndex.create(fact_index, claims)

    @staticmethod
    def _ir_matches(
        functions: Mapping[str, FactSymbol],
        report: VerificationReport,
    ) -> dict[str, FunctionIR]:
        definitions = [
            function
            for function in report.module.functions
            if function.has_body
        ]
        name_counts: dict[str, int] = {}
        for function in definitions:
            name_counts[function.name] = (
                name_counts.get(function.name, 0) + 1
            )
        result: dict[str, FunctionIR] = {}
        for identity, symbol in functions.items():
            location = symbol.definition
            if location is None:
                continue
            candidates = [
                function
                for function in definitions
                if function.name == symbol.name
                and function.location.file == location.file
                and function.location.line == location.line
                and function.location.column == location.column
            ]
            if (
                len(candidates) == 1
                and name_counts[candidates[0].name] == 1
            ):
                result[identity] = candidates[0]
        return result

    @staticmethod
    def _verified_obligations(
        function: FunctionIR,
        report: VerificationReport,
    ) -> tuple[str, ...] | None:
        obligations = tuple(
            obligation
            for obligation in report.obligations
            if obligation.function == function.name
        )
        if not obligations:
            return None
        obligation_ids = tuple(
            obligation.id for obligation in obligations
        )
        results = tuple(
            result
            for result in report.results
            if result.function == function.name
        )
        result_ids = tuple(
            result.obligation_id for result in results
        )
        if (
            len(result_ids) != len(set(result_ids))
            or set(result_ids) != set(obligation_ids)
            or len(results) != len(obligations)
            or any(
                result.status != VerificationStatus.VERIFIED
                for result in results
            )
        ):
            return None
        return tuple(sorted(obligation_ids))


def write_promotion_artifacts(
    result: FactTrustPromotionResult,
    output_dir: str | os.PathLike[str],
    *,
    check: bool = False,
) -> tuple[str, ...]:
    """Write linked artifacts atomically or return sorted check mismatches."""

    root = Path(output_dir)
    expected = dict(result.artifacts())
    expected["promotion-run.json"] = result.summary_json().encode("utf-8")
    mismatches: list[str] = []
    for name, data in sorted(expected.items()):
        path = root / name
        if check:
            try:
                actual = path.read_bytes()
            except OSError as error:
                mismatches.append(f"{name}: {error}")
            else:
                if actual != data:
                    mismatches.append(f"{name}: content differs")
            continue
        _atomic_write(path, data)
    if check and root.exists():
        expected_names = set(expected)
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if path.is_file() and path.name not in expected_names:
                mismatches.append(
                    f"{path.name}: stale undeclared artifact"
                )
    return tuple(sorted(mismatches))


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
