"""Verification-condition generation from the Semantic IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .integer_types import (
    integer_type,
    is_fixed_integer_type,
    is_signed_integer_type,
)
from .model import (
    Contract,
    Expr,
    FunctionIR,
    IRNode,
    ModuleIR,
    Obligation,
    SourceLocation,
    TraceTemplate,
)
from .query_fragment import QueryFragment, classify_expressions


def _binary(op: str, left: Expr, right: Expr) -> Expr:
    return Expr.binary(op, left, right)


def _and(left: Expr, right: Expr) -> Expr:
    return Expr.binary("&&", left, right, "bool")


def _or(left: Expr, right: Expr) -> Expr:
    return Expr.binary("||", left, right, "bool")


def _not(value: Expr) -> Expr:
    return Expr.unary("!", value, "bool")


def _implies(premise: Expr, conclusion: Expr) -> Expr:
    return _or(_not(premise), conclusion)


def _join_boolean(expressions: tuple[Expr, ...], op: str) -> Expr:
    if not expressions:
        return Expr.boolean(True)
    result = expressions[0]
    for expression in expressions[1:]:
        result = Expr.binary(op, result, expression, "bool")
    return result


def _equality(name: str, type_name: str, value: Expr) -> Expr:
    return Expr.binary("==", Expr.variable(name, type_name), value, "bool")


def _literal_integer(expr: Expr) -> bool:
    if expr.kind == "constant" and is_signed_integer_type(expr.type):
        return True
    return (
        expr.kind == "unary"
        and expr.op == "-"
        and len(expr.args) == 1
        and expr.args[0].kind == "constant"
        and expr.args[0].type == expr.type
        and is_signed_integer_type(expr.type)
    )


def _contains_nonlinear_multiplication(expr: Expr) -> bool:
    if expr.kind == "binary" and expr.op == "*":
        left, right = expr.args
        if not _literal_integer(left) and not _literal_integer(right):
            return True
    return any(_contains_nonlinear_multiplication(arg) for arg in expr.args)


@dataclass(frozen=True, slots=True)
class _PathState:
    assumptions: tuple[Expr, ...]
    trace_templates: tuple[TraceTemplate, ...] = ()

    def add(self, expression: Expr) -> "_PathState":
        if expression in self.assumptions:
            return self
        return _PathState(self.assumptions + (expression,), self.trace_templates)

    def decide(
        self,
        condition: Expr,
        taken: bool,
        kind: str,
        location: SourceLocation,
    ) -> "_PathState":
        assumption = condition if taken else _not(condition)
        state = self.add(assumption)
        template = TraceTemplate(kind, condition, self.assumptions, location)
        if template in state.trace_templates:
            return state
        return _PathState(
            state.assumptions,
            state.trace_templates + (template,),
        )


class VerificationConditionGenerator:
    def __init__(self, module: ModuleIR) -> None:
        self.module = module
        self._obligation_index = 0
        self._obligations: list[Obligation] = []
        self._by_key: dict[tuple[str, int], list[FunctionIR]] = {}
        self._consistency_keys: set[tuple[str, int]] = set()
        self._well_formed_keys: set[tuple[str, int]] = set()
        for function in module.functions:
            self._by_key.setdefault(function.key, []).append(function)
        self._recursive_reasons = self._recursive_call_reasons()

    def generate(self) -> tuple[Obligation, ...]:
        for issue in self.module.unsupported:
            self._unsupported_obligation(
                "<module>", issue, issue.reason or "unsupported module construct"
            )

        for function in self.module.functions:
            recursion_reason = self._recursive_reasons.get(function.key)
            if recursion_reason is not None:
                if function.has_body:
                    self._add(
                        function.name,
                        "unsupported_construct",
                        (),
                        None,
                        function.location,
                        recursion_reason,
                        unsupported_reason=recursion_reason,
                    )
                continue
            unsupported = self._first_unsupported(function.body)
            if unsupported is not None:
                self._unsupported_obligation(
                    function.name,
                    unsupported,
                    unsupported.reason or "unsupported function construct",
                )
                continue

            unannotated_loop = self._first_unannotated_loop(function.body)
            if unannotated_loop is not None:
                self._unsupported_obligation(
                    function.name,
                    unannotated_loop,
                    "WhileStmt is unsupported without a cs: invariant",
                )
                continue
            contracts = self._contracts_for(function)
            self._contract_consistency(function, contracts)
            if not function.has_body:
                self._external_contract_well_formed(function, contracts)
                continue
            initial = _PathState(tuple(self._type_bounds(function)))
            for contract in contracts:
                if contract.kind == "requires":
                    initial = initial.add(contract.expression)
            alive = self._walk_sequence(
                function.body,
                [initial],
                function,
                tuple(contract for contract in contracts if contract.kind == "ensures"),
            )
            for state in alive:
                self._add(
                    function.name,
                    "missing_return",
                    state.assumptions,
                    Expr.boolean(False),
                    function.location,
                    "non-void function must return on every reachable path",
                    trace_templates=state.trace_templates,
                )
        return tuple(self._obligations)

    def _recursive_call_reasons(self) -> dict[tuple[str, int], str]:
        graph = {key: set() for key in self._by_key}
        for key, functions in self._by_key.items():
            for function in functions:
                if not function.has_body:
                    continue
                graph[key].update(
                    called
                    for called in self._called_keys(function.body)
                    if called in graph
                )

        reachable: dict[tuple[str, int], set[tuple[str, int]]] = {}
        for start in sorted(graph):
            visited: set[tuple[str, int]] = set()
            pending = list(reversed(sorted(graph[start])))
            while pending:
                current = pending.pop()
                if current in visited:
                    continue
                visited.add(current)
                pending.extend(
                    reversed(sorted(graph[current] - visited))
                )
            reachable[start] = visited

        recursive = {key for key in graph if key in reachable[key]}
        reasons: dict[tuple[str, int], str] = {}
        remaining = set(recursive)
        while remaining:
            start = min(remaining)
            component = {
                candidate
                for candidate in recursive
                if candidate in reachable[start]
                and start in reachable[candidate]
            }
            remaining.difference_update(component)
            labels = ", ".join(
                f"{name}/{arity}" for name, arity in sorted(component)
            )
            recursion_kind = (
                "direct recursion"
                if len(component) == 1
                else "mutual recursion"
            )
            reason = (
                f"{recursion_kind} is unsupported without a "
                f"decreasing-measure policy: {labels}"
            )
            for key in component:
                reasons[key] = reason
        return reasons

    @staticmethod
    def _called_keys(nodes: Iterable[IRNode]) -> set[tuple[str, int]]:
        result: set[tuple[str, int]] = set()
        for node in nodes:
            if node.kind == "call" and node.callee is not None:
                result.add((node.callee, len(node.arguments)))
            result.update(
                VerificationConditionGenerator._called_keys(node.body)
            )
            result.update(
                VerificationConditionGenerator._called_keys(node.then_body)
            )
            result.update(
                VerificationConditionGenerator._called_keys(node.else_body)
            )
        return result

    def _contract_consistency(
        self, function: FunctionIR, contracts: tuple[Contract, ...]
    ) -> None:
        if function.key in self._consistency_keys:
            return
        self._consistency_keys.add(function.key)
        requires = tuple(
            contract for contract in contracts if contract.kind == "requires"
        )
        if not requires:
            return
        assumptions = tuple(self._type_bounds(function)) + tuple(
            contract.expression for contract in requires
        )
        self._add(
            function.name,
            "contract_consistency",
            assumptions,
            None,
            requires[0].location,
            "function requirements must admit at least one input",
            mode="satisfiable",
        )

    def _external_contract_well_formed(
        self, function: FunctionIR, contracts: tuple[Contract, ...]
    ) -> None:
        if function.key in self._well_formed_keys:
            return
        if any(candidate.has_body for candidate in self._by_key[function.key]):
            return
        self._well_formed_keys.add(function.key)
        for contract in contracts:
            if contract.kind != "ensures":
                continue
            self._add(
                function.name,
                "contract_well_formed",
                (),
                contract.expression,
                contract.location,
                f"external postcondition must be in the supported logic fragment: {contract.text}",
                mode="well_formed",
            )

    def _walk_sequence(
        self,
        nodes: Iterable[IRNode],
        states: list[_PathState],
        function: FunctionIR,
        ensures: tuple[Contract, ...],
    ) -> list[_PathState]:
        current = states
        for node in nodes:
            next_states: list[_PathState] = []
            for state in current:
                next_states.extend(self._walk_node(node, state, function, ensures))
            current = next_states
            if not current:
                break
        return current

    def _walk_node(
        self,
        node: IRNode,
        state: _PathState,
        function: FunctionIR,
        ensures: tuple[Contract, ...],
    ) -> list[_PathState]:
        if node.kind == "assume":
            assert node.expression is not None
            return [state.add(node.expression)]
        if node.kind == "assign":
            assert node.expression is not None and node.target is not None
            defined = self._expression_safety(
                function.name, node.expression, state, node
            )
            type_name = self._symbol_type(function, node.target)
            return [
                defined.add(_equality(node.target, type_name, node.expression))
            ]
        if node.kind == "assert":
            assert node.expression is not None
            defined = self._expression_safety(
                function.name, node.expression, state, node
            )
            self._add(
                function.name,
                "assertion",
                defined.assumptions,
                node.expression,
                node.location,
                "source assertion must hold",
                trace_templates=defined.trace_templates,
            )
            return [defined.add(node.expression)]
        if node.kind == "call":
            defined = state
            for argument in node.arguments:
                defined = self._expression_safety(
                    function.name, argument, defined, node
                )
            self._call_preconditions(function, node, defined)
            if node.target is None:
                return [defined]
            if (
                node.result_type is None
                or not is_fixed_integer_type(node.result_type)
                or self._symbol_type(function, node.target) != node.result_type
            ):
                self._add(
                    function.name,
                    "unsupported_construct",
                    defined.assumptions,
                    None,
                    node.location,
                    "call-result target must have explicit matching int type",
                    unsupported_reason="malformed call-result IR",
                    trace_templates=defined.trace_templates,
                )
                return [defined]
            target = Expr.variable(node.target, node.result_type)
            after_call = defined
            if is_signed_integer_type(node.result_type):
                profile = integer_type(node.result_type)
                after_call = after_call.add(
                    _binary(
                        ">=",
                        target,
                        Expr.integer(profile.minimum, node.result_type),
                    )
                )
                after_call = after_call.add(
                    _binary(
                        "<=",
                        target,
                        Expr.integer(profile.maximum, node.result_type),
                    )
                )
            return [self._assume_call_postconditions(node, after_call)]
        if node.kind == "loop":
            assert node.expression is not None
            if not node.invariants:
                reason = "WhileStmt is unsupported without a cs: invariant"
                self._add(
                    function.name,
                    "unsupported_construct",
                    state.assumptions,
                    None,
                    node.location,
                    reason,
                    unsupported_reason=reason,
                    trace_templates=state.trace_templates,
                )
                return []

            entry_replacements = self._loop_replacements(node, "entry")
            for invariant in node.invariants:
                self._add(
                    function.name,
                    "loop_invariant_entry",
                    state.assumptions,
                    invariant.expression.substitute(entry_replacements),
                    invariant.location,
                    f"loop invariant must hold on entry: {invariant.text}",
                    trace_templates=state.trace_templates,
                )

            head_state = self._add_loop_havoc_bounds(state, node, "head")
            for invariant in node.invariants:
                head_state = head_state.add(invariant.expression)
            head_state = self._expression_safety(
                function.name, node.expression, head_state, node
            )
            body_states = self._walk_sequence(
                node.body,
                [head_state.add(node.expression)],
                function,
                ensures,
            )
            back_edge_replacements = self._loop_replacements(
                node, "back_edge"
            )
            for body_state in body_states:
                for invariant in node.invariants:
                    self._add(
                        function.name,
                        "loop_invariant_preservation",
                        body_state.assumptions,
                        invariant.expression.substitute(
                            back_edge_replacements
                        ),
                        invariant.location,
                        f"loop body must preserve invariant: {invariant.text}",
                        trace_templates=body_state.trace_templates,
                    )

            exit_state = self._add_loop_havoc_bounds(state, node, "exit")
            exit_replacements = self._loop_replacements(node, "exit")
            for invariant in node.invariants:
                exit_state = exit_state.add(
                    invariant.expression.substitute(exit_replacements)
                )
            exit_condition = node.expression.substitute(exit_replacements)
            exit_state = self._expression_safety(
                function.name, exit_condition, exit_state, node
            )
            return [exit_state.add(_not(exit_condition))]
        if node.kind == "return":
            assert node.expression is not None
            defined = self._expression_safety(
                function.name, node.expression, state, node
            )
            for contract in ensures:
                goal = contract.expression.substitute({"result": node.expression})
                self._add(
                    function.name,
                    "postcondition",
                    defined.assumptions,
                    goal,
                    node.location,
                    f"postcondition declared at line {contract.location.line}: {contract.text}",
                    trace_templates=defined.trace_templates,
                )
            return []
        if node.kind == "branch":
            assert node.expression is not None
            defined = self._expression_safety(
                function.name, node.expression, state, node
            )
            true_states = self._walk_sequence(
                node.then_body,
                [
                    defined.decide(
                        node.expression, True, "branch", node.location
                    )
                ],
                function,
                ensures,
            )
            false_states = self._walk_sequence(
                node.else_body,
                [
                    defined.decide(
                        node.expression, False, "branch", node.location
                    )
                ],
                function,
                ensures,
            )
            merged = [
                self._apply_merges(item, node.merges, True, function)
                for item in true_states
            ]
            merged.extend(
                self._apply_merges(item, node.merges, False, function)
                for item in false_states
            )
            return self._compact_states(merged)
        raise RuntimeError(f"unexpected IR node kind during VC generation: {node.kind}")

    @staticmethod
    def _compact_states(states: list[_PathState]) -> list[_PathState]:
        if len(states) < 2:
            return states

        unique: list[_PathState] = []
        by_assumptions: dict[frozenset[Expr], int] = {}
        for state in states:
            key = frozenset(state.assumptions)
            existing = by_assumptions.get(key)
            if existing is None:
                by_assumptions[key] = len(unique)
                unique.append(state)
                continue
            prior = unique[existing]
            templates = prior.trace_templates
            for template in state.trace_templates:
                if template not in templates:
                    templates += (template,)
            unique[existing] = _PathState(prior.assumptions, templates)

        if len(unique) == 1:
            return unique

        common_set = set(unique[0].assumptions)
        for state in unique[1:]:
            common_set.intersection_update(state.assumptions)
        common = tuple(
            assumption
            for assumption in unique[0].assumptions
            if assumption in common_set
        )
        residuals = [
            tuple(
                assumption
                for assumption in state.assumptions
                if assumption not in common_set
            )
            for state in unique
        ]
        path_union = _join_boolean(residuals[0], "&&")
        for residual in residuals[1:]:
            path_union = _or(path_union, _join_boolean(residual, "&&"))

        templates: tuple[TraceTemplate, ...] = ()
        for state in unique:
            for template in state.trace_templates:
                if template not in templates:
                    templates += (template,)
        return [_PathState(common + (path_union,), templates)]

    def _apply_merges(
        self,
        state: _PathState,
        merges: tuple[IRNode, ...],
        true_edge: bool,
        function: FunctionIR,
    ) -> _PathState:
        result = state
        for merge in merges:
            assert merge.target is not None
            incoming = merge.incoming_true if true_edge else merge.incoming_false
            assert incoming is not None
            result = result.add(
                _equality(
                    merge.target,
                    self._symbol_type(function, merge.target),
                    incoming,
                )
            )
        return result

    @staticmethod
    def _loop_replacements(
        node: IRNode, state_name: str
    ) -> dict[str, Expr]:
        return {
            variable.head: Expr.variable(
                str(getattr(variable, state_name)), variable.type
            )
            for variable in node.loop_variables
        }

    @staticmethod
    def _add_loop_havoc_bounds(
        state: _PathState, node: IRNode, state_name: str
    ) -> _PathState:
        result = state
        for variable in node.loop_variables:
            if not is_signed_integer_type(variable.type):
                continue
            profile = integer_type(variable.type)
            value = Expr.variable(
                str(getattr(variable, state_name)), variable.type
            )
            result = result.add(
                _binary(">=", value, Expr.integer(profile.minimum, variable.type))
            )
            result = result.add(
                _binary("<=", value, Expr.integer(profile.maximum, variable.type))
            )
        return result

    def _expression_safety(
        self, function: str, expr: Expr, state: _PathState, node: IRNode
    ) -> _PathState:
        if expr.kind == "binary" and expr.op in {"&&", "||"}:
            left, right = expr.args
            left_defined = self._expression_safety(function, left, state, node)
            rhs_guard = left if expr.op == "&&" else _not(left)
            guarded = left_defined.add(rhs_guard)
            right_defined = self._expression_safety(
                function, right, guarded, node
            )

            # Preserve RHS guarantees as guarded facts for later operations.
            # Assuming the execution guard itself here would delete the
            # short-circuited path.
            result = left_defined
            for guarantee in right_defined.assumptions:
                if guarantee not in guarded.assumptions:
                    result = result.add(_implies(rhs_guard, guarantee))
            return result

        current = state
        for argument in expr.args:
            current = self._expression_safety(function, argument, current, node)
        if (
            expr.kind == "unary"
            and expr.op == "-"
            and is_signed_integer_type(expr.type)
        ):
            profile = integer_type(expr.type)
            in_range = _binary(
                "!=",
                expr.args[0],
                Expr.integer(profile.minimum, expr.type),
            )
            self._add(
                function,
                "signed_overflow",
                current.assumptions,
                in_range,
                node.location,
                f"signed negation must remain within {expr.type}",
                trace_templates=current.trace_templates,
            )
            return current.add(in_range)
        if expr.kind != "binary" or not is_fixed_integer_type(expr.type):
            return current
        if expr.op in {"+", "-", "*"}:
            if not is_signed_integer_type(expr.type):
                return current
            profile = integer_type(expr.type)
            fragment = classify_expressions(current.assumptions + (expr,))
            if (
                expr.op == "*"
                and _contains_nonlinear_multiplication(expr)
                and fragment == QueryFragment.QF_LIA
            ):
                self._add(
                    function,
                    "unsupported_logic",
                    current.assumptions,
                    None,
                    node.location,
                    "variable-by-variable multiplication is outside QF_LIA",
                    unsupported_reason="nonlinear integer multiplication",
                    trace_templates=current.trace_templates,
                )
                return current
            if fragment == QueryFragment.QF_BV:
                in_range = Expr.predicate("signed_no_overflow", expr)
                self._add(
                    function,
                    "signed_overflow",
                    current.assumptions,
                    in_range,
                    node.location,
                    f"signed {expr.op} result must remain within {expr.type}",
                    trace_templates=current.trace_templates,
                )
                return current.add(in_range)
            lower_bound = _binary(
                ">=", expr, Expr.integer(profile.minimum, expr.type)
            )
            upper_bound = _binary(
                "<=", expr, Expr.integer(profile.maximum, expr.type)
            )
            in_range = _and(lower_bound, upper_bound)
            self._add(
                function,
                "signed_overflow",
                current.assumptions,
                in_range,
                node.location,
                f"signed {expr.op} result must remain within {expr.type}",
                trace_templates=current.trace_templates,
            )
            return current.add(lower_bound).add(upper_bound)
        if expr.op in {"/", "%"}:
            numerator, denominator = expr.args
            nonzero = _binary("!=", denominator, Expr.integer(0, expr.type))
            self._add(
                function,
                "division_by_zero",
                current.assumptions,
                nonzero,
                node.location,
                "integer divisor must be non-zero",
                trace_templates=current.trace_templates,
            )
            denominator_defined = current.add(nonzero)
            if not is_signed_integer_type(expr.type):
                return denominator_defined
            profile = integer_type(expr.type)
            overflow_case = _and(
                _binary(
                    "==",
                    numerator,
                    Expr.integer(profile.minimum, expr.type),
                ),
                _binary("==", denominator, Expr.integer(-1, expr.type)),
            )
            no_overflow = _not(overflow_case)
            self._add(
                function,
                "signed_overflow",
                denominator_defined.assumptions,
                no_overflow,
                node.location,
                f"{expr.type} minimum {expr.op} -1 must be excluded",
                trace_templates=denominator_defined.trace_templates,
            )
            return denominator_defined.add(no_overflow)
        return current

    def _call_preconditions(
        self, caller: FunctionIR, node: IRNode, state: _PathState
    ) -> None:
        key = (node.callee or "", len(node.arguments))
        candidates = self._by_key.get(key, [])
        if not candidates:
            self._add(
                caller.name,
                "unsupported_construct",
                state.assumptions,
                None,
                node.location,
                f"call to {node.callee} has no visible body or contract",
                unsupported_reason="uncontracted external call",
                trace_templates=state.trace_templates,
            )
            return
        has_body = any(candidate.has_body for candidate in candidates)
        has_contract = any(candidate.contracts for candidate in candidates)
        requires: list[tuple[FunctionIR, Contract]] = []
        for candidate in candidates:
            requires.extend(
                (candidate, contract)
                for contract in candidate.contracts
                if contract.kind == "requires"
            )
        if not has_body and not has_contract:
            self._add(
                caller.name,
                "unsupported_construct",
                state.assumptions,
                None,
                node.location,
                f"external call {node.callee} has no contract",
                unsupported_reason="uncontracted external call",
                trace_templates=state.trace_templates,
            )
            return
        seen: set[Expr] = set()
        for owner, contract in requires:
            replacements = {
                parameter.versioned_name: argument
                for parameter, argument in zip(owner.parameters, node.arguments)
            }
            conclusion = contract.expression.substitute(replacements)
            if conclusion in seen:
                continue
            seen.add(conclusion)
            self._add(
                caller.name,
                "precondition",
                state.assumptions,
                conclusion,
                node.location,
                f"{node.callee} requires {contract.text.removeprefix('requires ')}",
                trace_templates=state.trace_templates,
            )

    def _assume_call_postconditions(
        self,
        node: IRNode,
        state: _PathState,
    ) -> _PathState:
        assert node.target is not None and node.result_type is not None
        key = (node.callee or "", len(node.arguments))
        result = Expr.variable(node.target, node.result_type)
        current = state
        seen: set[Expr] = set()
        for owner in self._by_key.get(key, []):
            replacements = {
                parameter.versioned_name: argument
                for parameter, argument in zip(owner.parameters, node.arguments)
            }
            replacements["result"] = result
            for contract in owner.contracts:
                if contract.kind != "ensures":
                    continue
                assumption = contract.expression.substitute(replacements)
                if assumption in seen:
                    continue
                seen.add(assumption)
                current = current.add(assumption)
        return current

    def _contracts_for(self, function: FunctionIR) -> tuple[Contract, ...]:
        contracts: list[Contract] = []
        seen: set[tuple[str, Expr]] = set()
        for owner in self._by_key.get(function.key, [function]):
            replacements = {
                source.versioned_name: Expr.variable(target.versioned_name, target.type)
                for source, target in zip(owner.parameters, function.parameters)
            }
            for contract in owner.contracts:
                adapted = Contract(
                    kind=contract.kind,
                    expression=contract.expression.substitute(replacements),
                    location=contract.location,
                    text=contract.text,
                    machine_proposed=contract.machine_proposed,
                )
                key = (adapted.kind, adapted.expression)
                if key not in seen:
                    seen.add(key)
                    contracts.append(adapted)
        return tuple(contracts)

    @staticmethod
    def _type_bounds(function: FunctionIR) -> Iterable[Expr]:
        for parameter in function.parameters:
            if not is_signed_integer_type(parameter.type):
                continue
            profile = integer_type(parameter.type)
            value = Expr.variable(parameter.versioned_name, parameter.type)
            yield _binary(
                ">=", value, Expr.integer(profile.minimum, parameter.type)
            )
            yield _binary(
                "<=", value, Expr.integer(profile.maximum, parameter.type)
            )

    @staticmethod
    def _symbol_type(function: FunctionIR, versioned_name: str) -> str:
        original = versioned_name.split("#", 1)[0]
        for symbol in function.parameters + function.locals:
            if symbol.name == original:
                return symbol.type
        raise RuntimeError(f"unknown IR symbol {versioned_name}")

    @staticmethod
    def _first_unsupported(nodes: Iterable[IRNode]) -> IRNode | None:
        for node in nodes:
            if node.kind == "unsupported":
                return node
            nested = VerificationConditionGenerator._first_unsupported(node.body)
            if nested is not None:
                return nested
            nested = VerificationConditionGenerator._first_unsupported(node.then_body)
            if nested is not None:
                return nested
            nested = VerificationConditionGenerator._first_unsupported(node.else_body)
            if nested is not None:
                return nested
        return None

    @staticmethod
    def _first_unannotated_loop(nodes: Iterable[IRNode]) -> IRNode | None:
        for node in nodes:
            if node.kind == "loop" and not node.invariants:
                return node
            for nested_nodes in (node.body, node.then_body, node.else_body):
                nested = VerificationConditionGenerator._first_unannotated_loop(
                    nested_nodes
                )
                if nested is not None:
                    return nested
        return None

    def _unsupported_obligation(
        self, function: str, node: IRNode, reason: str
    ) -> None:
        self._add(
            function,
            "unsupported_construct",
            (),
            None,
            node.location,
            reason,
            unsupported_reason=reason,
        )

    def _add(
        self,
        function: str,
        kind: str,
        assumptions: tuple[Expr, ...],
        conclusion: Expr | None,
        location: SourceLocation,
        description: str,
        unsupported_reason: str | None = None,
        mode: str = "validity",
        trace_templates: tuple[TraceTemplate, ...] = (),
    ) -> None:
        self._obligation_index += 1
        self._obligations.append(
            Obligation(
                id=f"ob{self._obligation_index:05d}",
                function=function,
                kind=kind,
                assumptions=assumptions,
                conclusion=conclusion,
                location=location,
                description=description,
                unsupported_reason=unsupported_reason,
                mode=mode,
                trace_templates=trace_templates,
            )
        )
