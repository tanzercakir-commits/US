# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B2.2 - native deterministic referee and verification rule**

## Next

- [ ] **B2.3 - SARIF semantic-verification output**
- [ ] **B2.4 - MCP `verify_function` referee surface**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-06 - B2.1 added the pure native VC generator. All 14 obligation
payloads are byte-identical to the Python reference; CodeSkeptic is green at
840/840 and the reference suite at 314/314. Next is the deterministic referee.
