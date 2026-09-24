# ReportBuilder Pilot — Frozen Experiment Contract

Status: **FROZEN BEFORE MODEL OUTPUTS**

## Common execution envelope

Both representation conditions use the same envelope.

- Target: Python 3.11, standard library only.
- No network access during generation or execution.
- A trial workspace contains only the current implementation (if any), exactly
  one model-facing condition, and exactly one model-facing request.
- The agent cannot read `FACT_MANIFEST.json`, `SCORING.md`, evaluator code,
  hidden results, the sibling condition, other trial outputs, or the wider US
  repository.
- A fresh agent context is used for every stage.
- Model identity, reasoning/effort or temperature-equivalent settings, tool
  permissions, and repetition ordering are fixed identically across paired
  conditions before the first model trial and recorded in a run manifest.

## Frozen model-facing inputs

Representation condition — exactly one of:

- `REPORTBUILDER.us.txt`
- `REPORTBUILDER.md`

Task — exactly one matching the current stage:

- `REQUEST_0_INITIAL.md`
- `REQUEST_1_CSV.md`
- `REQUEST_2_CACHE.md`

The request files contain the common executable API details needed by the
hidden deterministic evaluator. Those details are identical across the US and
Markdown conditions and therefore are not a representation advantage.

## Trial sequence

For each paired repetition:

1. Fresh context: condition + `REQUEST_0_INITIAL.md`; generate the initial
   implementation; evaluate and archive without repair.
2. Fresh context: resulting code + the same original condition +
   `REQUEST_1_CSV.md`; evaluate and archive without repair.
3. Fresh context: resulting code + the same original condition +
   `REQUEST_2_CACHE.md`; evaluate and archive without repair.
4. Run the sibling representation under the identical model/settings/tool
   envelope.

Use five paired repetitions. Alternate pair order deterministically:
US/Markdown, Markdown/US, US/Markdown, Markdown/US, US/Markdown.

No failed output is repaired before scoring. Diagnostic reruns are separate and
cannot replace a frozen trial.

## Freeze rule

After the first model output exists, changing any fact, condition, request,
acceptance check, weight, threshold, or outcome rule invalidates the affected
pilot series. A redesigned experiment must use a new version/directory and keep
this frozen series intact.
