# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.6 - optional invariant-inference research**

## Next

- [ ] **A6.7 - semantic-extensions phase gate**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.5 added exact modular `modifies` frames, post-state reference
summaries, preservation of unlisted caller locations, schema v6 migration, the
immutable v5 archive, and a fully verified frame fixture; next is the isolated
CHC/Spacer invariant-inference research spike.