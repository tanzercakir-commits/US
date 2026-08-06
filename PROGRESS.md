# PROGRESS — Append-only ledger

> Rules: entries are ONLY appended; existing entries are never deleted or
> edited (typo fixes excepted). This file is the single source of truth for
> "done" — PLAN.md carries no status. Append an entry at the end of every
> session. Keep narrative minimal; use `+` for positives, `-` for
> negatives/blockers (D11).

## Entry template

```
## YYYY-MM-DD — <stage ID or session name> — DONE | PARTIAL | NOTE
+ <what went well / what was delivered>
- <problems, blockers, debts>
Evidence: <commands run + observed results; test count; commit hash>
Next: <for PARTIAL: the exact file/command to resume from>
```

---

## (before this session) — Codex prototype — DONE
+ Isolated vertical slice: Clang JSON AST → Semantic IR → VC → deterministic
  affine checker; `cs:` contracts; result taxonomy; design document.
+ CodeSkeptic investigated read-only in a separate clone (findings in
  `docs/semantic_verification_prototype.md`); this repo is NOT CodeSkeptic.
Evidence: commits `4326583` (prototype, 25 files, ~4.2k lines) + `c6ddca5`
(docs); 64 unit tests.

## 2026-08-02 — Independent evaluation session — DONE
+ Core files audited line by line (checker/vc/model/contracts/frontend/
  pipeline); claims verified by execution.
+ Fail-closed behavior confirmed adversarially (`+=`, nested call, `while`,
  ternary, shadowing, `unsigned` → all correctly `unsupported`; disjoint-scope
  name reuse correctly accepted).
- Weaknesses recorded and routed into the plan: prover strength (→A1), call
  returns (→A2), loops (→A3), counterexample noise (→A4), Clang JSON bridge /
  single TU (→B1).
Evidence: `python -m unittest discover -s tests` → 64/64 (4.5 s);
`python -m semantic_verifier examples/vertical_slice.cpp` matches the design
doc (9 verified, 2 violated with real counterexamples, 1 honest unknown).
No code changes. Basis of decision D1 (take over).

## 2026-08-02 — Discussion sessions (vision + problem model) — NOTE
+ Thesis: not "a logic language AI understands" but "a logic layer that
  catches AI's mistakes".
+ Annotation value = enforcement class (ladder: docs → runtime → best-effort
  → proof).
+ Failure-layer model: context 35%, grounding 25%, goals 15%, intent 15%,
  capability 10%; solution list 1a–5c.
+ Bitter-lesson synthesis: the referee is a clean-training-data factory.
Outcome: PLAN.md §1 and the program map derive from these sessions.

## 2026-08-02 — F0.1: plan-system files — DONE
+ PLAN.md (programs A–F, ~90 stages, decision log D1–D11, constitution,
  rolling wave), PROGRESS.md, TODO.md, CLAUDE.md created.
+ Decisions: take over (D1), Python lab + C++ production + JSON schema bridge
  (D2), OOP discipline (D3), subprocess SMT (D4).
- Files were first authored in Turkish, then rewritten in English per the
  owner's language policy (D10) before the first commit.
Evidence: four files at repo root; baseline 64/64 green this session.

## 2026-08-02 — F0.2: guardrails — DONE
+ `.githooks/pre-commit`: full suite on every commit + test-count ratchet
  (`guardrails/test_baseline.txt` = 64) + PROGRESS.md required when code is
  staged.
+ `.githooks/commit-msg`: stage ID or allowed prefix required.
+ `.gitattributes` (LF for hooks), README workflow section,
  `core.hooksPath` activated locally.
- Z3 is NOT installed on this machine (`z3` not on PATH) — blocker for A1.2,
  not for A1.1. Install decision pending (GitHub release zip +
  `SEMANTIC_VERIFIER_Z3`, or a package manager).
- Hooks are per-clone: new clones must run
  `git config core.hooksPath .githooks` once (documented in README/CLAUDE).
