# ReportBuilder Pilot — Frozen Experiment Contract

Status: **FROZEN BEFORE MODEL OUTPUTS**

## Common execution envelope

Both conditions use the same envelope.

- Target: Python 3.11, standard library only.
- No network access during generation or execution.
- Trial workspace contains only the current implementation, one model-facing
  condition file, and the current request.
- The agent cannot read this experiment contract, the evaluator manifest,
  scoring, hidden checks, the sibling condition, or the wider repository.
- A fresh agent context is used for each stage. It receives the current code,
  the original condition, and the current request.
- Model identity, effort/temperature-equivalent settings, tool permissions, and
  repetition seed/order are fixed identically across paired conditions before
  the first trial and recorded in a later run manifest. Gate A does not select
  a model.

## Required deliverable shape

The implementation must create a package named `report_builder` with these
public names available for deterministic tests:

- `report_builder.ui.UI`
- `report_builder.service.ReportService`
- `report_builder.data.DataReader`
- `report_builder.render.Renderer`
- `report_builder.results.ReadFailure`
- `report_builder.results.EmptyReport`

`ReportService` exposes `build_report(query)`. Dependencies may be injected.
No other file layout or internal data structure is prescribed.

## Request 0 — initial implementation

> Implement the supplied ReportBuilder specification in Python 3.11 using only
> the standard library. Use the required public package/API shape. Keep the
> solution small. Do not add network behavior. Do not modify the supplied
> specification.

This request is identical for both conditions.

## Request 1 — maintenance: CSV

> Add CSV report output as an optional output format while preserving all
> existing behavior and constraints. Existing callers that do not request CSV
> must keep their prior behavior.

No original fact is repeated in this maintenance request.

## Request 2 — maintenance: in-memory cache

> Add an optional in-memory cache for successful report results while preserving
> all existing behavior and constraints. Existing callers that do not enable
> caching must keep their prior behavior.

The request deliberately does not resolve the previously open eviction-policy
decision.

## Trial sequence

For each paired repetition:

1. Generate initial implementation from one condition + Request 0.
2. Deterministically evaluate and archive the result without repair.
3. Start a fresh agent context with that code + the same original condition +
   Request 1; evaluate and archive without repair.
4. Start a fresh agent context with that code + the same original condition +
   Request 2; evaluate and archive without repair.
5. Repeat with the sibling condition under the same model/settings/tool envelope.

No failed output is repaired before scoring. Diagnostic reruns are separate and
cannot replace the frozen trial.
