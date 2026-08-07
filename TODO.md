# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **D3.1 - define allowed and forbidden dependency edges**

## Next

- [ ] **D3.2 - enforce architectural rules with SARIF output**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-07 - F2.3 raised only the fixture subprocess wait budget from 30 to
120 seconds after a measured ~59-second cold run; all byte and determinism
assertions remain intact. Fixture tests are 3/3 and the suite is 454/454.
D3.1 resumes next.
