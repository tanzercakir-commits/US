# WorkflowRelay Gate A2 — Frozen Experiment Contract

Status: **FROZEN BEFORE MODEL OUTPUTS**

## Purpose

Gate A2 tests representation, not hidden information, evaluator access, or
different implementation instructions. The structured US condition and strong
Markdown condition receive the same canonical facts and the same maintenance
requests.

The experiment is allowed to produce a positive, negative, null,
inconclusive, insensitive-ceiling, or insensitive-floor result.

## Common execution envelope

Both conditions use the same envelope.

- Target implementation language: Python 3.11, standard library only.
- No network access during generation or execution.
- A trial workspace contains only:
  1. the implementation from the immediately prior stage of the same
     condition/repetition, when applicable;
  2. exactly one model-facing representation condition;
  3. exactly one current request.
- A trial agent cannot read the sibling condition, FACT_MANIFEST.json,
  REPRESENTATION_V0.md, SCORING.md, evaluator code, score-series code, hidden
  results, sibling outputs, prior repetitions, or the wider US repository.
- Every stage uses a fresh agent context.
- No failed output is repaired before scoring.
- Diagnostic reruns are labeled separately and never replace frozen trial
  output.

## Required pre-trial run manifest

No model trial may begin until `RUN_MANIFEST.json` exists and
`python freeze_check.py --trial-ready` succeeds.

The run manifest must freeze, before the first model output:

- exact source commit containing this Gate A2 design;
- exact model identity/version;
- reasoning/effort or temperature-equivalent setting;
- enabled tools and write permissions;
- network permission state;
- execution/runtime environment used for deterministic evaluation;
- five-pair ordering;
- fresh-context policy;
- frozen artifact SHA-256 digests.

`RUN_MANIFEST.template.json` is not trial authorization.

## Frozen model-facing conditions

Exactly one of:

- `WORKFLOWRELAY.us.txt`
- `WORKFLOWRELAY.md`

Both are deterministic renderings of `FACT_MANIFEST.json`.
`render_conditions.py --check` must succeed.

## Frozen maintenance sequence

For each condition/repetition:

1. fresh context: condition + `REQUEST_0_INITIAL.md`; implement from scratch;
2. fresh context: resulting stage-0 code + same condition +
   `REQUEST_1_BATCH.md`;
3. fresh context: resulting stage-1 code + same condition +
   `REQUEST_2_MULTI_EXPORT.md`;
4. fresh context: resulting stage-2 code + same condition +
   `REQUEST_3_RETRY.md`.

Each stage is evaluated and archived before the next stage begins.

The later maintenance requests intentionally do not repeat many original
constraints. Preservation of the original specification is part of the test.

## Repetitions and pairing

Use five paired repetitions.

Pair order is frozen as:

1. US, Markdown
2. Markdown, US
3. US, Markdown
4. Markdown, US
5. US, Markdown

Within a pair, both conditions use the identical frozen model/settings/tool
envelope.

## Evaluator adversarial policy

The deterministic evaluator is allowed to use hostile but protocol-conforming
collaborators, including:

- Processor objects that mutate nested payload input;
- Exporter objects that mutate nested result input;
- exporters that succeed and fail in controlled sequences;
- repeated equal job IDs;
- partial multi-export success followed by failure;
- a new WorkflowService instance over the same JobStore/AuditLog;
- explicit retry policies that cause one failed phase to repeat.

These probes exist to expose aliasing, durable-state, rollback, and
duplicate-effect bugs that passive Gate A collaborators could miss.

## Freeze rule

After the first model output exists, changing any of the following invalidates
the affected series:

- canonical facts or their condition renderer;
- either model-facing condition;
- any request;
- trial API;
- evaluator behavior;
- check weight or family;
- critical-event definition;
- sensitivity threshold;
- representation outcome rule;
- model/settings/tool envelope;
- pair ordering.

A redesign must use a new version/directory and retain this Gate A2 series
unchanged.

## Human review and cost observations

Human readability/maintainability review, token counts, wall-clock time, and
tool-call counts are recorded separately. They cannot change deterministic
correctness scores or representation outcomes.
