"""Human-readable deterministic dumps for IR and verification results."""

from __future__ import annotations

from .model import FunctionIR, IRNode, ModuleIR, VerificationReport


def dump_module(module: ModuleIR) -> str:
    lines = [f"module {module.source}"]
    for issue in module.unsupported:
        lines.append(
            f"  unsupported {issue.location.line}:{issue.location.column}: {issue.reason}"
        )
    for function in module.functions:
        lines.extend(_dump_function(function))
    return "\n".join(lines) + "\n"


def _dump_function(function: FunctionIR) -> list[str]:
    parameters = ", ".join(
        f"{parameter.versioned_name}:{parameter.type}"
        for parameter in function.parameters
    )
    suffix = "" if function.has_body else " declaration"
    lines = [
        f"function {function.name}({parameters}) -> {function.return_type}{suffix}"
    ]
    for contract in function.contracts:
        lines.append(f"  {contract.kind} {contract.expression.text()}")
    lines.extend(_dump_nodes(function.body, 1))
    return lines


def _dump_nodes(nodes: tuple[IRNode, ...], depth: int) -> list[str]:
    indent = "  " * depth
    lines: list[str] = []
    for node in nodes:
        prefix = f"{indent}{node.id} "
        if node.kind in {"assume", "assert", "return"}:
            lines.append(f"{prefix}{node.kind} {node.expression.text()}")
        elif node.kind == "assign":
            lines.append(f"{prefix}{node.target} := {node.expression.text()}")
        elif node.kind == "call":
            arguments = ", ".join(argument.text() for argument in node.arguments)
            lines.append(f"{prefix}call {node.callee}({arguments})")
        elif node.kind == "unsupported":
            lines.append(f"{prefix}unsupported {node.reason}")
        elif node.kind == "branch":
            lines.append(f"{prefix}branch {node.expression.text()}")
            lines.append(f"{indent}  true:")
            lines.extend(_dump_nodes(node.then_body, depth + 2))
            lines.append(f"{indent}  false:")
            lines.extend(_dump_nodes(node.else_body, depth + 2))
            for merge in node.merges:
                lines.append(
                    f"{indent}  {merge.id} merge {merge.target} := "
                    f"[true: {merge.incoming_true.text()}, "
                    f"false: {merge.incoming_false.text()}]"
                )
    return lines


def dump_results(report: VerificationReport) -> str:
    lines: list[str] = []
    for obligation, result in zip(report.obligations, report.results):
        lines.append(
            f"{result.status.value}: {result.function}:{result.kind} "
            f"at {result.location.file}:{result.location.line}:{result.location.column}"
        )
        lines.append(f"  {obligation.formula_text()}")
        lines.append(f"  {result.message}")
        if result.counterexample is not None:
            model = ", ".join(
                f"{name}={result.counterexample[name]}"
                for name in sorted(result.counterexample)
            )
            lines.append(f"  counterexample: {model or '{}'}")
    summary = report.summary()
    lines.append(
        "summary: "
        + ", ".join(f"{name}={summary[name]}" for name in sorted(summary))
    )
    return "\n".join(lines) + "\n"
