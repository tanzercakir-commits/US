# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **C4.0 - expand the enforcement ladder**

## Next

- [ ] **C4.1 - generate property-test skeletons for unproven obligations**
- [ ] **C4.2 - generate runtime assertions and the three-rung demo**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - C3.1 shipped the byte-stable, fail-closed C++26 contracts bridge.
The positive fixture verifies 6/6 obligations; the negative postcondition is
replayed as a violation. Text/JSON/IR are byte-identical across repeated runs,
and the reference suite is green at 366/366. Next is C4.0 expansion.