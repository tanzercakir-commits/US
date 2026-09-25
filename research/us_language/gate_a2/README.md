# US Language — Gate A2

Status: **DESIGN FROZEN / NO MODEL OUTPUTS**

Gate A2 is an isolated PRACTICAL research experiment under PLAN decisions
D17-D19. It does not alter the production TODO, verifier/runtime semantics,
shared schemas, repository-level tests/tools, CI, release controls, or public
supported-behavior claims.

## Research question

Can Representation v0 preserve cross-cutting human intent, architecture,
invariants, delegated freedom, control flow, and intentionally unresolved
decisions better than a strong information-equivalent Markdown specification
when an implementation evolves through several interacting maintenance changes?

Gate A2 is not designed to make US win. It is designed to avoid the Gate A
ceiling while remaining cheap enough to falsify the representation hypothesis.

## System under test

The pilot system is **WorkflowRelay**, a multi-component workflow executor with:

- API
- WorkflowService
- JobStore
- Processor
- Exporter
- AuditLog
- injected policy callables introduced by maintenance

The experiment deliberately combines durable state, architecture boundaries,
deep alias isolation, append-only audit behavior, commit/export ordering,
partial external-effect failure, multi-export recovery, and automatic retry.

## Representation

Gate A2 keeps the six Representation v0 concepts unchanged:

- `intent`
- `architecture`
- `rules`
- `freedom`
- `flow`
- `unknowns`

No parser or compiler is built. Fact IDs are experimental parity anchors only.

## Model-facing inputs

A trial agent sees exactly one representation condition:

- `WORKFLOWRELAY.us.txt`, or
- `WORKFLOWRELAY.md`

and exactly one current request:

- `REQUEST_0_INITIAL.md`
- `REQUEST_1_BATCH.md`
- `REQUEST_2_MULTI_EXPORT.md`
- `REQUEST_3_RETRY.md`

For maintenance stages the agent also receives only the implementation produced
by the prior stage of the same repetition.

## Evaluator-only artifacts

- `REPRESENTATION_V0.md`
- `FACT_MANIFEST.json`
- `render_conditions.py`
- `EXPERIMENT_CONTRACT.md`
- `SCORING.md`
- `RUN_MANIFEST.template.json`
- `freeze_check.py`
- `evaluator.py`
- `score_series.py`

The condition files are deterministic renderings of the canonical fact
manifest. `freeze_check.py` verifies exact rendering and fact-ID parity.

## Freeze boundary

The benchmark design is frozen before model outputs. A trial series is **not**
authorized until an exact `RUN_MANIFEST.json` is created from the template and
`python freeze_check.py --trial-ready` passes.

After the first model output exists, changing any fact, request, evaluator
behavior, scoring weight, threshold, condition renderer, run envelope, or
outcome rule invalidates that series. Redesigns must use a new directory/version
and preserve this Gate A2 evidence unchanged.
