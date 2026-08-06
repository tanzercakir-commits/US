# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **F2.1 - fixtures layout + regeneration script** (declared outputs and
  DoD in the plan)

## Next

- None pulled until the F2 phase is read at stage start.
## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A3 phase gate passed: the sum loop verifies, the missing invariant
is unsupported, and the wrong invariant yields a replayed counterexample. Next
is F2.1.
