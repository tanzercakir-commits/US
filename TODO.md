# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.10 - unsigned integers and homogeneous QF_BV lane**

## Next

- [ ] **A6.11 - C++17 bitwise and shift operators**
- [ ] **A6.12 - fixed-width integer phase gate**
- [ ] **A6.2 - restricted arrays**
- [ ] **A6.3 - restricted value structs**
- [ ] **A6.4 - restricted proved references**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.9 added signed i64 lowering, exact promotions/narrowing,
width-specific safety VCs, literal-divisor C++17 arithmetic, replay, calls,
loops, and deterministic fixtures; next is the homogeneous unsigned QF_BV lane.