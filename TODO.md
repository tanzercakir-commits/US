# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B4.1 - CI semantic-verification gate mode**

## Next

- [ ] **B4.2 - editor and SARIF consumer integration**
- [ ] **C1.1 - offline AI contract proposal template**
- [ ] **C1.2 - proposal validation and acceptance workflow**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - B4.0 expanded the CI/adoption path into an opt-in semantic gate
with a separate deterministic baseline and a stable SARIF consumer stage.
CodeSkeptic remains green at 884/884 and the reference suite at 314/314. Next
is B4.1 implementation.