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

## Frozen model-facing inputs

- `REPORTBUILDER.us.txt` — structured US condition.
- `REPORTBUILDER.md` — strong Markdown control.
- `REQUEST_0_INITIAL.md` — initial implementation request.
- `REQUEST_1_CSV.md` — first maintenance request.
- `REQUEST_2_CACHE.md` — second maintenance request.

A trial agent receives exactly one condition, exactly one current request, and
its current trial code. It does not receive sibling conditions, evaluator-only
artifacts, prior sibling outputs, or wider repository/network access.

## Evaluator-only artifacts

- `REPRESENTATION_V0.md` — frozen semantics of the six representation classes.
- `FACT_MANIFEST.json` — canonical F01-F14 fact inventory and parity rule.
- `EXPERIMENT_CONTRACT.md` — pairing, isolation, sequencing, and freeze rules.
- `SCORING.md` — deterministic weights and outcome thresholds.
- `freeze_check.py` — verifies the frozen fact-ID parity and required artifacts.
- `evaluator.py` — deterministic per-stage hidden evaluator.
- `score_series.py` — deterministic five-pair outcome calculation.

Before any model trial, run `python freeze_check.py` from this directory.
Per-stage trial outputs are scored with `evaluator.py`; the completed five-pair
series is reduced to positive/null/negative/inconclusive by `score_series.py`.

No parser, compiler, production adapter, benchmark framework, production test
wiring, or verifier integration is authorized by this Gate A freeze.
