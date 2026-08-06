# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.1 - fixed-width integer-semantics decision point**

## Next

- [ ] **A6.2 - restricted arrays**
- [ ] **A6.3 - value-type structs**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.0 expanded A6.1-A6.7 with exact trust, schema, backend,
unsupported, and phase-gate contracts. Next is the fixed-width integer-semantics
decision and its implementation-stage insertion.
