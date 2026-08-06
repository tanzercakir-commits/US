# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B1.5 - arithmetic contract parsing and ContractInfo adaptation**

## Next

- [ ] **B1.4 - native/Python byte-comparison harness**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-06 - B1.3 added exact, owned ASTContext lowering for the native scalar
subset; CodeSkeptic is green at 824/824 and the reference suite at 314/314.
B1.5 comes before B1.4 because contract-bearing fixture equality requires the
native contract adaptation.