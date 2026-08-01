# CodeSkeptic Semantic Verification Program — Session Protocol

C++ → Semantic IR → verification conditions → deterministic referee.
The AI proposes, the referee decides. This repo is the lab/reference
implementation (Python); the production track is CodeSkeptic (separate repo,
C++17).

## Language policy (D10, D11)

- All repository artifacts (code, docs, plan files, diagnostics, commit
  messages) are in **English**.
- Conversation with the project owner is in **Turkish**.
- Keep working narrative minimal — the owner reads the final report. In
  PROGRESS/TODO notes mark positives with `+` and negatives/blockers with `-`
  so status can be scanned quickly from a phone.

## Session start (in order, no skipping)

1. Read [TODO.md](TODO.md) → the active stage.
2. Read the last entries of [PROGRESS.md](PROGRESS.md) → what finished last,
   any `PARTIAL`.
3. Read only the active stage's phase in [PLAN.md](PLAN.md); follow its
   Goal/Output/DoD.
4. Baseline: `python -m unittest discover -s tests` (~5 s). If red, log to
   PROGRESS first, then diagnose.

## Session end

1. Run the stage's DoD commands; record results.
2. APPEND a templated entry to PROGRESS.md (never edit old entries).
3. Update TODO.md (remove done, pull next from plan, ≤7 items).
4. Commit with the stage ID in the message (e.g. `A1.2: z3 runner`).
5. If work is unfinished, write a `PARTIAL` entry: the exact file/command to
   resume from.

## Guardrails (enforced by git hooks — do not bypass)

- Activate once per clone: `git config core.hooksPath .githooks`
- pre-commit: runs the full suite; blocks on failure. Test-count ratchet:
  suite size must equal `guardrails/test_baseline.txt`; adding tests requires
  bumping the staged baseline deliberately.
- pre-commit: staged code changes require PROGRESS.md to be staged too.
- commit-msg: message must start with a stage ID (`A1.2: ...`) or an allowed
  prefix (`plan|docs|chore|fix|test|wip`).
- Never use `--no-verify` unless the owner explicitly approves.

## Invariants (summary of PLAN.md §3 — no exceptions)

- `unknown`/`unsupported` never promotes to `verified`.
- Unsupported constructs are never silently approximated (fail-closed).
- Every counterexample is replayed against the original obligation.
- No wall clock / randomness on the logic path; all serialization
  deterministic and sorted.
- The AI is never the referee.
- The test count never decreases; soundness tests are never weakened.
- PLAN.md carries no status and is never renumbered; "done" lives only in
  PROGRESS.md.
- If work would spill outside the stage's declared file set, STOP and add a
  TODO note.

## Technical notes

- Python ≥3.11; NO package dependencies (deliberate — preserve it).
- Clang required (JSON AST): `clang`/`clang++` on PATH or
  `SEMANTIC_VERIFIER_CLANG`. Tested with Clang 20.1.8.
- Z3 (from A1.2 on): `z3` on PATH or `SEMANTIC_VERIFIER_Z3`; NO library
  linking, subprocess + SMT-LIB2 text only. Not installed yet (see TODO).
- Run: `python -m semantic_verifier examples/vertical_slice.cpp
  --format text|json|ir`
- Exit codes: 0 = all verified, 1 = violation, 2 = unknown/unsupported,
  3 = solver/checker error.
- Code style: frozen dataclass value objects; ABC interfaces at swappable
  seams (`CheckerBackend`, frontend); composition over inheritance.
