# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A1.5 — Solver decision document** (`docs/solver_decision.md` +
  README link; DoD in the plan)

## Next

- [ ] A1.6 — Phase gate: golden tests
- [ ] A2.1 — IR: call-with-result node
- [ ] F2.1 — `fixtures/` layout + regeneration script (can run parallel to
  A1; prerequisite of B1.1)

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 — A1.4 completed with swappable affine/Z3 backends and
deterministic cross-check alarms. Next work item is A1.5.
