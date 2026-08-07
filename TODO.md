# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **D1.1 - define the deterministic fact schema**

## Next

- [ ] **D1.2 - implement Clang fact extraction v0**
- [ ] **D1.3 - freeze fact determinism and golden tests**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - C4.2 shipped deterministic runtime guards and the combined
three-rung manifest. Static, property, and runtime artifacts share exact target
and contract identities; the original statuses remain unchanged. The suite is
green at 392/392. Next is the deterministic fact schema.
