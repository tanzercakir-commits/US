# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A2.4 — Phase gate** (verified/violated modular example + full
  suite; DoD in the plan)

## Next

- [ ] A3.1 — `cs: invariant` syntax
- [ ] A3.2 — `while` lowering + havoc
- [ ] F2.1 — `fixtures/` layout + regeneration script (can run parallel to
  A1; prerequisite of B1.1)

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 — A2.3 completed: deterministic direct/mutual recursion
detection fails closed with explicit cycle reasons. Next is A2.4.
