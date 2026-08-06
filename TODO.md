# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **F2.2 - determinism CI job** (suite plus two independent fixture
  generations with byte comparison)

## Next

- [ ] F3.1 - keep implemented/partial/proposed documentation current
## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - F2.1 completed: five fixture cases regenerate to ten canonical
artifacts and pass --check from any working directory. Next is F2.2.
