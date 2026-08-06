# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B2.1 - native VC generator and obligation fixture equality**

## Next

- [ ] **B2.2 - native deterministic referee and verification rule**
- [ ] **B2.3 - SARIF semantic-verification output**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-06 - B2.0 selected the native C++17 VC/referee route, retained Z3 as
an unlinked subprocess, and expanded B2.1-B2.4. CodeSkeptic is green at 833/833
and the reference suite at 314/314. Next is obligation byte equality in B2.1.