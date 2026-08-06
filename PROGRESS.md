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
## 2026-08-06 - F4.2: CHANGELOG discipline - DONE
+ Added a consumer-facing CHANGELOG with an Unreleased workflow, allowed
  categories, stage-ID linkage, append-only releases, and schema migration rules.
+ Recorded the complete 0.1.0 baseline, including the frozen v0 consumer
  contract and migration expectations.
+ Added guardrail tests that require the current project version release heading,
  current schema identity, migration section, and policy link; ratchet advanced
  from 137 to 139.
+ Linked CHANGELOG from README and linked its migration requirement from the
  schema policy.
- None.
Evidence: changelog guardrail tests -> 2/2; documentation links/code fences ->
valid; full suite -> 139/139; diff check -> clean; commit: this commit.
Next: A4.1 (deterministic counterexample model minimization).
## 2026-08-06 - A4.1: deterministic counterexample model minimization - DONE
+ Preserved mandatory complete-model replay before any public evidence
  reduction in both the affine and Z3 backends.
+ Added deterministic greedy elimination in sorted Semantic IR variable order;
  a binding is removed only when exact reasoning proves that the original
  assumptions plus the retained core force the negated conclusion.
+ Kept minimization fail-safe: unsupported emission, solver uncertainty, or a
  failed proof retains the candidate binding without weakening the violation.
+ Migrated the report/Semantic IR producer to
  codeskeptic.semantic-verification/v1 because counterexample changed from a
  complete replay model to a possibly empty sufficient binding core.
+ Preserved all 16 pre-migration corpus files byte-for-byte under
  fixtures/versions/v0 and regenerated the 10 current v1 artifacts twice with
  identical SHA-256 content.
+ Added a fail-closed schema compatibility gate plus tests rejecting unknown and
  mixed report/IR majors; documented consumer migration, rejected v0-compatible
  alternatives, the Unreleased migration window, and the absent legacy reader.
+ Added affine/Z3 quality regressions for the noisy call case: input=0 remains
  while irrelevant x is eliminated; ratchet advanced from 139 to 145.
- None.
Evidence: focused A4.1/schema tests -> 20/20; v0 Git-blob comparison -> 16/16;
independent current-corpus generation -> 10/10 byte-identical; fixture check ->
10/10 current; full suite -> 145/145; diff check -> clean; commit: this commit.
Next: A4.2 (counterexample relevance projection).
## 2026-08-06 - A4.2: counterexample relevance projection - DONE
+ Added a deterministic variable-cone analysis seeded by the obligation
  conclusion and closed transitively through variable co-occurrence in
  assumptions.
+ Projected complete replayed models through the shared affine/Z3 evidence path
  before A4.1 greedy minimization, while retaining mandatory full-model replay.
+ Kept the projection conservative for compound assumptions and independent of
  solver minimization success; disconnected variables cannot leak into the
  public core even when the exact removal prover is inconclusive.
+ Added direct regressions for transitive x-y-z relevance and disconnected noise
  removal; ratchet advanced from 145 to 147.
+ Updated the schema, solver, prototype, adoption, and changelog documentation;
  the counterexample field remains compatible with the existing v1 partial-core
  contract.
+ Confirmed all 10 current fixture artifacts remain byte-identical.
- None.
Evidence: A4 counterexample-quality tests -> 8/8; fixture check -> 10/10 current
with no byte diff; full suite -> 147/147; diff check -> clean; commit: this
commit.
Next: A4.3 (counterexample trace explanation).
## 2026-08-06 - A4.3: counterexample trace explanation - DONE
+ Added internal immutable TraceStep metadata with a versioned condition, taken
  direction, deterministic kind, and exact source location.
+ Carried true/false branch decisions through VC path state in outer-to-inner
  order and attached them only to violated results; proof obligations and
  referee decisions remain independent of the diagnostic trace.
+ Preserved traces through affine, Z3, and definitive cross-check selection
  while suppressing them for verified, unknown, unsupported, and solver-error
  outcomes.
+ Added an optional machine-readable result trace and deterministic human text
  in the form "when branch condition ... is true/false at file:line:column".
+ Documented the field as a compatible v1 diagnostic addition: consumers may
  ignore it safely, and all 10 existing current fixtures remain byte-identical.
