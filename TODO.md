# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- A7.4: admit the bounded stack/global pointer subset and generate explicit
  null, bounds, provenance, type, and lifetime obligations.

## Next

- A7.5: carry owned memory effects across direct project calls with
  fail-closed may/must-alias and frame summaries.

## Blockers / open questions

- None. Production work continues on `codex/semantic-verification-native` in
  `C:\tmp\CodeSkeptic-reference`.

## Last updated

2026-08-08 - A7.3 completed with proof-neutral Memory IR v7, exact value-only
migration evidence, and the 697-test baseline green; A7.4 is active.
