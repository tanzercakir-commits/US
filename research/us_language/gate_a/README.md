# Gate A — ReportBuilder representation experiment

Status: **FROZEN DESIGN / NO MODEL OUTPUTS YET**

This directory is an isolated PRACTICAL research artifact under D17-D19.
It does not change the production TODO, verifier semantics, schemas, CI,
release controls, or supported-behavior claims.

## Hypothesis

Holding information, task, model settings, and evaluation constant, the minimal
US representation preserves intent, architecture, rules, delegated freedom,
flow, and unresolved decisions better across initial generation and maintenance
than a strong Markdown control.

## Gate A contents

- `REPRESENTATION_V0.md` — semantics of the six representation classes.
- `FACT_MANIFEST.json` — evaluator-only canonical fact inventory.
- `REPORTBUILDER.us.txt` — model-facing structured condition.
- `REPORTBUILDER.md` — model-facing strong Markdown control.
- `EXPERIMENT_CONTRACT.md` — frozen implementation and maintenance requests.
- `SCORING.md` — deterministic-core acceptance and outcome rules.

Trial agents receive exactly one condition file plus the same task request and
the current trial workspace. They do not receive the fact manifest, scoring
document, hidden checks, sibling condition, or repository/network access.

No parser, compiler, production adapter, benchmark framework, or verifier
integration is authorized by this Gate A freeze.