+ Added true/false direction, JSON shape, human rendering, cross-check, Z3
  propagation, and replay-error suppression regressions; ratchet advanced from
  147 to 149.
- None.
Evidence: focused trace/backend tests -> 12/12; fixture check -> 10/10 current
with no byte diff; full suite -> 149/149; diff check -> clean; commit: this
commit.
Next: A5.0 (expand the scaling phase into concrete stages).
## 2026-08-06 - A5.0: scaling phase expansion - DONE
+ Replaced the coarse scaling headings with A5.1–A5.4 stages carrying explicit
  Goal, Output, DoD, and dependency contracts.
+ Made scaling subordinate to proof semantics: optimization misses, malformed
  cache data, inconclusive path reduction, timeout, and budget exhaustion can
  never produce verified.
+ Separated path-growth measurement/architecture choice from production VC
  rewriting and required the spike to add any chosen implementation stage
  before the phase gate.
+ Defined a semantic-keyed persistent cache with safe recomputation and a
  deterministic work-unit file budget alongside the existing solver timeout.
+ Added a phase gate comparing cached/uncached report bytes and requiring
  repeated budget/probe determinism plus full-suite and fixture evidence.
- None.
Evidence: A5 structure/field review -> A5.1–A5.4 complete; local documentation
links -> valid via full suite; baseline/full suite -> 149/149; diff check ->
clean; commit: this commit.
Next: A5.1 (path-growth measurement and merge-point VC decision spike).
## 2026-08-06 - A5.1: path-growth measurement and merge decision - DONE
+ Added a solver-free deterministic probe using the ordinary Clang, lowering,
  and VC path plus stable sorted JSON under codeskeptic.path-scaling-probe/v0.
+ Measured 1/2/4/8 sequential empty diamonds: 2/4/16/256 post-join assertion
  obligations from 114/148/216/352 source bytes and 3/4/6/10 IR nodes.
+ Confirmed every measured obligation has a unique exact semantic key, so exact
  duplicate deletion gives zero reduction on the baseline.
+ Defined the SHA-256 logical key boundary and documented why branch dropping,
  unproved assumption subsumption, source/ID hashing, affine exhaustion, eager
  trace alternatives, and a general BDD/SMT simplifier are rejected shortcuts.
+ Chose exact factored disjunction at structured joins with compact guarded trace
  templates; inserted A5.5 before caching with a 1/1/1/1 acceptance target.
+ Added probe determinism, exponential-count, key-normalization, and decision
  guardrails; expanded the declared stage file set before required ratchet/count
  updates and advanced the suite from 149 to 152.
- None.
Evidence: path-scaling tests -> 3/3; two external probe renders -> byte-identical
SHA-256 f1ce3d1b528273af2df8052f92d0af9cb69bd51f6d1fb710bb0aedd425303f59;
full suite -> 152/152; fixture check -> 10/10 current; diff check -> clean;
commit: this commit.
Next: A5.5 (exact structured merge-point compaction).
## 2026-08-06 - A5.5: exact structured merge-point compaction - DONE
+ Compacted every multi-state structured branch join into common assumptions
  plus one exact source-ordered disjunction of residual state conjunctions.
+ Deduplicated only structurally identical assumption sets; no path, assignment,
  or branch-specific merge equality is approximated or silently discarded.
+ Replaced eagerly copied resolved paths with compact guarded TraceTemplate
  provenance and resolved true/false TraceStep values only after complete model
  replay; resolution failure is solver_error before public evidence.
+ Added deterministic affine case splitting for disjunctive assumptions, which
  restored pre-compaction exact proofs without treating finite search as proof.
+ Reduced the 1/2/4/8-diamond probe from 2/4/16/256 post-join obligations to
  1/1/1/1 while leaving source, IR, expected path, and assumption-depth metrics
  unchanged.
+ Matched compact/unmerged Z3 verdicts for nested and assignment-bearing
  diamonds; forced both post-join trace directions and guarded failure behavior.
+ Existing 10 fixture artifacts remain byte-identical; expanded the declared
  file set before ratchet/count updates and advanced tests from 152 to 155.
