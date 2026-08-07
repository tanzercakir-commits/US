# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **D1.3 - freeze fact determinism and golden tests**

## Next

- [ ] **D2.1 - add world-model CLI queries**
- [ ] **D2.2 - expose world-model queries through MCP**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - D1.2 shipped two-pass Clang JSON-AST fact extraction for owned
symbols, def/use, direct calls, mutations, and derived purity. Unsupported
dispatch, locations, and forms remain explicit. The suite is green at 415/415.
Next is the deterministic fact corpus.
