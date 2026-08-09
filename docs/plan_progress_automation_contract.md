# PLAN/PROGRESS/TODO automation contract

Status: frozen for F5.5 implementation.

## Authority

- `PLAN.md` defines stage identity, order, title, goal, and dependencies. It
  carries no completion status.
- `PROGRESS.md` is the append-only completion and partial-work ledger.
- `TODO.md` is a generated view of unfinished work. It is never an independent
  status authority and must not be edited by hand after F5.5.

## Parsing

1. A PLAN stage is declared once by either a level-four stage heading or a
   compact stage bullet. Its identifier is an uppercase program letter, a
   phase number, a dot, and a stage number.
2. A stage is complete only when PROGRESS contains an explicit heading for the
   same identifier whose terminal status contains `DONE`.
3. PARTIAL records never complete a stage. A later DONE record does.
4. Duplicate PLAN identifiers, malformed declarations, or a PROGRESS stage
   identifier absent from PLAN fail closed. Nothing is silently skipped.

## Generated TODO

1. TODO contains only unfinished PLAN stages in PLAN order.
2. The first unfinished stage is `Now`. Other unfinished stages in its phase
   are shown individually when the seven-item limit permits. Later phases are
   grouped by exact identifier range and list every included stage title.
3. TODO reports exact total, completed, and remaining counts and SHA-256 hashes
   of the PLAN and PROGRESS inputs.
4. Rendering is deterministic, location-independent, LF-only, and uses no
   clock, network, random value, model call, or repository branch name.
5. `check` compares exact bytes. `check --staged` reads PLAN, PROGRESS, and TODO
   from the Git index so unstaged working-tree content cannot mask drift.

## PROGRESS append operations

1. `record-done` accepts one existing unfinished stage, explicit ISO date,
   positive notes, limitation/blocker notes, and stage-specific evidence.
2. Before writing DONE, it runs the full unittest suite and requires the
   observed test count to equal `guardrails/test_baseline.txt`.
3. Verifier failure, count mismatch, invalid input, or stale TODO writes no
   PROGRESS or TODO bytes.
4. A successful DONE operation appends one canonical entry, preserves every
   previous PROGRESS byte, derives the next stage, and regenerates TODO.
5. `record-partial` requires an exact resume instruction, appends a canonical
   PARTIAL entry, completes no stage, and regenerates TODO. It never claims a
   verifier pass unless supplied evidence says so.
6. Neither operation edits PLAN or invents evidence. Stage-specific DoD
   evidence remains the operator's responsibility.

## Commit gate

The pre-commit hook runs the full suite, enforces the test-count ratchet and
PROGRESS requirement, then requires the staged TODO to equal the deterministic
view generated from staged PLAN and PROGRESS. The hook has no bypass in this
contract.
