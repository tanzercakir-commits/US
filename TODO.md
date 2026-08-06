# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **B3.3 - contract package versioning and distribution**

## Next

- [ ] **B4.0 - CI and adoption path expansion**
- [ ] **B4.1 - CI semantic-verification gate mode**
- [ ] **B4.2 - editor and SARIF consumer integration**

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-06 - B3.2 added exact offline integer models for system-header
`std::abs`, `std::min`, and `std::max`, with value-only semantics and explicit
fail-closed boundaries. CodeSkeptic is green at 874/874 and the reference suite
at 314/314. Next is versioned offline contract packaging.
