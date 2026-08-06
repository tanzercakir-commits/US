# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B1.3 - native ASTContext to Semantic IR lowering**

## Next

- [ ] **B1.4 - native/Python byte-comparison harness**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-06 - B1.2 added the standalone Clang/reporter-independent production
SemanticIR module and five tests; CodeSkeptic is green at 816/816. Next is
native ASTContext lowering for the exact v0 subset.