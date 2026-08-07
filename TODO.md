# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **C4.2 - generate runtime assertions and the three-rung demo**

## Next

- [ ] **D1.1 - define the deterministic fact schema**
- [ ] **D1.2 - implement Clang fact extraction v0**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - C4.1 shipped deterministic property-test skeleton generation.
The affine fixture preserves verified=1 and unsupported=2 while producing one
deduplicated, compilable, generated-unexecuted target. The suite is green at
381/381. Next is the runtime-guard rung and combined demo.