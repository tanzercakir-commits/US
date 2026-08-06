# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A5.4 - scaling phase gate**

## Next

- None queued after the active phase gate.

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A5.3 added deterministic per-process solver timeouts and
source-ordered per-file supported-check budgets. Exhaustion is explicit unknown,
cache cannot bypass the limit, and cross-check cannot hide timeout as verified.
Next is the A5.4 scaling phase gate.
