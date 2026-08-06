# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.4 - restricted proved references**

## Next

- [ ] **A6.5 - modular calls and frame summaries**
- [ ] **A6.6 - optional invariant-inference research**
- [ ] **A6.7 - semantic-extensions phase gate**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.3 added exact value structs, field-sensitive SSA, QF_RECORD
datatypes, typed replay/cache evidence, schema v4 migration, the immutable v3
archive, and a fully verified struct fixture; next is restricted proved
references.