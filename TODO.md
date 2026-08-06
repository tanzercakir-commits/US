# TODO — Active set

> Rules: at most 7 items. Stage details are NOT repeated here — look up the ID
> in [PLAN.md](PLAN.md). Updated at the end of every session: done items move
> to PROGRESS, next items are pulled from the plan. Goal-drift brake: before
> starting work not on this list, write it here first. Blockers are marked
> with `-` (D11).

## Now (active stage)

- [ ] **A6.8 - fixed-width type profile and schema v2**

## Next

- [ ] **A6.9 - signed int64 QF_LIA lane**
- [ ] **A6.10 - unsigned integers and homogeneous QF_BV lane**
- [ ] **A6.11 - C++17 bitwise and shift operators**
- [ ] **A6.12 - fixed-width integer phase gate**
- [ ] **A6.2 - restricted arrays**

## Blockers / open questions

- None. (Z3 5.0.0 installed 2026-08-02, user scope; `SEMANTIC_VERIFIER_Z3`
  User env var points to it. New shells pick the variable up automatically.)

## Last updated

2026-08-06 - A6.1 selected homogeneous per-obligation QF_LIA/QF_BV lowering,
a pinned C++17 fixed-width profile, and schema v2. Added A6.8-A6.12; next is the
type/profile and schema foundation.
