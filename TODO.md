# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A1.1 — SMT-LIB2 emitter** (`semantic_verifier/smtlib.py` +
  `tests/test_smtlib.py`; DoD in the plan)

## Next

- [ ] A1.2 — Z3 process runner
- [ ] A1.3 — Model parser + replay
- [ ] F2.1 — `fixtures/` layout + regeneration script (can run parallel to
  A1; prerequisite of B1.1)

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-02 — F0 committed; TODO staleness guard added to pre-commit; Z3 5.0.0
installed. Next work item is A1.1.