- None.
Evidence: path-scaling tests -> 5/5; focused merge/trace/backend tests -> 18/18;
probe acceptance -> 1/1/1/1; full suite -> 155/155; fixture check -> 10/10
current; diff check -> clean; commit: this commit.
Next: A5.2 (persistent obligation-result cache).

## 2026-08-06 - A5.2: persistent obligation-result cache - DONE
+ Added an opt-in deterministic JSON cache with exact SHA-256 keys over the
  report/key schemas, canonical conjunction/query content, backend identity,
  implementation policy, nested cross-check identities, and configuration.
+ Reconstructed every hit with the current obligation ID, owner/kind, primary
  source location, and source-mapped trace locations; trace semantics must match
  before cached directions are reusable.
+ Kept cache I/O outside referee status: missing, stale, malformed, unknown, or
  unwritable data recomputes normally, and solver_error is never stored/reused.
+ Integrated cache selection into the backend interface, pipeline constructor,
  Z3 runner identity, cross-check identity, and the CLI as `--cache PATH`.
+ Proved warm/cold pipeline report byte identity with zero warm backend calls,
  one-query-only invalidation, schema/backend/config misses, current metadata
  reconstruction, malformed-file/entry recovery, and solver-error retry.
+ Documented the independent cache/key schemas, exact trust boundary, CI use,
  untrusted-cache warning, and counterexample retention sensitivity.
+ Expanded the declared stage file set before required consumer/count/ledger
  updates and advanced the test ratchet from 155 to 162.
- None.
Evidence: cache tests -> 7/7; CLI cold/warm affine reports -> byte-identical with
matching exit 1; full suite -> 162/162; fixture check -> 10/10 current; diff
check -> clean; commit: this commit.
Next: A5.3 (deterministic resource budgets).

## 2026-08-06 - A5.3: deterministic resource budgets - DONE
+ Added frozen validated SolverTimeout and FileCheckBudget values: solver bounds
  are positive finite seconds; file bounds are non-negative checks or unlimited.
+ Counted one source-ordered unit for each started supported top-level obligation
  and returned explicit unknown for every unstarted obligation after exhaustion.
+ Preserved unsupported results without consuming supported units, reset the
  allowance at every file/check_all boundary, and kept earlier results intact.
+ Composed the file budget outside cache and cross-check layers, so warm entries
  cannot bypass a lower limit and both referees consume one top-level unit.
+ Kept initial and countermodel-request Z3 timeouts unknown; cross-check resource
  exhaustion cannot be strengthened to verified, while already replayed
  violations survive inconclusive minimization work.
+ Added `--max-checks N`, centralized existing solver-timeout validation, and
  documented zero/unlimited boundaries, unit accounting, exit behavior, and CI.
+ Expanded the declared stage file set before required count/ledger updates and
  advanced the test ratchet from 162 to 173.
- None.
Evidence: budget tests -> 11/11; injected initial/model-request timeout and
cross-check guards -> green; repeated CLI budget reports -> byte-identical,
exit 2, 10 unknown; full suite -> 173/173; fixture check -> 10/10 current; diff
check -> clean; commit: this commit.
Next: A5.4 (scaling phase gate).

## 2026-08-06 - A5.4: scaling phase gate - DONE
+ Added a committed four-diamond assignment scaling slice with contracts,
  arithmetic safety, assertion, and postcondition coverage; both backends verify
  all 11 generated obligations.
+ Added a deterministic sorted-JSON executable gate over uncached/cache-fill/warm
  reports, repeated file budgets, and the independent 1/2/4/8 path probe.
+ Froze identical default cross-check report SHA-256
  13f7aaf4d2b780cef3affb0b4aeeb22b326d86d36bab3883d6bd55e818226939
  with 11 uncached/fill calls and zero warm calls.
+ Froze identical max_checks=5 report SHA-256
  1ea0e0f93fdd4b915bf9f73dec88dbf581947f9c5c1f41a167bd5e7050570ee6
  with five verified, six unknown, and five backend calls on both runs.
+ Reconfirmed the merge target at 1/1/1/1 obligations while representing
  2/4/16/256 paths, with no timing or temporary-path evidence.
+ Added the scaling operations/failure runbook and deterministic gate tests;
  expanded the stage file set before ratchet updates from 173 to 175.
