"""Owned adapter seam for source-level contract surfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from .contracts import (
    ContractIssue,
    contracts_before,
    contracts_from_cpp26,
    invariants_before,
)
from .cpp26_contracts import Cpp26FunctionContract
from .locations import LineMap
from .model import Contract, FrameContract


@dataclass(frozen=True, slots=True)
class FunctionContractSurfaceRequest:
    source: str
    declaration_offset: int
    line_map: LineMap
    parameter_types: Mapping[str, str]
    return_type: str
    parameter_modes: Mapping[str, str]
    native_contracts: tuple[Cpp26FunctionContract, ...] = ()
    const_value_parameters: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class LoopContractSurfaceRequest:
    source: str
    statement_offset: int
    line_map: LineMap
    symbol_types: Mapping[str, str]
    statement_kind: str


@dataclass(frozen=True, slots=True)
class ContractSurfaceResult:
    contracts: tuple[Contract, ...]
    frame: FrameContract | None
    issues: tuple[ContractIssue, ...]
    consumed_lines: tuple[int, ...]
    consumed_native_offsets: tuple[int, ...]

    @classmethod
    def empty(cls) -> "ContractSurfaceResult":
        return cls((), None, (), (), ())


class ContractSurfaceAdapter(ABC):
    """Collect one source syntax into owned contracts without judging it."""

    @property
    @abstractmethod
    def surface_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def collect_function(
        self, request: FunctionContractSurfaceRequest
    ) -> ContractSurfaceResult:
        raise NotImplementedError

    @abstractmethod
    def collect_loop(
        self, request: LoopContractSurfaceRequest
    ) -> ContractSurfaceResult:
        raise NotImplementedError


def _legacy_result(
    contracts: tuple[Contract, ...],
    frame: FrameContract | None,
    issues: tuple[ContractIssue, ...],
) -> ContractSurfaceResult:
    lines = {contract.location.line for contract in contracts}
    lines.update(issue.location.line for issue in issues)
    if frame is not None:
        lines.add(frame.location.line)
    return ContractSurfaceResult(
        contracts,
        frame,
        issues,
        tuple(sorted(lines)),
        (),
    )


class LegacyCsContractSurfaceAdapter(ContractSurfaceAdapter):
    @property
    def surface_id(self) -> str:
        return "legacy-cs"

    def collect_function(
        self, request: FunctionContractSurfaceRequest
    ) -> ContractSurfaceResult:
        contracts, frame, issues = contracts_before(
            request.source,
            request.declaration_offset,
            request.line_map,
            request.parameter_types,
            request.return_type,
            request.parameter_modes,
        )
        return _legacy_result(contracts, frame, issues)

    def collect_loop(
        self, request: LoopContractSurfaceRequest
    ) -> ContractSurfaceResult:
        invariants, issues = invariants_before(
            request.source,
            request.statement_offset,
            request.line_map,
            request.symbol_types,
            request.statement_kind,
        )
        return _legacy_result(invariants, None, issues)


class Cpp26ContractSurfaceAdapter(ContractSurfaceAdapter):
    @property
    def surface_id(self) -> str:
        return "cpp26"

    def collect_function(
        self, request: FunctionContractSurfaceRequest
    ) -> ContractSurfaceResult:
        contracts, issues = contracts_from_cpp26(
            request.native_contracts,
            request.line_map,
            request.parameter_types,
            request.return_type,
            request.parameter_modes,
            request.const_value_parameters,
        )
        return ContractSurfaceResult(
            contracts,
            None,
            issues,
            (),
            tuple(spec.offset for spec in request.native_contracts),
        )

    def collect_loop(
        self, request: LoopContractSurfaceRequest
    ) -> ContractSurfaceResult:
        del request
        return ContractSurfaceResult.empty()


LEGACY_CS_CONTRACT_SURFACE = LegacyCsContractSurfaceAdapter()
CPP26_CONTRACT_SURFACE = Cpp26ContractSurfaceAdapter()