Evidence: hook scripts in `.githooks/`; activation verified by the F0.3
commit passing through them.

## 2026-08-02 — F0.3: first commit of the plan system — DONE
+ Plan system + guardrails committed on branch
  `feature/semantic-verification-prototype`.
Evidence: this commit (`F0: bootstrap plan system and guardrails`); pre-commit
hook ran the suite (64/64) during the commit.
Next: A1.1 (SMT-LIB2 emitter) — tomorrow's big start.

## 2026-08-02 — chore: TODO staleness guard + Z3 install — DONE
+ pre-commit extended: code commits now require TODO.md either staged or
  already carrying today's date (staleness guard). PROGRESS stays enforced
  per commit; TODO freshness enforced per working day.
+ Z3 5.0.0 (x64-win) installed user-scope at
  %LOCALAPPDATA%\Programs\z3-5.0.0-x64-win\bin\z3.exe;
  SEMANTIC_VERIFIER_Z3 User env var set. A1.2 blocker cleared.
- PATH deliberately untouched (setx truncation risk); discovery contract is
  the env var + known locations.
Evidence: `z3 --version` → "Z3 version 5.0.0 - 64 bit"; owner approved the
install in-session.
Next: A1.1 (SMT-LIB2 emitter).

## 2026-08-06 — A1.1: SMT-LIB2 emitter — DONE
+ Deterministic QF_LIA emission covers validity and satisfiability queries,
  sorted declarations, int/bool expressions, and constant multiplication.
+ Reversible collision-free symbol encoding preserves readable SSA names
  (`y#0` → `y_v0`); malformed and unsupported formulas fail closed.
+ Added 9 focused tests; test-count guardrail advanced from 64 to 73.
- None.
Evidence: `python -m unittest tests.test_smtlib` → 9/9; full suite → 73/73;
`python -m compileall -q semantic_verifier tests` → success; emitted smoke
query on Z3 5.0.0 → `unsat`, exit 0; commit: this commit.
Next: A1.2 (Z3 process runner).

## 2026-08-06 — A1.2: Z3 process runner — DONE
+ Added deterministic Z3 discovery: explicit path, environment, PATH, then
  platform-known locations.
+ Added bounded subprocess execution with fixed seeds, disabled parallelism,
  and exact `sat`/`unsat`/`unknown`/timeout/crash result-taxonomy mapping.
+ Missing or unlaunchable Z3 degrades to `solver_error` without terminating
  the runner; added 13 tests and advanced the ratchet from 73 to 86.
- None.
Evidence: `python -m unittest tests.test_z3_backend` → 13/13 (real Z3 process
included); full suite → 86/86; `python -m compileall -q semantic_verifier
tests` → success; commit: this commit.
Next: A1.3 (model parser + replay).

## 2026-08-06 — A1.3: model parser + replay — DONE
+ Added a strict S-expression parser for zero-arity Z3 int/bool models with
  reversible source-name recovery and exact binding/sort validation.
+ Countermodels are obtained only after an initial `sat`, then replayed against
  the original assumptions and conclusion before a violation is reported.
+ Corrupt, incomplete, malformed, or non-replaying models become
  `solver_error`; added 10 tests and advanced the ratchet from 86 to 96.
- None.
Evidence: `python -m unittest tests.test_z3_backend` → 23/23; corrupt-model
injection test → `solver_error`; real Z3 violation returned replayed bindings;
full suite → 96/96; direct Z3 check of `vertical_slice.cpp` obligations →
10 verified, 2 violated, 0 unknown/unsupported/solver_error; commit: this commit.
Next: A1.4 (CheckerBackend interface and selection).

## 2026-08-06 — A1.4: backend interface and selection — DONE
+ Added the `CheckerBackend` ABC, adapted the affine checker, and added Z3 and
  deterministic affine/Z3 cross-check backends.
+ Definitive backend disagreement produces a `solver_error` soundness alarm;
  unsupported and operational failures remain fail-closed.
