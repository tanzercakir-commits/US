# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A2.2 — VC: havoc + assumed ensures** (`semantic_verifier/vc.py` +
  tests + chain example; DoD in the plan)

## Next

- [ ] A2.3 — Recursion policy
- [ ] A2.4 — Phase gate
- [ ] F2.1 — `fixtures/` layout + regeneration script (can run parallel to
  A1; prerequisite of B1.1)

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 — A2.1 completed: controlled int call-result init/assign
lowering with fail-closed nested-call boundaries. Next is A2.2.
