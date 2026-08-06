# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.12 - fixed-width integer phase gate**

## Next

- [ ] **A6.2 - restricted arrays**
- [ ] **A6.3 - restricted value structs**
- [ ] **A6.4 - restricted proved references**
- [ ] **A6.5 - modular calls and frame summaries**
- [ ] **A6.6 - optional invariant-inference research**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.11 added exact C++17 bitwise/shift semantics, homogeneous QF_BV
encoding, shift-count and signed-left-shift safety, pinned arithmetic right
shift, replay, and deterministic fixtures; next is the integer phase gate.