- None.
Evidence: scaling-gate tests -> 2/2; two default cross-check gate renders ->
byte-identical, exit 0; full suite -> 175/175; fixture check -> 10/10 current;
path probe -> 1/1/1/1 target; diff check -> clean; commit: this commit.
Next: A6.0 (semantic-extensions expansion stage).

## 2026-08-06 - A6.0: semantic-extensions expansion stage - DONE
+ Expanded A6.1-A6.7 into Goal/Output/DoD/Depends contracts without renumbering
  existing stages; added the combined semantic-extension phase gate.
+ Ordered fixed-width decisions before aggregate lvalues, value records, proved
  references, modular frames, and optional invariant-inference research.
+ Fixed parser-last admission: every feature requires owned IR, exact VCs,
  capability checks, replay, schema review, and negative fail-closed tests.
+ Preserved default cross-check policy: a backend-specific unsupported result is
  never silently discarded in favor of one capable backend.
+ Required A6.1 to document the integer truth tables and append selected
  implementation stages after A6.7 without changing existing IDs.
+ Added the semantic-extensions roadmap covering trust, schema/fixture migration,
  dependencies, and the per-stage acceptance template.
- None.
Evidence: plan extended: A6.1-A6.7; stage contract review -> 7/7 complete;
full suite -> 175/175; fixture check -> 10/10 current; diff check -> clean;
commit: this commit.
Next: A6.1 (fixed-width integer-semantics decision point).

## 2026-08-06 - A6.1: fixed-width integer-semantics decision - DONE
+ Selected typed per-obligation homogeneous lowering: signed arithmetic stays
  QF_LIA when eligible; unsigned, mixed-to-unsigned, bitwise, and shifts use
  pure QF_BV; no SMT query mixes Int and BitVec sorts.
+ Pinned a C++17 i32/u32/i64/u64 two's-complement target profile with arithmetic
  signed right shift and mandatory Clang-side validation before source support.
+ Froze promotions/usual conversions, assignment conversions, literal policy,
  signed UB, unsigned modulo behavior, bitwise operations, and shift rules.
+ Chose schema v2 type IDs plus canonical decimal-string integer evidence to
  preserve all i64/u64 values; v1 fixtures must be archived unchanged.
+ Kept the fail-closed backend policy: affine rejects BV-required obligations,
  default both remains unsupported, and explicit Z3 mode is required.
+ Rejected pure-Int bit emulation, all-BV legacy migration, mixed-sort queries,
  signed-wrap approximation, and target-ambiguous implementation behavior.
+ Added primary C++17/SMT-LIB/Z3 references, three documentation guardrails, and
  implementation stages A6.8-A6.12 without renumbering existing stages.
- None.
Evidence: plan extended: A6.8-A6.12; decision tests -> 3/3; full suite ->
178/178; fixture check -> 10/10 current; diff check -> clean; commit: this
commit.
Next: A6.8 (fixed-width type profile and schema v2).

## 2026-08-06 - A6.8: fixed-width type profile and schema v2 - DONE
+ Added immutable owned `i32`/`u32`/`i64`/`u64` type identities, exact
  signedness/width/range metadata, and the pinned C++17 target-profile value.
+ Added a cached Clang compile probe for 8-bit bytes, 32/64-bit widths,
  two's-complement representation/narrowing, and arithmetic signed right shift;
  mismatch becomes deterministic frontend `solver_error` before lowering.
+ Migrated existing C++ `int` lowering and the QF_LIA referee path to explicit
  `i32` without accepting unsigned or 64-bit source types early.
+ Advanced report/Semantic IR to `codeskeptic.semantic-verification/v2`; fixed
  integer constants, counterexample bindings, and cache evidence now use strict
  canonical decimal strings while booleans remain JSON booleans.
+ Archived the complete v1 corpus with a 16-file SHA-256 manifest; regenerated
  current v2 fixtures and proved identical summaries and result status tuples.
+ Updated the schema, adoption, prototype, solver, changelog, and README
  contracts; expanded the ratchet from 178 to 189 tests.
- None.
Evidence: integer/profile/migration tests -> 11/11; full suite -> 189/189;
fixture check -> 10/10 current; archived v1 hashes -> 16/16; v1/v2 result
equivalence -> 5/5 cases; diff check -> clean; commit: this commit.
Next: A6.9 (signed int64 QF_LIA lane).
