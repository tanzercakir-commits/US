# US Language — Gate A to Gate A2 Handoff

Date: 2026-09-24

## Read first

1. `AGENTS.md`
2. `TODO.md`
3. PLAN decisions D17-D19
4. `research/us_language/PREPROJECT.md`
5. `research/us_language/gate_a/RESULT.md`
6. this handoff

Do not rely on prior conversation history or memory. Reconstruct state from repository evidence.

## Governance

US Language remains owner-authorized PRACTICAL research under `research/us_language/`. Production TODO remains A7.4. Do not touch production verifier/runtime semantics, shared schemas, repository tools/tests/examples, CI, release controls, or public support claims. Production integration requires a new PLAN stage and at least REVIEWED governance.

## Gate A

Frozen Gate A head: `e922e1d8b264c592edcd8da84e34bd864738a67f`.

Representation v0 tested six concepts: `intent`, `architecture`, `rules`, `freedom`, `flow`, `unknowns` against an information-equivalent strong Markdown control. Pilot: ReportBuilder. Per condition/repetition: initial 40 + CSV 25 + cache 35. Five paired repetitions, 30 stage evaluations total.

Final deterministic results:

| Run | US | Markdown |
|---|---:|---:|
| 1 | 100 | 100 |
| 2 | 100 | 100 |
| 3 | 100 | 100 |
| 4 | 100 | 100 |
| 5 | 100 | 100 |

Median 100-100; critical events 0-0. Frozen outcome: **NULL**.

Interpretation: this pilot did not demonstrate a measurable US representation advantage. It also does not establish general equivalence. Both conditions saturated the benchmark, so the main finding is a ceiling/sensitivity problem.

## Important observations

Human review stayed separate from frozen scoring. Some implementations passed the frozen immutability check while exposing source rows directly to a renderer; other implementations defensively copied/deep-copied them. Gate A therefore had measurement blind spots. Do not rescore Gate A post hoc; use this to improve the next experiment.

Python 3.11 runtime was unavailable in trial environments; most runtime checks used Python 3.13.5, with later Python 3.11 grammar checks. A formal model/settings/tool-permissions run manifest was not frozen before execution, limiting stronger reproducibility claims.

Research result branch: `research/us-language-gate-a-result`.
Result commit before handoff: `32954a8cca8bfae0d779c12477fc043c5022d9fc`.
Draft PR: #8.

## Do not do next

Do not build a parser/compiler, weaken Markdown, change Gate A scoring, or integrate US Language into production surfaces. Do not reinterpret NULL as a US win.

## Recommended next step: Gate A2

Design a NEW, harder, information-equivalent experiment. Keep Representation v0 conceptually stable initially. Increase cross-cutting information pressure instead of weakening the control.

Gate A2 should include more components/files, cross-module dependency constraints, interacting invariants, explicit freedom distinct from unknowns, at least two unresolved decisions, richer failure/retry/degraded flows, maintenance requests that create tension with earlier intent, at least one locally convenient but globally forbidden change, delayed requests that do not repeat old constraints, adversarial deterministic checks, a canonical parity fact manifest, frozen scoring before outputs, and a frozen model/settings/tool run manifest.

A multi-component workflow system is a promising candidate: API, WorkflowService, JobStore, Exporter, AuditLog, Policy. Example pressures: API must not call JobStore directly; JobStore owns persistence; audit is append-only; retries must not duplicate external effects; export failure must not roll back committed workflow state; batching is delegated freedom; policy choices remain unresolved.

## Start instruction for the next conversation

Continue US Language research from this handoff. Do not rely on previous conversation history or memory. Gate A is complete with a frozen NULL result caused by full score saturation. Do not build a parser/compiler or touch production verifier surfaces. Design Gate A2 as a harder, fair, falsifiable, information-equivalent US-vs-Markdown experiment.

Before implementing anything, report: (1) Gate A2 problem, (2) why it is harder than ReportBuilder, (3) exact parity method, (4) maintenance sequence, (5) deterministic acceptance/scoring, and (6) how it avoids Gate A ceiling/blind spots.