+ Added CLI `--backend=affine|z3|both`, Z3 path/timeout options, and 10 tests;
  advanced the ratchet from 96 to 106.
- None.
Evidence: `python -m unittest tests.test_backend` → 10/10; full suite →
106/106; `python -m semantic_verifier examples/vertical_slice.cpp --backend
both --format text` → 10 verified, 2 violated, 0 unknown/unsupported/
solver_error, exit 1 as expected; commit: this commit.
Next: A1.5 (solver decision document).

## 2026-08-06 — A1.5: solver decision document — DONE
+ Added `docs/solver_decision.md`: MIT license, subprocess decision, QF_LIA
  boundary, Windows/Linux/macOS packaging, discovery, timeout, determinism,
  failure taxonomy, model serialization, and mandatory replay.
+ Linked the decision record from README; refreshed backend usage and the
  current 106-test count.
- None.
Evidence: document exists; README local link resolves; license/release and
parameter claims checked against official Z3 project/guide sources; full suite
→ 106/106; commit: this commit.
Next: A1.6 (phase gate: golden tests).

## 2026-08-06 — A1.6: Z3 phase gate — DONE
+ Added three golden regressions: repeated Z3 JSON, repeated cross-check text,
  and `transitive_chain` permanently `verified` under Z3.
+ Aligned the CLI default with the phase DoD: `both` is now the default;
  dependency-free operation remains available through `--backend affine`.
+ A1 exceeded its ≥85 target with 109 tests; ratchet advanced from 106 to 109.
- None.
Evidence: `python -m unittest tests.test_determinism` → 5/5; full suite →
109/109; `python -m semantic_verifier examples/vertical_slice.cpp --format
text` → 10 verified, 2 violated, 0 unknown/unsupported/solver_error, exit 1
(expected for real violations); repeated Z3/cross-check outputs byte-identical;
commit: this commit.
Next: A2.1 (IR call-with-result node).

## 2026-08-06 — A2.1: call-with-result IR — DONE
+ Extended call IR with an explicit result type and versioned target.
+ Lowered only `int q = f(x);` and `q = f(x);` into result-bearing call nodes;
  assignment advances the target SSA version.
+ Added three tests covering both forms and the fail-closed boundary for calls
  nested in return/arithmetic/arguments plus non-int result assignment.
- None.
Evidence: `python -m unittest tests.test_lowering` → 8/8; full suite →
112/112; `python -m compileall -q semantic_verifier tests` → success; ratchet
advanced from 109 to 112; commit: this commit.
Next: A2.2 (VC havoc + assumed ensures).

## 2026-08-06 — A2.2: havoc + assumed ensures — DONE
+ Result-bearing calls now leave the fresh SSA target unconstrained except for
  int32 bounds, then assume deduplicated callee `ensures` after parameter and
  `result` substitution.
+ Existing call `requires` obligations remain evaluated before result facts;
  ensures-only external contracts are now recognized as contracted calls.
+ Added `examples/modular_calls.cpp` and five focused tests; ratchet advanced
  from 112 to 117.
- None.
Evidence: `python -m unittest tests.test_modular_calls` → 5/5; full suite →
117/117; `python -m semantic_verifier examples/modular_calls.cpp --format
text` → 6 verified, 0 violated/unknown/unsupported/solver_error, exit 0;
commit: this commit.
Next: A2.3 (recursion policy).

## 2026-08-06 — A2.3: recursion policy — DONE
+ Added deterministic IR call-graph reachability/SCC analysis across nested
  branch bodies and overload-safe function keys.
+ Direct and mutual recursive components now fail closed as `unsupported` with
  explicit members and the missing decreasing-measure policy.
+ Added four tests; acyclic overload and modular-chain behavior remains green;
  ratchet advanced from 117 to 121.
- None.
Evidence: `python -m unittest tests.test_recursion_policy` → 4/4; direct and
mutual examples explicitly rejected; full suite → 121/121; commit: this commit.
Next: A2.4 (phase gate).
