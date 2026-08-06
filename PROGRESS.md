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

## 2026-08-06 — A2.4: modular-call phase gate — DONE
+ Extended the modular example with an intentionally unchecked caller while
  preserving the verified `withdraw` → `validate` chain.
+ The negative variant returns a replayed concrete input; all operational and
  soundness-alarm categories remain zero.
- None.
Evidence: modular/recursion focused tests → 9/9; full suite → 121/121;
`python -m semantic_verifier examples/modular_calls.cpp --format text` →
6 verified, 1 violated (`candidate=-2147483648`), 0 unknown/unsupported/
solver_error, exit 1; commit: this commit.
Next: A3.1 (`cs: invariant` syntax).
## 2026-08-06 - A3.1: loop-invariant syntax - DONE
+ Added strict parsing for contiguous cs: invariant blocks immediately before
  Clang WhileStmt nodes, including machine-proposed invariant metadata.
+ Invariants use only caller-supplied in-scope symbols, require boolean
  expressions, and cannot attach to non-while statements.
+ Refactored comment-block collection without changing function-contract
  parsing; added four focused tests and advanced the ratchet from 121 to 125.
- None.
Evidence: python -m unittest tests.test_contracts -> 8/8; full suite ->
125/125; git diff --check -> clean; commit: this commit.
Next: A3.2 (while lowering and loop-modified-variable havoc).
## 2026-08-06 - A3.2: while lowering and havoc - DONE
+ Added owned loop IR with invariant contracts, a one-iteration body, and
  deterministic entry/head/back-edge/exit SSA state for each modified variable.
+ Loop heads and exits are explicit havoc states; nested branch assignments are
  included while unchanged variables retain their existing SSA names.
+ Serialization, human-readable dumps, expression traversal, recursive-call
  discovery, and fail-closed pre-A3.3 VC handling now understand loop nodes.
+ Replaced the obsolete unreachable-WhileStmt boundary fixture with DoStmt and
  added two focused lowering tests; ratchet advanced from 125 to 127.
- Loop VC generation intentionally remains unsupported until A3.3.
Evidence: lowering/verification focused tests -> 22/22; deterministic loop IR
dump -> byte-identical; full suite -> 127/127; compileall and diff check ->
clean; commit: this commit.
Next: A3.3 (loop-invariant VC triple).
## 2026-08-06 - A3.3: loop-invariant VC triple - DONE
+ Loop verification now proves each invariant at entry and after one arbitrary
  iteration from a bounded, invariant-constrained head havoc state.
+ Post-loop paths use an independent bounded exit havoc state constrained only
  by all invariants and the negated condition; body-path facts are not leaked.
+ Missing invariants are detected before path walking and fail closed for the
  whole function; nested loops and loop-body calls remain structurally visible.
+ Added five Z3/cross-check soundness tests, including replayed entry and
  preservation counterexamples; ratchet advanced from 127 to 132.
- None.
Evidence: loop/legacy verification tests -> 17/17; count-loop entry,
preservation, overflow, and postcondition obligations all verified under both
backends; full suite -> 132/132; compileall and diff check -> clean; commit:
this commit.
Next: A3.4 (explicit termination NON-GOAL record).
## 2026-08-06 - A3.4: termination NON-GOAL record - DONE
+ Every lowered loop now carries termination=non_goal in Semantic IR and JSON.
+ Verification reports retain a machine-readable loop_termination non-goal
  record even when Semantic IR is omitted from JSON.
+ Text output explicitly states that termination is unchecked and verified loop
  obligations establish partial correctness only.
+ Updated the prototype scope/limitations and added one all-output regression
  test; ratchet advanced from 132 to 133.
- Termination arguments and variants remain deliberately out of scope.
Evidence: loop/determinism focused tests -> 11/11; full suite -> 133/133;
compileall and diff check -> clean; commit: this commit.
Next: A3.5 (loop phase gate).
## 2026-08-06 - A3.5: loop phase gate - DONE
+ Added a bounded sum(0..n) example whose linear invariant proves entry,
  preservation, int32 safety, and the declared result bounds.
+ Added source-identical missing-invariant and non-inductive-invariant variants.
+ The correct example is fully verified, the missing annotation fails closed,
  and the wrong invariant returns a replayed preservation counterexample.
+ Added an end-to-end fixture gate test; ratchet advanced from 133 to 134.
- Exact unbounded triangular-number specifications are outside QF_LIA; the
  example deliberately verifies linear safety/result bounds for 0 <= n <= 10.
