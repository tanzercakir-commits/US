# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **C3.1 - accept standard syntax through the fail-closed bridge**

## Next

- [ ] **C4.0 - expand the enforcement ladder**
- [ ] **C4.1 - generate property-test skeletons for unproven obligations**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - C3.0 froze the P2900 mapping and compiler evidence. GCC 16 reports
experimental support; Clang reports P2900 unsupported, and local Clang 20.1.8
rejects the feature. C3.1 is fully scoped as a byte-stable fail-closed bridge.
The reference suite is green at 355/355.