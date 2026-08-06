# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A1.2 — Z3 process runner** (`semantic_verifier/z3_backend.py` +
  `tests/test_z3_backend.py`; DoD in the plan)

## Next

- [ ] A1.3 — Model parser + replay
- [ ] A1.4 — CheckerBackend interface and selection
- [ ] F2.1 — `fixtures/` layout + regeneration script (can run parallel to
  A1; prerequisite of B1.1)

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 — A1.1 completed with a deterministic, fail-closed SMT-LIB2
emitter and 9 focused tests. Next work item is A1.2.
