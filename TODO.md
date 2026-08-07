# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **C3.0 - research and expand the C++26 contracts bridge**

## Next

- [ ] **C3.1 - accept standard syntax when compiler support matures**
- [ ] **C4.0 - expand the enforcement ladder**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - C2.2 shipped the guarded-absolute contract-first pilot. The
ordinary referee verifies 6/6 obligations, the seeded mismatch deterministically
fails by replayed postcondition violation, and the full suite is green at
351/351. Next is the C3.0 C++26 contracts research and rolling-wave expansion.