Evidence: correct CLI -> 6 verified, no alarms, exit 0; missing-invariant CLI ->
1 unsupported, exit 2; wrong-invariant CLI -> 1 violated with replayed
counterexample (n=2, i#1=1, total#2=3), exit 1; loop tests -> 7/7; full suite
-> 134/134; commit: this commit.
Next: F2.1 (fixture layout and regeneration script).
## 2026-08-06 - F2.1: fixture corpus and regeneration - DONE
+ Added a versioned fixture manifest with five self-contained C++ cases spanning
  violations, modular calls, verified loops, missing invariants, and wrong
  invariants.
+ Committed ten canonical artifacts: deterministic human-readable Semantic IR
  and full sorted JSON reports for every case.
+ Added a stdlib-only regeneration tool with summary drift detection, safe
  relative manifest paths, --check, --output-dir, and explicit Z3 selection.
+ Fixture inputs and goldens are forced to LF through .gitattributes so clean
  Windows checkouts preserve the byte contract.
+ Added two infrastructure tests; ratchet advanced from 134 to 136.
- None.
Evidence: fixture regeneration -> 10 artifacts; regeneration --check from an
unrelated working directory -> current; fixture tests -> 2/2; full suite ->
136/136; compileall and diff check -> clean; commit: this commit.
Next: F2.2 (determinism CI job).
## 2026-08-06 - F2.2: determinism CI gate - DONE
+ Added a least-privilege Ubuntu CI job that installs Clang/Z3, runs the full
  suite, regenerates fixtures in two independent directories, and recursively
  compares every byte.
+ The workflow uses the current Node 24 action majors (checkout v6 and
  setup-python v6) with an explicit Python 3.11 runtime.
+ Added a two-process local regression test for the same byte-identity contract;
  ratchet advanced from 136 to 137.
- The hosted workflow itself cannot be executed locally; its exact commands are
  covered by the repository tests and local fixture tool.
Evidence: fixture infrastructure tests -> 3/3 including two-process byte
identity; full suite -> 137/137; compileall and diff check -> clean; commit:
this commit.
Next: F3.1 (documentation phase-gate upkeep).
## 2026-08-06 - F3.1: phase-gate documentation upkeep - DONE
+ Reclassified current capabilities into explicit implemented, partial, and
  proposed sections through the completed A1-A3 and F2 gates.
+ Documented Z3/cross-check semantics, fail-closed SMT emission, replay, modular
  call havoc/ensures, recursion rejection, loop VCs, and termination non-goals.
+ Updated the supported/unsupported boundary, runtime requirements, examples,
  fixture commands, 137-test scope, limitations, and native-adapter next step.
- None.
Evidence: stale-capability text scan -> clean; local documentation links ->
valid; full suite -> 137/137; diff check -> clean; commit: this commit.
Next: F3.2 (result taxonomy and schema reference).
## 2026-08-06 - F3.2: result and schema reference - DONE
+ Added a field-level v0 reference for the report envelope, five result statuses,
  CLI precedence, obligations/modes/kinds, counterexamples, and non-goals.
+ Documented every shared expression/location value and Semantic IR module,
  function, symbol, contract, node, and loop-variable field.
+ Defined omission rules, one-to-one obligation/result linkage, replay evidence,
  stable ordering, UTF-8/newline behavior, and fixture byte contracts.
+ Linked the reference from the main prototype document.
- The v0 compatibility/change policy remains intentionally deferred to F4.1.
Evidence: committed fixture envelope/status keys -> all present in reference;
local documentation links -> valid; full suite -> 137/137; diff check -> clean;
commit: this commit.
Next: F3.3 (adoption guide).
## 2026-08-06 - F3.3: adoption guide - DONE
+ Added a fail-closed rollout guide from observation-only CI through a frozen
  pilot subset, reviewed contracts/invariants, controlled gating, and semantic
  feature expansion.
+ Documented CI exit-code preservation, per-status triage, counterexample data
  handling, schema/fixture discipline, and the native CodeSkeptic adapter seam.
+ Added a completion checklist that keeps non-goals, unsupported ownership,
  compatibility review, and the deterministic referee explicit.
+ Refreshed README capability/test counts and linked all documentation entry
  points; linked the guide from the prototype assessment.
- None.
Evidence: documentation links and code fences -> valid; full suite -> 137/137;
diff check -> clean; commit: this commit.
Next: F4.1 (schema version policy).
## 2026-08-06 - F4.1: schema version policy - DONE
+ Froze codeskeptic.semantic-verification/v0 as the first field-reference and
  fixture-backed compatibility baseline.
+ Defined compatible additive changes and mandatory major triggers based on
  semantic safety, not merely JSON field additivity.
+ Recorded why pre-freeze A2 result calls and A3 loop/non-goal fields remain in
  v0 while equivalent post-freeze reinterpretations require v1.
+ Defined fail-closed consumer rules and a v0-to-v1 procedure that preserves old
  fixture bytes under a versioned archive and regenerates the new corpus twice.
+ Linked the policy from README, schema reference, adoption guide, and prototype
  architecture.
- No v1 proposal exists yet, so no migration tool or schema bump was created.
Evidence: all golden report/IR schema values -> matching v0; documentation links
and code fences -> valid; full suite -> 137/137; diff check -> clean; commit:
this commit.
Next: F4.2 (CHANGELOG discipline).
