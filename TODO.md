# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A5.5 - exact structured merge-point compaction** (stage inserted by
  the A5.1 measurement decision)

## Next

- [ ] **A5.2 - persistent obligation-result cache**
- [ ] **A5.3 - deterministic resource budgets**
- [ ] **A5.4 - scaling phase gate**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A5.1 measured 2^N post-join growth with zero exact duplicates and
inserted A5.5 for exact guarded merge compaction before caching.
