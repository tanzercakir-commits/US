# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.0 - semantic-extensions expansion stage**

## Next

- [ ] **A6.1 - integer-semantics decision point**
- [ ] **A6.2 - restricted arrays**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A5.4 froze the scaling slice and executable phase gate: 11/11
cross-check obligations verify, warm cache makes zero backend calls, budgeted
reports repeat exactly, and the merge probe remains 1/1/1/1. Next is A6.0.
