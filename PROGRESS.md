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

## 2026-08-06 - A6.9: signed int64 QF_LIA lane - DONE
+ Added owned C++17 `long long`/`i64` lowering, exact i32-to-i64 promotion,
  pinned i64-to-i32 narrowing, typed literals, contracts, calls, and loops.
+ Parameterized signed range, negation, add/subtract/multiply, divisor-zero,
  and type-minimum/-1 obligations by width for both i32 and i64.
+ Added exact C++17 signed division/remainder emission for literal divisors;
  variable-divisor logical formulas fail closed in both referee paths.
+ Extended deterministic affine search, SMT-LIB sorts/casts, Z3 model parsing,
  and counterexample minimization/replay with exact i64 decimal evidence.
+ Added the 22-obligation i64 example/fixture and ten boundary, conversion,
  arithmetic, call, loop, replay, and negative fail-closed tests.
+ Updated schema/adoption/solver/prototype/changelog documentation and advanced
  the ratchet from 189 to 199 tests.
- None.
Evidence: int64 tests -> 10/10; exact SMT-LIB/referee tests -> green; i64
example -> 22 verified, zero non-verified results; full suite -> 199/199;
fixture check -> 12/12 current; diff check -> clean; commit: this commit.
Next: A6.10 (unsigned integers and homogeneous QF_BV lane).

## 2026-08-06 - A6.10: unsigned integers and homogeneous QF_BV lane - DONE
+ Added C++17 `unsigned int`/`unsigned long long` lowering as `u32`/`u64`,
  exact assignment casts, the complete i32/u32/i64/u64 usual-conversion table,
  and modulo-width unary/add/subtract/multiply semantics.
+ Added deterministic per-obligation QF_LIA/QF_BV classification and homogeneous
  QF_BV emission with exact signed/zero extension, truncation, comparisons,
  division, remainder, and no mixed `Int`/`BitVec` declarations.
+ Preserved signed C++ undefined behavior inside BV-tainted paths with an exact
  double-width `signed_no_overflow` predicate for addition, subtraction, and
  multiplication; replayed counterexamples cover all three unsafe operations.
+ Added strict width/sort-aware bitvector model parsing, source-signedness replay,
  counterexample minimization, and cache/backend identities for both SMT lanes.
+ Extended unsigned contracts, result-bearing calls, loop invariants, fixtures,
  explicit-Z3 adoption guidance, schema documentation, and migration notes.
+ Added 17 focused tests and the 20-obligation unsigned example/fixture; advanced
  the test-count ratchet from 199 to 216.
- None.
Evidence: unsigned/BV tests -> 17/17; mixed signed-overflow negatives -> 3/3;
explicit-Z3 example -> 20 verified, zero non-verified results; full suite ->
216/216; fixture check -> 14/14 current; diff check -> clean; commit: this commit.
Next: A6.11 (C++17 bitwise and shift operators).

## 2026-08-06 - A6.11: C++17 bitwise and shift operators - DONE
+ Added C++17 `~`, `&`, `|`, `^`, `<<`, and `>>` lowering with exact contract
  precedence, bool integral promotion, usual arithmetic conversions for bitwise
  pairs, and promoted-left result typing for shifts.
+ Classified every bitwise/shift formula as homogeneous QF_BV and added exact
  `bvnot`/`bvand`/`bvor`/`bvxor` plus width-normalized `bvshl`/`bvlshr`/`bvashr`
  emission without mixed `Int`/`BitVec` declarations.
+ Added shift-count range obligations and exact signed-left-shift definedness:
  nonnegative left operand plus zero-extended double-width representability in
  the corresponding unsigned type; pinned negative signed right shift is
  arithmetic.
+ Extended deterministic replay, simplification, constant evaluation,
  counterexample minimization, backend/cache identities, schema references,
  adoption guidance, and the supported/unsupported boundary.
+ Kept compound assignments, rotates, and builtin bit operations fail-closed.
+ Added ten focused tests and the 19-obligation bitwise fixture/example; advanced
  the test-count ratchet from 216 to 226.
- None.
Evidence: bitwise tests -> 10/10; invalid shift-count cases -> 3/3 violated;
invalid signed-left-shift values -> 2/2 violated; explicit-Z3 example -> 19
verified, zero non-verified results and repeated JSON byte-identical; full suite
-> 226/226; fixture check -> 16/16 current; diff check -> clean; commit: this
commit.
Next: A6.12 (fixed-width integer phase gate).

## 2026-08-06 - A6.12: fixed-width integer phase gate - DONE
+ Added `codeskeptic.fixed-integer-phase-gate/v0` and a deterministic combined
  slice with 60 obligations: 47 verified and 13 replayed violations.
+ Froze positive and negative evidence for all eight A6.1 operator-table rows,
  including every signed/unsigned add-subtract-multiply operation, division/
  remainder guards, comparisons, bitwise identities, and both shift families.
+ Froze the validated target profile, complete 4-by-4 usual-conversion table,
  assignment samples, homogeneous QF_LIA/QF_BV query hashes, and backend matrix.
+ Proved all 16 archived v1 hashes immutable and all five legacy v1 cases
  status-equivalent after v2 migration; archived files remained untouched.
+ Added the fixed-width operations/capability runbook, adoption/schema links,
  deterministic gate CLI, combined fixture/example, and frozen source/report
  hashes.
+ Added four phase-gate tests and advanced the test-count ratchet from 226 to
  230; the current fixture corpus now contains 18 artifacts.
- None.
Evidence: phase-gate tests -> 4/4; repeated gate JSON -> byte-identical; combined
slice -> 47 verified, 13 replayed violations, zero unknown/unsupported/error;
backend matrix -> LIA verified by affine/Z3/both, BV verified by Z3 and explicit
unsupported in affine/both; v1 archive -> 16/16 hashes; v1/v2 equivalence -> 5/5
cases; full suite -> 230/230; fixture check -> 18/18 current; diff check ->
clean; commit: this commit.
Next: A6.2 (restricted arrays).

## 2026-08-06 - A6.2: restricted arrays (QF_ARRAY) - DONE
+ Added canonical `array<E,N>` owned values for fully initialized local,
  one-dimensional fixed-size arrays of 1-64 fixed-width integer elements.
+ Added exact `array`/`select`/`store` IR, whole-array SSA writes and branch/loop
  value merges; updating one element preserves every other element exactly.
+ Added source and contract indexing with a replayable `array_bounds` obligation
  for every access, including accesses inside loop invariants.
+ Added homogeneous QF_ALIA/QF_ABV SMT emission, strict array-sort/value model
  parsing, source-level materialization, replay, minimization, and cache evidence.
+ Kept decay, aliases, raw-array parameters, dynamic/multidimensional arrays,
  partial/uninitialized/oversized arrays, and unmodeled operations fail-closed.
+ Advanced report/Semantic IR to v3, cache/key schemas to v1, and the fixed-
  integer gate to v1; archived all 28 v2 fixture hashes and proved nine-case
  v2-to-v3 plus five-case v1-to-v3 result-status equivalence.
+ Added 13 focused tests and the fully verified 18-obligation array fixture;
  advanced the test ratchet from 230 to 244 and the corpus to 20 artifacts.
- None.
Evidence: array tests -> 13/13; signed QF_ALIA and unsigned QF_ABV lanes ->
deterministic; OOB candidates -> replayed and minimized; explicit-Z3 example ->
18 verified, zero non-verified and repeated JSON byte-identical; integer phase
gate v1 -> green; v2 archive -> 28/28 hashes; full suite -> 244/244; fixture
check -> 20/20 current; non-archive diff check -> clean; commit: this commit.
Next: A6.3 (restricted value structs).
## 2026-08-06 - A6.3: restricted value structs (QF_RECORD) - DONE
+ Added canonical named value-record types with 1-16 public scalar, owned-array,
  or earlier-record fields, maximum depth 8, and full aggregate initialization.
+ Added exact `record`/`project`/`update` IR, whole-record and field-sensitive SSA,
  nested field/array paths, copy isolation, branch/loop merges, and field contracts.
+ Added direct record parameters, returns, locals, and contracted calls by value;
  every signed integer leaf, including array fields and call/loop havoc, is bounded.
+ Added deterministic QF_RECORD datatype emission with dependency-first nested
  declarations, signed Int and unsigned/bitvector sublanes, typed model decoding,
  mandatory recursive replay, minimization, public evidence, and cache v2 tags.
+ Kept methods, non-implicit constructors, inheritance, unions, bitfields, layout
  claims, classes/private state, pointers/references, partial/default/uninitialized
  values, excessive width/depth, and escaping addresses fail-closed.
+ Advanced report/Semantic IR to v4, cache/key schemas to v2, and the fixed-
  integer gate to v2; archived all 31 v3 fixture hashes and proved ten-case
  v3-to-v4, nine-case v2-to-v4, and five-case v1-to-v4 status equivalence.
+ Added 16 focused/migration tests and the fully verified 9-obligation struct
  fixture; advanced the test ratchet from 244 to 260 and corpus to 22 artifacts.
- None.
Evidence: struct tests -> 15/15; signed/unsigned/nested-array datatype lanes ->
deterministic and replayed; explicit-Z3 example -> 9 verified, zero non-verified;
integer phase gate v2 -> green; v3 archive -> 31/31 hashes; full suite ->
260/260; fixture check -> 22/22 current on two runs; diff check -> clean; commit:
this commit.
Next: A6.4 (restricted references with proved alias discipline).

## 2026-08-06 - A6.4: restricted references with proved alias discipline - DONE
+ Added local const/mutable lvalue references whose unique live owned scalar,
  value-record, or record-field target is established before lowering.
+ Lowered every reference read to the target's current SSA version and every
  permitted write to the shared aggregate update path; no declaration-time
  snapshot or independent reference storage exists.
+ Added proof-bearing target/path, referent type, mutability, declaration
  location, and enclosing-lexical-scope lifetime metadata to FunctionIR.
+ Supported scalar and whole-record aliases, disjoint record-field aliases,
  branch/sequential lifetimes, outer bindings in loops, and by-value calls.
+ Kept conditional/multiple targets, temporaries, rvalue/pointer/array-element
  references, in-loop declarations, overlapping live aliases, parameters,
  returns, fields, and address escape fail-closed.
+ Advanced report/Semantic IR to v5 and the fixed-integer gate to v3; archived
  all 34 v4 fixture hashes and proved 11 v4-to-v5, 10 v3-to-v5, nine v2-to-v5,
  and five v1-to-v5 status-equivalent migrations.
+ Added ten focused reference tests and the fully verified six-obligation
  reference fixture; advanced the test ratchet from 260 to 271 and the corpus
  from 22 to 24 artifacts.
+ Expanded the A6.4 exact file set in PLAN before schema, fixture, migration,
  gate, and documentation edits.
- None.
Evidence: reference tests -> 10/10; focused stage tests -> 50/50; explicit-Z3
example -> 6 verified, zero non-verified; integer phase gate v3 -> green; v4
archive -> 34/34 hashes; full suite -> 271/271; fixture check -> 24/24 current;
diff check -> clean; commit: this commit.
Next: A6.5 (`modifies` contracts and frame conditions).

## 2026-08-06 - A6.5: modifies contracts and frame conditions - DONE
+ Added strict `cs: modifies` parsing for explicit empty, single, multiple, and
  nested value-record field frames rooted at mutable reference parameters.
+ Added declaration-only const/mutable reference parameters, positional frame
  reuse across renamed redeclarations, and conflict detection across summaries.
+ Normalized modified actuals to caller-owned lvalue paths, rejected overlapping
  actuals, havoced each affected root once, and retained recursive type bounds.
+ Added exact functional preservation equalities for every unlisted reachable
  field and post-call reference arguments for `ensures`; `requires` retain
  pre-call values and result assignment receives a later SSA version.
+ Kept reference-parameter definitions, missing/conflicting frames, conditional
  or overlapping actuals, array-element frames, inaccessible/value/const roots,
  and duplicate/overlapping targets fail-closed.
+ Advanced report/Semantic IR to v6 and the fixed-integer gate to v4; archived
  all 37 v5 fixture hashes and proved 12 v5-to-v6, 11 v4-to-v6, 10 v3-to-v6,
  nine v2-to-v6, and five v1-to-v6 status-equivalent migrations.
+ Added 17 parser/frame/migration tests and the fully verified ten-obligation
  frame fixture; advanced the test ratchet from 271 to 288 and the corpus from
  24 to 26 artifacts.
+ Expanded the A6.5 exact file set in PLAN before schema, fixture, migration,
  gate, and documentation edits.
- None.
Evidence: frame tests -> 14/14; focused stage tests -> 64/64; explicit-Z3
example -> 10 verified, zero non-verified; integer phase gate v4 -> green; v5
archive -> 37/37 hashes; full suite -> 288/288; fixture check -> 26/26 current;
diff check -> clean; commit: this commit.
Next: A6.6 (CHC/Spacer invariant-inference research spike).
## 2026-08-06 - A6.6: CHC/Spacer invariant-inference research spike - DONE
+ Added an isolated signed-i32 Horn problem model, strict S-expression parser,
  canonical CHC emitter, and Z3/Spacer subprocess runner pinned to 5.0.0 with
  fixed SMT/SAT/Spacer seeds, disabled parallel solving, and bounded execution.
+ Added a sorted six-case corpus and v0 candidate artifact recording useful,
  insufficient, no-candidate, timeout, unsupported, and malformed outcomes.
+ Reattached every solver candidate as `cs: ai invariant` and sent it through
  the ordinary affine/Z3 referee; machine provenance, loop entry, and loop
  preservation remain explicit in the resulting Semantic IR and VCs.
+ Demonstrated one candidate that verifies all five obligations and one
  inductive candidate whose violated postcondition remains `insufficient`.
+ Added deterministic solver-case budgeting, strict certificate/`let` parsing,
  canonical query/certificate/source hashes, and artifact check/write CLI modes.
+ Added the decision memo recommending an optional proposal-only pre-pass for
  signed-linear loops without integrating inference into the trusted path.
+ Added 13 focused tests and advanced the test ratchet from 288 to 301.
+ Expanded the A6.6 exact file set in PLAN before implementation edits.
- None.
Evidence: invariant research tests -> 13/13; repeated corpus renders -> byte-
identical; committed artifact SHA-256 ->
`e644ec4c61032510888f44d162d57bc4b72a87f16b2a067f0b3120f498fdc0e1`;
proposal-only check -> green; full suite -> 301/301; fixture check -> 26/26
current; diff check -> clean; commit: this commit.
Next: A6.7 (semantic-extension phase gate).

## 2026-08-06 - A6.7: semantic-extension phase gate - DONE
+ Added the deterministic `codeskeptic.semantic-extensions-phase-gate/v0`
  artifact over every A6 feature family, current/legacy fixtures, migration,
  counterexample replay, negative boundaries, and invariant proposals.
+ Added an eight-obligation combined slice covering owned arrays, value records,
  proved references, modular frames, i64 arithmetic, unsigned bitwise state,
  and loop invariants; explicit Z3 verifies all eight obligations.
+ Froze the seven-row backend capability matrix. Signed QF_LIA cross-checks;
  BV, array, and record formulas remain explicit `unsupported` under default
  cross-check even though the capable Z3 lane verifies them.
+ Added five fail-closed probes for pointers, variable-length arrays, array-
  element references, missing mutable-reference frames, and `short`.
+ Regenerated the 14-case/28-artifact current corpus twice byte-identically and
  added the combined example IR/report fixture without changing schema v6.
+ Reused and pinned all v1-v5 archive/migration evidence, 13 replayed integer
  violations, and the A6.6 useful/insufficient ordinary-referee decisions.
+ Added the semantic-extension operations runbook and eight phase-gate tests;
  advanced the test ratchet from 301 to 309.
+ Expanded the A6.7 exact file set before implementation, then recorded and
  resolved the fixture-count test spill before editing that test.
- None.
Evidence: semantic-extension gate -> green, canonical artifact SHA-256
`d27330e7f930043bca16b955d17b39b912f9ff345f4f260f7aab02d717fff2a9`;
combined capable/default summaries -> 8 verified / 8 unsupported; focused gate
tests -> 8/8; fixture infrastructure -> 3/3; inference artifact -> matched;
integer gate -> green with 13 replayed violations; fixture checks -> 28/28 on
two runs; full suite -> 309/309; diff check -> clean; commit: this commit.
Next: B1.1 (deterministic fixture export for the native adapter).

## 2026-08-06 - B1.1: deterministic native-adapter fixture export - DONE
+ Added canonical `codeskeptic.native-adapter-semantic-ir/v0` and
  `codeskeptic.native-adapter-obligations/v0` envelopes for all 14 reference
  fixture cases, independent of checker result serialization.
+ Added the sorted `codeskeptic.native-adapter-fixtures/v0` manifest with v6
  report identity, backend/summary metadata, source/artifact paths, and SHA-256
  hashes for every source, IR, and obligation payload.
+ Added `tools/export_fixtures.py` with deterministic in-memory generation,
  write/check modes, safe relative paths, exact committed-file comparison, and
  working-directory-independent defaults.
+ Proved every exported Semantic IR and obligation list equals the corresponding
  current v6 report fields; two complete 29-artifact maps are byte-identical.
+ Added five export/integrity tests and advanced the ratchet from 309 to 314.
+ Expanded the sparse B1.1 plan contract with Goal/Output/exact file set/DoD
  before implementation.
- None.
Evidence: native-adapter export tests -> 5/5; manifest SHA-256 ->
`462d1be66df0a3ef4d6d9493a443270248289e2c91df9ccd18e825db244c8e82`;
`python tools/export_fixtures.py --check` -> 29/29 current; ordinary fixture
check -> 28/28 current; full suite -> 314/314; diff check -> clean; commit:
this commit.
Next: B1.2 (standalone CodeSkeptic semantic module skeleton).

## 2026-08-06 - B1.2: standalone CodeSkeptic semantic module skeleton - DONE
+ Created CodeSkeptic production branch `codex/semantic-verification-native`
  from the clean `main` clone at `C:\tmp\CodeSkeptic-reference`.
+ Added Clang-independent owned C++17 value objects for v6 scalar/array/record
  identities, canonical expressions, contracts, statements, functions,
  unsupported records, complete modules, and deterministic validation issues.
+ Added source-ordered, fail-closed structural validation for type identities,
  canonical literals, expression arity, locations, node/function identities,
  parameters, contracts, and statement-specific required fields.
+ Integrated the standalone module into `codeskeptic_core` without touching
  `src/core/Rule.h` or depending on Diagnostic, reporters, server, or Clang AST.
+ Added five production tests for stable vocabulary, owned expression children,
  aggregate identities, source order, and deterministic malformed-input refusal;
  the production suite grew from 811 to 816 tests.
+ Expanded the B1.2 Goal/Output/exact cross-repository file set/DoD before edits
  and corrected the production-clone location in TODO.
- MSBuild inherited duplicate `Path`/`PATH` environment keys from the Codex
  shell; the build command removed the duplicate before launching MSBuild.
Evidence: production build -> success; focused SemanticIR tests -> 5/5; full
CodeSkeptic suite -> 816/816; forbidden dependency scan -> clean; Rule.h diff
-> empty; production commit -> `20b12bd`; reference baseline -> 314/314; commit:
this reference-ledger commit.
Next: B1.3 (native ASTContext to Semantic IR lowering).

## 2026-08-06 - B1.3: native ASTContext to Semantic IR lowering - DONE
+ Added a standalone `SemanticLowerer` that consumes Clang `ASTContext` and
  returns fully owned IR with no AST pointers retained beyond the translation
  unit.
+ Lowered main-file free-function definitions for exact `void`/`bool` and
  32/64-bit integer types, parameters, initialized locals, assignments, direct
  calls, returns, `if`/`else`, literals, local references, implicit scalar
  casts, and the supported unary/binary operator set.
+ Added deterministic source/function/symbol/node identities, source order and
  locations, distinct identities for shadowed variables, and repeatable output
  across independently parsed translation units.
+ Kept pointer/narrow types, templates, variadics, uninitialized locals, loops,
  compound assignment, member/indirect calls, macros, and every other omitted
  construct explicitly fail-closed with stable unsupported reasons.
+ Extended owned IR with function/parameter/local locations and locals, plus
  return-type-aware validation including exact void-return handling.
+ Added eight focused production tests; the CodeSkeptic suite grew from 816 to
  824 tests without touching `Rule.h` or introducing Rule, Diagnostic,
  reporter, or server dependencies.
+ Expanded the sparse B1.3 Goal/Output/exact file set/boundary/DoD before
  implementation and ordered B1.5 before the contract-dependent B1.4 gate.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: production build -> success; focused SemanticIR/lowerer tests ->
13/13; full CodeSkeptic suite -> 824/824; deterministic owned-lowering test ->
green; unsupported boundary tests -> green; forbidden dependency scan -> clean;
`Rule.h` diff -> empty; production commit -> `bc3c8f9`; reference suite ->
314/314; commit: this reference-ledger commit.
Next: B1.5 (native arithmetic contract parsing and ContractInfo adaptation),
then B1.4 (byte-for-byte native/Python fixture equality).

## 2026-08-06 - B1.5: arithmetic contracts and Semantic IR adaptation - DONE
+ Replaced the predicate-only parse path with an owned scalar expression tree
  covering the reference precedence ladder from unary through logical OR while
  retaining the legacy `ContractPred` recognizer shape for existing rules.
+ Added strict FunctionDecl-aware binding for parameters and `return`, boolean
  and fixed-width typing, pinned usual-arithmetic conversions, canonical
  constant conversion, i32-min/u64-max boundaries, and `integral` cast identity
  matching the Python reference IR.
+ Attached valid requires/ensures clauses to native functions with exact text,
  provenance, and source locations; requires now become source-ordered IR
  `assume` nodes with explicit `requires` origin.
+ Kept unknown names, non-boolean clauses, incompatible operands, overflowed
  literals, malformed syntax, guarded ensures, pointer/null clauses, effects,
  and policies explicit at the scalar semantic boundary rather than dropping
  or approximating them.
+ Preserved all legacy null, ownership, sidecar, policy, and guarded-contract
  consumers; the complete 48-test production contract suite remains green.
+ Updated the contract grammar and added six production tests for precedence,
  token separation, malformed arithmetic, assume origins, typed adaptation,
  signed/unsigned conversion, literal bounds, and fail-closed binding; the
  production suite grew from 824 to 830 tests.
+ Expanded the B1.5 Goal/Output/exact file set/grammar boundary/DoD before
  implementation.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused parser/IR/lowerer tests -> 24/24; legacy contract suite ->
48/48; full CodeSkeptic suite -> 830/830; reference expression-shape probe ->
matched for u32/i64/u64 arithmetic, i32 minimum, u64 maximum, result naming,
and `integral` casts; full reference suite -> 314/314; `Rule.h` diff -> empty;
production commit -> `f7fb925`; commit: this reference-ledger commit.
Next: B1.4 (byte-for-byte native/Python fixture equality).

## 2026-08-06 - B1.4: native/Python byte-comparison harness - DONE
+ Added canonical, lexicographically sorted native-adapter JSON serialization
  for the complete v6 module envelope, including records, references, frames,
  SSA nodes, loop metadata, unsupported records, and source identity.
+ Vendored the 14 B1.1 C++ sources and 14 canonical Semantic IR payloads with
  their manifest; all source and IR SHA-256 values match, and `.gitattributes`
  pins the byte contract to LF on Windows checkouts.
+ Added an in-memory Clang fixture runner with no Python process or fixture
  substitution on the native render path, first-byte/line/column mismatch
  diagnostics, and two-run determinism coverage.
+ Extended native lowering through owned arrays and records, projections and
  functional updates, local references, reference parameters, `modifies`
  frames and call effects, direct call results, branch merges, loop-head/back/
  exit SSA, invariants, termination metadata, and declaration-only functions.
+ Extended the owned contract parser/binder with result aliases, record field
  projections, invariants, and strict modifies paths while preserving all
  legacy contract consumers and fail-closed diagnostics.
+ Kept the B1.3 compatibility tests meaningful by updating them to assert the
  stronger SSA/declaration/loop semantics; production grew from 830 to 833
  tests and every test is green.
+ Expanded the B1.4 exact file set before implementation and recorded the
  discovered LF portability spill before adding production `.gitattributes`.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: vendored hash gate -> 14/14; native/Python byte equality -> 14/14;
complete native render determinism -> green; focused lowerer/adapter tests ->
13/13; full CodeSkeptic suite -> 833/833; reference fixture export -> 29/29
current; full reference suite -> 314/314; production commit -> `5acc51b`;
commit: this reference-ledger commit.
Next: B2.0 (production VC/referee route expansion and decision).

## 2026-08-06 - B2.0: native VC/referee route decision - DONE
+ Chose a C++17 production port for VC generation, deterministic SMT-LIB2,
  solver orchestration, model replay, and verification-result routing; Python
  remains the lab/reference oracle and is not a production runtime dependency.
+ Measured the direct helper surface: `vc.py` is 1,113 lines and its direct
  model/type/query dependencies bring the boundary to 2,345 lines; no general
  validated Semantic IR JSON input parser exists in the reference package.
+ Recorded the alternative matrix across soundness, packaging, determinism,
  portability, schema drift, diagnostics, testability, isolation, and long-term
  maintenance, including explicit reopen criteria.
+ Added D12 and fixed the production trust seams: native pure VCG,
  `CheckerBackend`, unlinked Z3 subprocess, mandatory counterexample replay,
  and shared result adapters for Rule/SARIF/MCP.
+ Expanded B2.1-B2.4 with Goal/Output/file boundaries/DoD/dependencies before
  implementation; B2.1 now requires 14-case obligation byte equality before a
  checker is introduced.
+ Added the production decision record without changing runtime code or test
  baselines.
- None.
Evidence: full CodeSkeptic suite -> 833/833; full reference suite -> 314/314;
production diff check -> clean; production commit -> `84eebfd`; commit: this
reference-ledger commit.
Next: B2.1 (native VC generator and obligation fixture equality).

## 2026-08-06 - B2.1: native verification-condition generator - DONE
+ Added owned native obligation and trace-template value objects, structural
  expression identity, a pure C++17 verification-condition generator, and
  canonical obligation JSON with no checker, Z3, Rule, or Diagnostic coupling.
+ Ported contract consistency/well-formedness, expression safety, calls,
  frame preservation, branch compaction and merges, loop invariant entry and
  preservation, recursion detection, and fail-closed unsupported boundaries.
+ Vendored all 14 canonical obligation payloads and pinned their manifest
  hashes; native lowering plus VCG is byte-identical to the Python reference
  for every payload and repeated complete renders are deterministic.
+ Added focused negative/determinism tests and a corpus behavior gate covering
  bounds, division, overflow, call preconditions, external contracts,
  postconditions, loops, and unsupported constructs.
+ Production grew from 833 to 840 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: obligation hashes -> 14/14; native/Python obligation byte equality ->
14/14; focused VC/fixture tests -> 7/7; full CodeSkeptic suite -> 840/840;
production commit -> `a36425e`; reference suite -> 314/314; commit: this
reference-ledger commit.
Next: B2.2 (native deterministic referee and verification rule).

## 2026-08-06 - B2.2: native deterministic referee and rule seam - DONE
+ Added the native `CheckerBackend`/`Z3Checker` seam and deterministic SMT-LIB2
  emission for homogeneous signed-integer, bitvector, owned-array, and owned-
  record obligations, including stable symbol encoding and solver seeds.
+ Added bounded unlinked-Z3 execution with deterministic discovery, explicit
  missing/crash/timeout outcomes, fixed options, and no library dependency.
+ Added typed get-value parsing, mandatory replay against the original
  assumptions/conclusion, trace resolution, and deterministic counterexample
  projection/minimization; malformed or incomplete models are solver errors.
+ Added a separate five-status verification result channel at `Rule::check`,
  `RuleEngine`, and `StaticAnalyzer`, preserving legacy diagnostics unchanged.
+ Added `SemanticVerificationRule` with injectable referee ownership; focused
  tests cover backend substitution, coexistence, missing Z3, timeout, crash,
  unsupported logic, corrupt models, deterministic queries, replay, and traces.
+ All 14 native status summaries match the manifest-pinned Python reference;
  production grew from 840 to 855 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused referee tests -> 15/15; native/reference status summaries ->
14/14; corrupt-model replay rejection -> green; deterministic violating fixture
repeat -> green; full CodeSkeptic suite -> 855/855; reference suite -> 314/314;
production commit -> `80be397`; commit: this reference-ledger commit.
Next: B2.3 (SARIF semantic-verification output).

## 2026-08-06 - B2.3: SARIF semantic-verification output - DONE
+ Added a backward-compatible reporter overload carrying the separate native
  verification-result channel from `StaticAnalyzer` into SARIF.
+ Added distinct SARIF level/kind mappings for verified, violated, unknown,
  unsupported, and solver-error results with a versioned CodeSkeptic property
  bag and deterministically sorted semantic rule IDs.
+ Added structured typed counterexamples, source/logical locations, and trace
  code flows carrying obligation IDs and evaluated step values.
+ Preserved the existing one-argument SARIF contract byte-for-byte when no
  semantic results are supplied; repeated semantic serialization is identical.
+ Production grew from 855 to 859 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused SARIF tests -> 10/10; five-status distinction -> green;
legacy byte compatibility -> green; deterministic repeated render -> green;
full CodeSkeptic suite -> 859/859; reference suite -> 314/314; production
commit -> `8bf2265`; commit: this reference-ledger commit.
Next: B2.4 (MCP `verify_function` referee surface).

## 2026-08-06 - B2.4: MCP `verify_function` referee surface - DONE
+ Added a stable `verify_function` MCP discovery schema requiring a source path
  and unique plain function name or exact canonical signature key.
+ Reused the native lowering, targeted VCG, deterministic backend, replayed
  evidence, and five-state result channel without adding any AI judgment path.
+ Added sorted and capped ambiguous-selection candidates plus bounded missing,
  invalid-path, and parse-failure tool errors.
+ Added versioned structured obligations, fixed status summaries, typed
  counterexamples, recursive trace conditions, source locations, and referee
  identity; repeated responses are byte-identical.
+ Production grew from 859 to 866 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and a serial
  link; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused MCP tests -> 25/25; exact/ambiguous/missing selection ->
green; all five result states -> green; deterministic repeat -> green; full
CodeSkeptic suite -> 866/866; reference suite -> 314/314; production commit ->
`9d46aaf`; commit: this reference-ledger commit.
Next: B3.0 (sidecar contract database expansion).

## 2026-08-06 - B3.0: sidecar contract database expansion - DONE
+ Measured the existing production seam: adjacent `.csk` parsing, anchored
  legacy enforcement, absolute sidecar locations, per-run cache clearing, and
  malformed-line diagnostics already exist and remain the foundation.
+ Isolated the native verification gap: semantic contract adaptation currently
  reads inline comments only, so B3.1 can merge adjacent sidecars without
  changing the parser grammar or introducing package discovery.
+ Expanded B3.1-B3.3 with explicit goals, outputs, planned file boundaries,
  soundness constraints, runnable DoD evidence, and dependencies.
+ Limited the first standard-library models to qualified scalar `abs`, `min`,
  and `max` signatures; heap, alias, floating, comparator, and container claims
  remain explicitly outside the stage.
+ Defined offline hash-checked package discovery and fail-closed conflict/schema
  rules before any distribution implementation.
- None.
Evidence: existing sidecar parser/enforcement tests -> green; production suite
at unchanged B2.4 commit -> 866/866; reference suite -> 314/314; plan links and
stage IDs -> present; commit: this planning commit.
Next: B3.1 (adjacent `.csk` contracts on the native verification path).

## 2026-08-06 - B3.1: adjacent sidecars on native verification - DONE
+ Merged inline and adjacent `.csk` clauses through the same strict typed
  semantic binder in inline-first order while retaining sidecar file and
  absolute-line provenance.
+ Made exact duplicate clauses and a second `modifies` contract fail closed;
  invalid sidecar names/types remain explicit unsupported contract records.
+ Extended targeted VCG so direct callee contract consistency and external
  postcondition well-formedness obligations precede any assumed callee ensures.
+ Added native lowering/VCG and MCP coverage for bodiless external sidecar
  requires/ensures, deterministic provenance, and edited-sidecar cache reload.
+ A live production MCP request with native Z3 produced two verified callee
  trust obligations and one replayed call-precondition violation.
+ Production grew from 866 to 869 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and serial
  linking; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused sidecar/native tests -> 4/4; live native-Z3 MCP summary ->
verified=2, violated=1, unknown=0, unsupported=0, solver_error=0; full
CodeSkeptic suite -> 869/869; reference suite -> 314/314; production commit ->
`75411c4`; commit: this reference-ledger commit.
Next: B3.2 (first value-semantic standard-library mini-models).

## 2026-08-06 - B3.2: integer standard-library mini-models - DONE
+ Added a deterministic offline registry with ten exact C++17 integer models:
  signed i32/i64 `std::abs` and homogeneous i32/u32/i64/u64 `std::min/max`.
+ Required system-header declarations, qualified canonical signatures, exact
  source argument types, and signature-unique semantic names, so user
  lookalikes and mixed calls cannot inherit a model.
+ Synthesized only referenced models as bodyless value-semantic functions with
  stable `codeskeptic://stdlib/cxx17/integer-v1` provenance.
+ Excluded the signed minimum from `abs`; copied `min/max` results retain exact
  value/order postconditions without making alias, heap, or reference claims.
+ Added fail-closed coverage for floating, mixed, comparator, initializer-list,
  pointer/reference-alias, unsigned `abs`, and user-lookalike forms.
+ Live native Z3 verified the three positive examples and replayed both the
  signed-min precondition and deliberately false `min` postcondition.
+ Repeated MCP verification output was byte-identical; production grew from
  869 to 874 tests and every test is green.
- Windows MSBuild still requires duplicate `Path`/`PATH` removal and serial
  linking; the existing LNK4199 delay-load warning remains non-fatal.
Evidence: focused native model tests -> 5/5; live native-Z3 positives ->
verified with zero unsupported; live negatives -> replayed precondition and
postcondition violations; repeated MCP bytes -> identical; full CodeSkeptic
suite -> 874/874; reference suite -> 314/314; production commit -> `8c62aad`;
commit: this reference-ledger commit.
Next: B3.3 (versioned contract packages and offline distribution).

## 2026-08-07 - B3.3: versioned contract packages and offline distribution - DONE
+ Replaced the embedded standard-library registry with a deterministic offline
  v1 package loader using target profiles, sorted claims, SHA-256 file pins,
  safe relative paths, and logical package provenance.
+ Kept loading fail-closed for missing required bundles, unknown schemas,
  malformed models, incompatible targets, traversal, hash drift, manifest/model
  disagreement, and non-identical duplicate signature claims; byte-identical
  duplicates deduplicate without precedence.
+ Added repeatable CLI/config and MCP local-package paths, deterministic package
  diagnostics, explicit blocked-signature lowering, and package metadata in
  both MCP analysis and verification results.
+ Migrated all ten B3.2 integer models into the same package schema consumed by
  source builds and relocated releases, preserving their exact semantic bounds.
+ Bundled the pack in release ZIPs and added fail-fast manifest checks to the
  packaging script, Docker build/runtime layout, and GitHub Action download.
+ A real 15 MB Windows package retained the pinned model hash; its relocated
  binary used native Z3 to verify `absolute_value` with summary verified=6 and
  every other status zero, and repeated MCP responses were byte-identical.
+ Production grew from 874 to 884 tests and every test is green.
- Docker and a hosted GitHub Action runner were unavailable locally; both
  definitions now assert the shared release manifest path when they execute.
Evidence: package/config/stdlib/MCP tests -> 39/39; full CodeSkeptic suite ->
884/884; release archive contains the pinned manifest and model hash
`375ee955fcf1da413504d53d249bad0a820f0ec3e2c5221b054b47c7c4f0e544`;
packaged native-Z3 MCP -> verified=6, all other states=0, repeated bytes equal;
full reference suite -> 314/314; production commit -> `628c9d6`; commit: this
reference-ledger commit.
Next: B4.0 (CI and adoption path expansion).

## 2026-08-07 - B4.0: CI and adoption path expansion - DONE
+ Inventoried the production CLI, rule engine, semantic result channel, exit
  policy, legacy baseline, SARIF reporter, Action, and packaging seams.
+ Expanded B4.1 and B4.2 with exact file boundaries, dependencies, rollout
  defaults, invariants, and executable definitions of done.
+ Froze legacy behavior unless semantic verification is explicitly enabled and
  separated proof-obligation debt from the legacy diagnostic baseline.
+ Defined report/violations/complete gate modes, fail-closed exit precedence,
  exact-status baseline escalation, logical fingerprints, and SARIF consumer
  stability requirements.
+ Production remains unchanged and green at 884/884; the reference suite is
  green at 314/314.
- No blockers.
Evidence: production commit `628c9d6` -> 884/884; reference suite -> 314/314;
expanded B4 stage contracts and exact file sets -> present; commit: this
planning commit.
Next: B4.1 (opt-in semantic-verification CI gate).

## 2026-08-07 - B4.1: opt-in semantic-verification CI gate - DONE
+ Added explicit CLI/config enablement with report, violations, and complete
  gate modes while preserving every legacy invocation by default.
+ Added a deterministic v1 semantic-debt baseline keyed by logical obligation
  SHA-256 plus exact status; matching changes only the gate and never hides a
  result, while solver errors and worsened statuses always resurface.
+ Added fail-closed exit precedence, five-status deterministic console output,
  strict JSON/HTML rejection, and normal-CLI native referee wiring.
+ Added Action inputs and five status-count outputs plus a hosted self-test
  fixture that installs the external Z3 referee and exercises report-only
  adoption with a raw violation exit.
+ The real native-Z3 fixture produced one verified and one replayed violated
  obligation; report=0, violations=1, baseline write=0, baselined gate=0, and
  missing baseline=3. Repeated console and SARIF bytes matched.
+ Production grew from 884 to 908 tests and every test is green.
- A hosted Action runner was unavailable locally; both Action YAML files parse
  and the workflow now pins the expected status-count assertions when hosted.
Evidence: focused config/gate/baseline/summary tests -> 26/26; full CodeSkeptic
suite -> 908/908; real Z3 fixture -> verified=1, violated=1; deterministic
console/SARIF -> byte-identical; production commit -> `88c1bed`; reference
suite -> 314/314; commit: this reference-ledger commit.
Next: B4.2 (SARIF editor and code-scanning consumer integration).

## 2026-08-07 - B4.2: SARIF editor and code-scanning integration - DONE
+ Added stable semantic rule descriptors, versioned logical partial
  fingerprints, and explicit baseline/gate metadata for all five statuses.
+ Kept verified, violated, unknown, unsupported, and solver-error results
  distinct in standard SARIF level/kind fields and the semantic property bag.
+ Added navigable physical/logical locations and ordered replay code flows with
  obligation fingerprints attached to every trace step.
+ Added a pinned five-status consumer contract covering relocation and line-shift
  stability, semantic-change invalidation, trace navigation, and byte stability.
+ Extended the Action self-test to upload semantic SARIF and assert status,
  fingerprint, and gate metadata; documented the supported consumer contract.
+ A real native-Z3 CLI fixture emitted two semantic records with two partial
  fingerprints; repeated SARIF output was byte-identical.
+ Production grew from 908 to 914 tests and every test is green.
- A hosted GitHub Action runner was unavailable locally; both Action YAML files
  parse and the hosted workflow contains the required assertions and upload.
Evidence: focused SARIF/result tests -> 17/17; full CodeSkeptic suite ->
914/914; real CLI -> semantic=2, fingerprints=2, repeated bytes equal; full
reference suite -> 314/314; production commit -> `25f5065`; commit: this
reference-ledger commit.
Next: C1.1 (offline AI contract proposal template).
## 2026-08-07 - C1.1: offline contract-proposal prompt pack - DONE
+ Added strict v1 request/response JSON schemas and bundled them as package
  data with a vendor-neutral, self-contained system prompt.
+ Added a dependency-free renderer and CLI that make no model or network call
  and produce canonical JSON with the complete response schema embedded.
+ Logical SHA-256 request identity excludes checkout path and line while
  including the exact signature, body, symbols, and visible contract context.
+ The response contract permits only candidate/declined outcomes, requires
  `cs: ai` on every proposed comment, and cannot encode accepted intent.
+ Added a frozen request/golden prompt pair plus strict-input, provenance,
  relocation, semantic-change, CLI, and repeat-byte coverage.
+ The reference suite grew from 314 to 322 tests and every test is green.
- External model execution is intentionally outside this repository; C1.2 will
  reject unfit responses through the deterministic referee before review.
Evidence: focused proposal tests -> 8/8; golden CLI check -> exact match;
request id -> `sha256:8daa621ef4da277cb6b9361b54cfdb4cb234352c82164c0f76b0fbca04e4da5b`;
full reference suite -> 322/322; commit: this stage commit.
Next: C1.2 (deterministic proposal pre-screening).
## 2026-08-07 - C1.2: deterministic proposal pre-screening - DONE
+ Added strict response parsing, logical request matching, canonical response
  hashing, and a versioned deterministic pre-screen report schema.
+ Built candidate overlays only in memory; input requests and source remain
  unchanged, and every retained comment keeps the `cs: ai` marker.
+ Reused the ordinary frontend, contract parser, VC generator, and checker for
  fragment checks, jointly typed contract satisfiability, and source preview.
+ Contradictory requirements are rejected as violated; malformed, unknown,
  unsupported, solver-error, and declined outcomes remain visibly distinct.
+ Machine-proposed invariants become eligible only when loop entry and
  preservation are both independently verified.
+ A body-violating but well-formed/satisfiable postcondition remains reviewable
  intent with violation counts visible; it is never called accepted or proved.
+ Added a six-state fixture matrix and byte-stable golden pre-screen artifact;
  the reference suite grew from 322 to 330 tests and every test is green.
- The dependency-free affine backend may conservatively return unknown; such a
  proposal is rejected unless an operator reruns with the available Z3/both
  referee and receives a definitive result.
Evidence: focused proposal tests -> 16/16; fixture matrix -> eligible, violated,
unsupported, unknown, malformed, and declined preserved; injected checker
failure -> solver_error rejection; repeated/golden pre-screen bytes -> equal;
full reference suite -> 330/330; commit: this stage commit.
Next: C1.3 (human approval and accepted-intent boundary).
## 2026-08-07 - C1.3: human approval and accepted-intent boundary - DONE
+ Added versioned review-bundle and accepted-intent audit artifacts with explicit
  proposed, rejected, reviewable, stale, and accepted state transitions.
+ Review export contains only the canonical `cs: ai` overlay; rejected and
  declined responses expose no source overlay to a human reviewer.
+ Acceptance requires a separately supplied source where only owned proposal
  lines may change and every reviewed contract has the `ai` marker removed.
+ Human-edited contract expressions are run through the complete C1.2
  pre-screen again; incomplete or invalid edits remain rejected.
+ Any non-candidate source edit is stale, and every accepted audit pins the
  canonical source/contracts so later semantic edits stop matching.
+ The tool never removes `ai`; accepted audits keep
  `human_attestation_required=true` because reviewer identity is external.
+ Added deterministic candidate/accepted source fixtures and byte-stable review
  and audit goldens; the suite grew from 330 to 338 tests and is fully green.
- The mechanism verifies the review boundary and referee result, not whether a
  particular person performed the edit; the operator supplies that attestation.
Evidence: focused proposal/review tests -> 24/24; all review/acceptance states
validate against their JSON schemas; review and acceptance golden CLI checks ->
exact match; relocation keeps review/audit identity, later source edit breaks
matching; full reference suite -> 338/338; commit: this stage commit.
Next: C2.1 (contract-first task template and end-to-end run).
## 2026-08-07 - C2.1: executable contract-first task template - DONE
+ Added a versioned, dependency-free workflow checker and CLI for prose request
  → `cs: ai` proposal → marker-free approval → implementation → verification.
+ Added a reusable Markdown task template and strict content-addressed manifest
  with safe relative paths, exact SHA-256 pins, and five-status expectations.
+ Enforced proposal/approval marker separation, unchanged declarations and
  contract kinds, and exact reuse of accepted contracts by the implementation.
+ Reused the ordinary frontend, VC generator, and checker; any violation,
  unknown, unsupported result, solver error, empty proof set, or summary drift
  prevents a complete workflow report.
+ The frozen `increment_checked` task verifies contract consistency, signed-add
  safety, and its postcondition: verified=3 and every other status zero.
+ Relocating the full task directory preserves report bytes; repeated output
  matches the golden run exactly.
+ The reference suite grew from 338 to 347 tests and every test is green.
- Correction to the prior C1.3 evidence: review/acceptance validation used exact
  versioned artifact shapes and frozen goldens, not standalone JSON Schema
  resources; those files were intentionally outside the C1.3 declared scope.
- Human reviewer identity and prose correctness remain external attestations;
  the workflow proves artifact consistency and implementation obligations.
Evidence: focused contract-first tests -> 9/9; transition/path/hash/marker/status
negative matrix -> fail-closed; frozen workflow -> verified=3, all other
statuses=0; repeated/golden bytes -> equal; full reference suite -> 347/347;
commit: this stage commit.
Next: C2.2 (contract-first pilot on the verifier project).
## 2026-08-07 - C2.2: contract-first verifier pilot - DONE
+ Applied the C2.1 workflow to an already-supported signed-i32
  `guarded_absolute_value` verification increment without checker changes.
+ Started with prose and `cs: ai` proposals; human approval changed the
  INT_MIN boundary from `value > -2147483648` to the clearer
  `value != -2147483648` before any implementation artifact was recorded.
+ The marker-free accepted contracts were copied exactly into the implementation.
  The ordinary referee produced verified=6 and zero in every other status.
+ A seeded implementation that returns negative inputs unchanged deterministically
  fails with a replayed postcondition violation; two runs emitted the same error.
+ The frozen successful workflow report is byte-identical across repeated runs.
+ Compared with the earlier implementation-first process, the pilot adds an
  explicit prose/proposal/approval/run evidence chain and catches contract/code
  drift at a named transition, at the cost of three reviewed artifacts plus a
  manifest and frozen report.
- This pilot does not claim that historical A stages used contract-first, prove
  real-world reviewer identity, or establish prose correctness.
Evidence: focused contract-first tests -> 13/13; successful pilot -> verified=6,
all other statuses=0; seeded mismatch -> deterministic replayed postcondition
violation and exit=2; full reference suite -> 351/351; commit: this stage commit.
Next: C3.0 (research and expand the C++26 contracts bridge).
## 2026-08-07 - C3.0: C++26 contracts research and bridge expansion - DONE
+ Froze a versioned, dated evidence matrix from WG21 working-draft/P2900 and
  official Clang/GCC support sources; no web or compiler status enters logic.
+ Recorded the exact `pre`, `post`, and `contract_assert` grammar,
  normal-exit postcondition scope, result binding, declaration/const rules,
  attributes, and four runtime evaluation semantics.
+ Mapped `pre` to `requires`, `post` to `ensures`, and
  `contract_assert` to the existing assertion IR without approximation.
+ Kept `invariant` and `modifies` explicitly unmapped because P2900 supplies
  no loop-invariant or frame-condition spelling.
+ Official status evidence records GCC 16 experimental support and Clang's
  current P2900 status as unsupported. The local Clang 20.1.8 `-std=c++2c`
  probe independently lacked `__cpp_contracts` and rejected `pre`.
+ Chose a temporary fail-closed lexical bridge with byte/newline-stable compiler
  text and side metadata; native Clang AST nodes remain the later replacement.
+ Expanded C3.1 with exact files, soundness boundaries, negative matrix, and DoD.
- C3.0 changes no source acceptance or verification behavior; that is C3.1.
Evidence: research matrix tests -> 4/4; official source set -> exact; local
Clang probe -> exit=1 with missing macro and rejected declarator; full reference
suite -> 355/355; commit: this stage commit.
Next: C3.1 (fail-closed standard-syntax source bridge).
## 2026-08-07 - C3.1: fail-closed C++26 contracts source bridge - DONE
+ Added a deterministic lexical bridge that recognizes controlled P2900
  `pre`, `post`, and `contract_assert` forms while ignoring comments,
  ordinary/raw strings, and preprocessing directives.
+ Private compiler input preserves the original UTF-8 byte count and newline
  positions. AST/result locations remain on the original source, and temporary
  bridge/header paths never enter reports.
+ Function contracts travel as side metadata into the existing strict contract
  parser; no standard predicate bypasses the owned expression or type boundary.
+ `post(r: expression)` performs token-wise result binding without rewriting
  same-spelled members. Postconditions without a result binding also work.
+ Enforced standard const-use and result-name rules plus the declared
  first-and-only, non-virtual, attribute-free definition boundary.
+ `contract_assert` reaches the existing assertion IR/VC path through a private
  declaration, so it is proved at its source point and then assumed.
+ Mixed standard/`cs:` contracts, attributes, malformed/unattached forms,
  redeclarations, virtual/member definitions, binder conflicts, and non-const
  post-parameter use all fail closed as explicit unsupported results.
+ Standard and existing fixtures have identical IR/obligation semantic
  projections after source locations are removed.
+ The positive fixture yields verified=6 with all other statuses zero. The
  seeded false postcondition yields verified=2, violated=1 with replay.
- This is a controlled static-analysis bridge, not the complete C++26 grammar
  or a runtime contract-evaluation implementation; native Clang contract AST
  nodes remain the intended future replacement.
Evidence: focused bridge tests -> 11/11; bridge/research/frontend regression
set -> 51/51; positive CLI -> 6/6 verified; negative CLI -> exit=1 and replayed
postcondition violation; repeated text/JSON/IR -> byte-identical; full reference
suite -> 366/366; commit: this stage commit.
Next: C4.0 (expand the enforcement ladder).
## 2026-08-07 - C4.0: enforcement-ladder policy and expansion - DONE
+ Froze an exact five-status routing matrix: verified stops as static proof;
  replayed violations remain defects; solver errors remain infrastructure
  failures; only eligible unknown/unsupported surfaces may descend.
+ Defined the initial callable capability as non-void fixed-scalar by-value
  functions with no frame contract and at least one exact postcondition.
+ Ineligible unknown/unsupported results route to `manual_required`; no
  placeholder or weakened predicate is permitted.
+ Distinguished unproven, generated-unexecuted, finite passed, runtime-guarded,
  manual, defect, infrastructure, and static-verified states.
+ Only `static_verified` claims verification. Every fallback preserves the
  original status and reason.
+ Fixed SHA-256 identity inputs and excluded checkout roots, clocks, executable
  paths, seeds, and randomness from logical/generated artifacts.
+ Expanded C4.1 and C4.2 with exact files, deterministic C++17 outputs,
  provenance requirements, negative boundaries, compile/run checks, and DoD.
- C4.0 changes no source, IR, checker, report, or exit-code behavior.
Evidence: policy tests -> 4/4; all five routes and eight states frozen; full
reference suite -> 370/370; commit: this stage commit.
Next: C4.1 (deterministic property-test skeleton generation).
## 2026-08-07 - C4.1: property-test fallback generation - DONE
+ Added strict five-status routing over fresh reports with one result per
  obligation and mandatory replay evidence for every violation.
+ Eligible unknown/unsupported results collapse by function/contract identity
  into one content-addressed property target; verified path results stay
  `static_verified`.
+ Generated framework-neutral C++17 accepts caller-supplied deterministic cases,
  binds each parameter once, filters exact requirements, calls the function
  once, and asserts every exact postcondition.
+ Added canonical manifest/source/report/contract/skeleton/workflow SHA-256
  identities with source paths normalized out of logical report hashes.
+ Relocation preserves skeleton and manifest bytes; any contract change updates
  the complete identity chain and exact generated predicate.
+ Verified, replayed violations, and solver errors never generate a fallback.
  Ineligible or stale unknown/unsupported surfaces are explicit manual routes.
+ Malformed result coverage and unreplayed violations fail closed.
+ The frozen affine fixture routes one verified result plus two unsupported
  results into one generated-unexecuted property target.
+ The committed skeleton compiles as C++17 and matches both golden artifacts.
- Generated skeletons contain no cases or execution claim; passing caller cases
  remains finite evidence and never promotes the original status to verified.
Evidence: focused generator/policy tests -> 15/15; affine fixture ->
verified=1, unsupported=2, targets=1; golden CLI -> exact match; C++17 syntax
compile -> pass; full reference suite -> 381/381; commit: this stage commit.
Next: C4.2 (runtime wrappers and the three-rung demo).

## 2026-08-07 - C4.2: runtime guards and three-rung demo - DONE
+ Generated content-addressed C++17 wrappers from the same strict callable
  subset and fresh referee report used by the property fallback.
+ Every wrapper checks all requirements before exactly one original call,
  checks all postconditions after normal return, and invokes an explicit
  caller-defined failure hook.
+ Static, property, and runtime artifacts share exact target and contract-set
  identities in one deterministic provenance manifest.
+ Preserved every original referee status and reason. Runtime enforcement is
  recorded as runtime_guarded and never promotes a result to verified.
+ The affine fixture keeps verified=1 and unsupported=2 while its two eligible
  unproven routes collapse to one property and one runtime target.
+ Golden wrapper/manifests, repeated generation, and source relocation are
  byte-stable.
+ The generated wrapper compiles as C++17; a satisfying child exits 0 and
  violated requirement/postcondition children reach the hook with exit 86.
- Runtime guards are enforcement rather than proof and make no claim about
  exceptional exits. Invariants, frames, and ineligible surfaces remain manual.
Evidence: runtime tests -> 11/11; combined enforcement tests -> 26/26; full
reference suite -> 392/392; commit: this stage commit.
Next: D1.1 (deterministic fact schema).

## 2026-08-07 - plan: D1 fact-extraction expansion - DONE
+ Expanded D1.1 through D1.3 into bounded schema, extractor, and deterministic
  corpus stages with exact file sets and executable definitions of done.
+ Kept the fact-index schema independent from verification results and made
  derived purity explicitly non-proof metadata.
+ Required closed enums, content-addressed identities, resolved references,
  canonical ordering, and explicit unsupported extraction limitations.
+ Reserved extraction for D1.2 and goldens for D1.3 so D1.1 remains a schema
  contract rather than an implicit parser implementation.
- No fact-index implementation or extraction behavior changes in this entry.
Evidence: C4.2 commit hook baseline -> 392/392.
Next: D1.1 (deterministic fact schema).

## 2026-08-07 - D1.1: deterministic fact schema - DONE
+ Added the independent codeskeptic.fact-index/v1 wire contract without
  coupling it to verification-report schema versions.
+ Added immutable value objects and a strict JSON loader for symbols,
  definitions, uses, direct calls, mutations, purity, and limitations.
+ Every symbol/relation and the complete index has a recomputed
  content-addressed SHA-256 identity over canonical owned fields.
+ Canonically sort arrays, reason sets, and object keys; normalize display-path
  separators and require one-based main-source locations.
+ Enforced graph closure, owner/context rules, mutable targets, duplicate
  rejection, and exactly one purity row per function.
+ Froze derived purity as pure, impure, or unknown with closed reasons. It
  creates no verified/proved claim.
+ Added a strict machine JSON Schema and a field/reference document matching
  the loader's closed enum and object boundaries.
+ Negative tests reject unknown fields/schemas/enums, tampered identities,
  dangling relations, duplicate facts, invalid paths/hashes/locations, bad
  ownership, incomplete purity, and cross-source locations.
- D1.1 defines and validates facts only; it performs no Clang extraction,
  query, cache, or proof.
Evidence: focused fact-schema tests -> 12/12; full reference suite -> 404/404;
commit: this stage commit.
Next: D1.2 (Clang fact extraction v0).

## 2026-08-07 - D1.2: Clang fact extraction v0 - DONE
+ Added a two-pass extractor over the existing real Clang JSON-AST frontend:
  public symbols first, then resolved graph relations.
+ Indexed main-file namespaces, overloaded free functions, parameters, locals,
  globals, records, and fields without persisting Clang IDs or physical paths.
+ Emitted deterministic definitions, read/write/address uses, direct calls,
  and local/parameter/global/field mutation targets.
+ Field writes retain both the exact field and owned storage root, supporting
  field queries and caller-visible mutation classification.
+ Derived pure/impure/unknown through a deterministic direct-call fixed point;
  global/parameter effects propagate as impure and incomplete callees as
  unknown. No proof trust or verification status is created.
+ Excluded system/header declarations and preserved internal/none/external
  linkage plus scope/overload distinctions.
+ Made indirect/virtual/member calls, unresolved symbols, macro locations,
  unsupported expressions/declarations, declaration-only functions, and
  graph-relevant global initializers explicit limitations.
+ Repeated in-memory extraction with fixed source/display bytes is
  byte-identical despite different temporary paths and frontend node IDs.
- Indirect or virtual dispatch, methods, macros, allocation, lambdas,
  overloaded operators, arrays, and unsupported mutation targets are not
  approximated; affected function purity remains unknown.
Evidence: focused extractor tests -> 11/11; combined fact tests -> 23/23; full
reference suite -> 415/415; commit: this stage commit.
Next: D1.3 (deterministic fact corpus).

## 2026-08-07 - D1.3: deterministic fact corpus - DONE
+ Froze a two-case corpus for accepted world-model facts and explicit
  fail-closed extraction limitations.
+ The world case covers namespaces, overloads, shadowed locals, records/fields,
  direct call chains, local/global/parameter mutations, and purity propagation.
+ The limitation case covers indirect/virtual calls, macros, unsupported
  aliases, declaration-only callees, unresolved builtins, and unknown purity.
+ Added canonical fact-index goldens and a content-hash manifest binding every
  source, stable display path, index identity, and exact output bytes.
+ Added deterministic generation and read-only check modes with stale-golden
  refusal and no deletion behavior.
+ Strict round-trip, resolved-edge, canonical-order, original/relocated input,
  manifest-hash, and environment-exclusion tests all pass.
+ Generation is confined to fixtures/facts and leaves existing verification
  report/IR fixtures byte-identical.
- This corpus freezes D1 v0 extraction behavior; unsupported routes remain
  limitations and do not become inferred facts or proof.
Evidence: focused corpus tests -> 9/9; combined fact tests -> 32/32; full
reference suite -> 424/424; commit: this stage commit.
Next: D2.1 (world-model CLI queries).

## 2026-08-07 - plan: D2 query-interface expansion - DONE
+ Expanded D2.1 through D2.3 into bounded query, MCP, and context-pack stages
  with exact file sets and executable definitions of done.
+ Defined exact ID/qualified-name selectors, explicit ambiguity, typed
  who-calls/who-mutates boundaries, and fact-only neighborhoods.
+ Scoped D2.2 to one read-only stdio MCP tool over the pure query API, with the
  protocol version deferred to dated official evidence in that stage.
+ Defined an ASCII/UTF-8 byte ceiling equal to the requested context token
  budget, giving a conservative hard upper bound without a tokenizer package.
+ Kept every query and pack inside one validated D1 index; no heuristic
  cross-TU join, missing-edge inference, model call, or proof promotion.
- No query, MCP, or context-pack runtime behavior changes in this entry.
Evidence: D1.3 commit hook baseline -> 424/424.
Next: D2.1 (deterministic world-model queries and CLI).

## 2026-08-07 - D2.1: deterministic fact queries and CLI - DONE
+ Added pure who-calls, who-mutates, and neighborhood queries over one strictly
  validated fact-index/v1 artifact.
+ Exact content IDs or qualified names select symbols; overloaded names fail
  with deterministic typed candidate lists.
+ Caller answers preserve call IDs and sites; mutator answers preserve mutation
  IDs, kinds, and sites. Empty exact answers succeed.
+ Neighborhood uses only owns, defines, uses, calls, and mutates edges, with
  undirected BFS reachability and original edge direction retained in output.
+ Depth 0 through 8 is validated; each symbol carries its shortest distance and
  all returned arrays/objects have deterministic ordering.
+ Relevant module/symbol limitations remain visible without becoming inferred
  edges or answers.
+ Added canonical codeskeptic.fact-query-result/v1 JSON, deterministic text,
  and a standalone CLI with distinct success/query/input exit codes.
- Queries do not extract, infer missing relations, heuristically join TUs,
  resolve limitations, call a model/referee, or create proof trust.
Evidence: focused query/CLI tests -> 9/9; combined fact/query tests -> 41/41;
full reference suite -> 433/433; commit: this stage commit.
Next: D2.2 (MCP fact-query endpoint).

## 2026-08-07 - plan: align D2.2 with MCP 2026-07-28 - DONE
+ Replaced the removed initialize/notifications/initialized handshake with the
  current stateless, per-request metadata contract.
+ Added required server/discover, resultType, server identity, and cache-field
  coverage to the D2.2 boundary and definition of done.
+ Preserved newline-delimited JSON-RPC stdio framing and the read-only query
  surface, both explicitly supported by the current specification.
- This entry changes plan text only; the D2.2 endpoint remains to be built.
Evidence: official MCP 2026-07-28 specification, changelog, stdio transport,
discovery, tools, and schema pages reviewed on 2026-08-07; full suite baseline
remains 433/433.
Next: D2.2 (MCP fact-query endpoint).
## 2026-08-07 - D2.2: MCP fact-query endpoint - DONE
+ Froze the official MCP 2026-07-28 stateless protocol profile from dated
  primary specification evidence.
+ Added a dependency-free newline-delimited UTF-8 JSON-RPC stdio server with
  required per-request metadata, server/discover, resultType, cache fields,
  and server identity.
+ Exposed one deterministic read-only codeskeptic.query_facts tool over the
  exact D2.1 who-calls, who-mutates, and neighborhood API.
+ Successful calls return matching canonical text and structured content;
  limitations remain explicit facts and never become inference or proof.
+ Protocol, version, method, tool, parameter, query, malformed JSON, non-finite
  JSON, invalid UTF-8, notification, stdout/stderr, and clean EOF paths are
  deterministic and fail closed.
+ Tool discovery declares read-only, idempotent, closed-world, non-destructive
  behavior and returns in stable order.
- Legacy initialize, HTTP transports, sessions, model calls, fact extraction,
  file mutation, proof promotion, and inferred relations are out of scope.
Evidence: focused MCP tests -> 11/11; combined fact/MCP tests -> 52/52; full
reference suite -> 444/444; commit: this stage commit.
Next: D2.3 (compact fact-based context packs).

## 2026-08-07 - D2.3: compact fact context packs - PARTIAL
+ Focused context tests pass 10/10; combined fact/context tests pass 62/62.
+ The frozen context pack is canonical and 1906/2000 bytes.
- First full-suite process was externally terminated before its summary.
- The retry reached 454 tests but tests/test_fixtures.py timed out while running
  tools/regenerate_fixtures.py after 30 seconds; no D2.3 assertion failed.
Resume: run python -m unittest tests.test_fixtures.FixtureInfrastructureTests.test_two_independent_regenerations_are_byte_identical -v, then rerun
python -m unittest discover -s tests.

## 2026-08-07 - D2.3: compact fact-based context packs - DONE
+ Added canonical codeskeptic.fact-context/v1 packs with an exact root and
  content-addressed source/index provenance envelope.
+ Enforced a hard ASCII/UTF-8 byte ceiling equal to the requested conservative
  token budget; the default and maximum are 2000 bytes.
+ Ranked only indexed purity, explicit limitations, and exact depth-eight graph
  relations by distance and stable semantic priority.
+ Kept the longest ranked prefix that fits and reported exact omitted
  limitation, purity, relation, and total counts.
+ Froze a 1906-byte golden containing pipeline purity and both direct callees.
+ Added deterministic generation and read-only check modes with distinct
  selector/budget, stale-check, and input/output failures.
+ Exact minimum-envelope errors, repeated calls, exact-ID selectors, relocated
  index files, and limitation/unknown trust paths are byte-stable.
- No source reconstruction, inferred facts, proof promotion, model call, wall
  clock, randomness, or unstable physical path enters a context pack.
+ The earlier PARTIAL fixture timeout was isolated as process contention; its
  focused retry passed and the clean full-suite rerun passed.
Evidence: focused context tests -> 10/10; combined fact/context tests -> 62/62;
isolated fixture retry -> 1/1; full reference suite -> 454/454; commit: this
stage commit.
Next: D3.0 (architectural-rule enforcement expansion).

## 2026-08-07 - D3.0: architectural-rule expansion - DONE
+ Split D3 into a strict policy-schema stage and a fact-based enforcement/SARIF
  stage with exact file sets and executable definitions of done.
+ Defined a complete ordered layer-pair matrix with no implicit allow/forbid
  default and deterministic exact/prefix classification.
+ Limited enforceable dependencies to resolved direct D1 call facts.
+ Made unclassified/ambiguous endpoints and every fact-index limitation
  explicit unknown findings, with unknown taking aggregate precedence.
+ Fixed actionable evidence, stable SARIF rule/location requirements, and
  clean/violation/unknown/error CLI exit semantics.
- No policy parser or architecture runtime behavior changes in this entry.
Evidence: D2.3 commit hook and D3.0 baseline -> 454/454.
Next: D3.1 (strict architectural dependency policy).

## 2026-08-07 - D3.1: strict architectural dependency policy - PARTIAL
+ Policy model, canonical fixture, validation CLI, and focused tests pass 9/9.
- The first 463-test DoD run hit two existing tests/test_fixtures.py
  subprocess timeouts at their fixed 30-second limit; no D3.1 test failed.
Resume: run python -m unittest tests.test_fixtures -v, then rerun
python -m unittest discover -s tests from a clean process state.

## 2026-08-07 - F2.3: calibrated fixture subprocess timeout - DONE
+ Measured one cold fixture regeneration at about 59 seconds after the original
  30-second subprocess budget became a systematic false failure.
+ Replaced duplicated literals with one named 120-second test-only timeout,
  providing at least 2x measured headroom while retaining a finite bound.
+ Preserved both independent-process executions, manifest/summary checks, exact
  artifact comparison, expected bytes, and fixture generation behavior.
+ The previously failing fixture infrastructure tests pass 3/3.
- No verifier, fixture, manifest, golden, pass criterion, or test count changed.
Evidence: fixture infrastructure -> 3/3; full reference suite -> 454/454;
commit: this stage commit.
Next: resume D3.1 (strict architectural dependency policy) from
stash wip/D3.1-before-F2.3.

## 2026-08-07 - D3.1: strict architectural dependency policy - DONE
+ Added frozen, content-addressed codeskeptic.architecture-policy/v1 value
  objects with canonical sorted-key ASCII JSON.
+ Defined literal exact qualified-name, qualified-name-prefix, and normalized
  relative source-prefix selectors without glob/regex semantics.
+ Classification returns all zero/one/multiple matching layers in sorted policy
  order; selector order never hides ambiguity.
+ Required one explicit allow/forbid decision for every ordered layer pair,
  including self, with no default.
+ Strict loading rejects malformed JSON, duplicate object keys, non-finite
  numbers, unknown/missing fields, invalid names/paths/kinds/decisions,
  duplicate layers/selectors/pairs, incomplete matrices, and stale IDs.
+ Added a canonical three-layer policy fixture and validation CLI.
- This stage defines policy only; it does not inspect calls, infer dependencies,
  emit compliance, invoke a model/referee, or produce proof.
+ F2.3 resolved the earlier fixture timeout; the resumed clean DoD passed.
Evidence: focused policy/CLI tests -> 9/9; full reference suite -> 463/463;
commit: this stage commit.
Next: D3.2 (fact-based enforcement and deterministic SARIF).

## 2026-08-07 - D3.2: fact-based architecture enforcement and SARIF - DONE
+ Checked every resolved direct call exactly once against the complete D3.1
  matrix and preserved allow/forbid decisions with exact call IDs and sites.
+ Added canonical codeskeptic.architecture-result/v1 JSON plus deterministic
  text and SARIF 2.1.0 renderings.
+ The frozen world result decides all three calls: two allowed and one forbidden
  orchestration-to-storage dependency.
+ Unclassified or multiply classified endpoints become explicit call-local
  unknown findings without fabricated decisions.
+ Every fact-index limitation becomes an unknown finding; unknown takes
  aggregate precedence over known violations, then violation over clean.
+ SARIF uses stable CSARCH001/CSARCH002 rules, normalized relative URIs,
  one-based regions, exact/content fingerprints, and no unstable run state.
+ Added clean self-layer, forbidden, unclassified, ambiguous, limitation,
  precedence, CLI exit, malformed input, repeated, and relocated tests.
- Enforcement is limited to indexed resolved direct calls; clean architecture
  status is policy compliance for that graph, not semantic verification/proof.
Evidence: focused enforcement tests -> 10/10; combined architecture tests ->
19/19; full reference suite -> 473/473; commit: this stage commit.
Next: D4 (incremental fact extraction expansion).

## 2026-08-07 - D4.0: incrementality expansion - DONE

+ Replaced the one-line D4 placeholder with one bounded implementation stage
  for strict content-addressed translation-unit extraction.
+ Froze cache keys, hit validation, atomic writes, path portability,
  fail-closed corruption behavior, and explicit non-goals before coding.
+ Full suite reported 473/473 passing in 297.656 s; the outer command wrapper
  reached its 298 s limit after unittest had printed OK.
- No blockers.
Next: D4.1 - implement and prove the incremental extraction cache.

## 2026-08-07 - D4.1: content-addressed TU extraction cache - DONE

+ Added strict translation-unit declarations and content-addressed cache state
  with canonical identities for the source, display path, fact schema, and
  extractor contract.
+ Warm hits validate canonical manifest/index bytes, graph identity, source
  hash, display path, and cache-key derivation before reuse; corruption fails
  closed instead of becoming a miss.
+ Cold extraction, exact one-TU invalidation, add/remove accounting, relocated
  byte stability, atomic current-state preservation, and no-write check mode
  are frozen over a two-TU C++17 corpus.
+ CLI exit codes distinguish current, stale, and input/extraction error states;
  documentation fixes the non-goals and operational contract.
- No blockers.
Evidence: focused incrementality tests -> 12/12; frozen cache check -> current
with 2/2 reused; full reference suite -> 485/485 in 348.319 s; commit: this
stage commit.
Next: D5.0 - expand referee-backed fact trust promotion.

## 2026-08-07 - D5.0: verified-fact trust expansion - DONE

+ Split D5 into a strict D1-linked trust overlay and a separate referee-backed
  promotion engine before introducing any proved label.
+ Froze proof eligibility around explicit human-authored empty frames, complete
  non-empty verified VC sets, exact source/report evidence, and already-proved
  direct callees.
+ Explicitly excluded synthetic true obligations, derived-callee trust,
  incomplete results, cross-TU inference, and mutation of the D1 fact index.
+ The immediately preceding D4.1 commit hook passed the full 485/485 suite.
- No blockers.
Next: D5.1 - implement the strict fact-trust overlay.

## 2026-08-07 - D5.1: strict fact-trust overlay - DONE

+ Added immutable codeskeptic.fact-trust/v1 claim and overlay identities linked
  to one exact D1 fact-index identity and source hash.
+ Enforced one claim per D1 purity row, derived/proved value rules, fixed proof
  evidence, exact proved direct-callee coverage, and acyclic proof dependency.
+ Added strict duplicate/unknown/value/evidence/identity/cross-index negatives,
  canonical shuffled-input stability, and a matching Draft 2020-12 JSON Schema.
+ Documented that structural JSON validity is not proof that a referee ran and
  that only D5.2 is the controlled proved-trust producer.
- No blockers.
Evidence: focused trust-overlay tests -> 11/11; schema JSON parse -> clean;
full reference suite -> 496/496 in 372.714 s; commit: this stage commit.
Next: D5.2 - implement referee-backed pure-claim promotion.

## 2026-08-07 - D5.2: referee-backed pure-claim promotion - DONE

+ Added a one-parse pipeline that derives the D1 index and Semantic IR from the
  same FrontendUnit, retains the full verification report, and emits a linked
  trust overlay.
+ Proved promotion requires an exact definition/IR match, an explicit
  human-authored empty frame, a complete non-empty all-verified result set, no
  relevant limitation, and already-proved exact direct callees.
+ Zero/incomplete, violated, unknown, unsupported, solver-error, impure,
  unknown-purity, external-callee, overload, machine-frame, non-empty-frame,
  and module-limitation cases remain derived.
+ Bound referee IDs to exact built-in checker implementations; custom or
  mismatched checker labels are rejected before artifact production.
+ Froze a 2-proved/2-derived four-artifact bundle, relocation stability, atomic
  writes, exact check mode, stale-artifact detection, and CLI exit behavior.
- No blockers.
Evidence: focused promotion tests -> 14/14; frozen bundle check -> exact,
proved=2 and derived=2; full reference suite -> 510/510 in 311.032 s; commit:
this stage commit.
Next: E1.0 - expand the repair-loop bullets into bounded implementation stages.

## 2026-08-07 - E1.0: repair-loop expansion - DONE

+ Replaced the coarse E1 bullets with bounded replay-attested bundle, untrusted
  proposer harness, and append-only telemetry stages.
+ Froze the original-obligation recheck, exact iteration cap, referee-only
  success decision, non-mutating source policy, and complete attempt logging.
+ Isolated monotonic elapsed-time measurement at the orchestration boundary so
  it cannot influence logic-path decisions, artifact IDs, or ordering.
+ The immediately preceding D5.2 commit hook passed the full 510/510 suite.
- No blockers.
Next: E1.1 - implement the replay-attested repair bundle.

## 2026-08-07 - E1.1: replay-attested repair bundle - DONE

+ Added strict codeskeptic.repair-bundle/v1 identities, loader, JSON Schema,
  source/report cross-validation, and canonical obligation/result evidence.
+ Builder reproduces the complete report from source, then independently checks
  the original obligation and requires the identical concrete violated result.
+ Bundles preserve bounded exact source lines plus human/machine provenance for
  every related requires, ensures, and modifies contract.
+ Bound referee labels to exact built-in affine/Z3/cross-check implementations;
  custom/mismatched checkers and every non-replayable state fail closed.
+ Added deterministic CLI generate/check behavior and a frozen violated golden.
- No blockers.
Evidence: focused repair-bundle tests -> 14/14 including installed Z3 replay;
golden check -> exact; full reference suite -> 524/524 in 260.499 s; commit:
this stage commit.
Next: E1.2 - implement the bounded untrusted-proposer repair harness.

## 2026-08-07 - E1.2: bounded untrusted-proposer repair harness - DONE

+ Added strict content-addressed line-edit proposals, offline proposal scripts,
  attempt records, canonical loop logs, and a PatchProposer abstract seam.
+ Harness applies at most 1-8 in-memory proposals, re-verifies every candidate,
  rebundles replayable violations, stops on first verified success, and logs
  exactly N attempts on exhaustion.
+ Success requires a non-empty all-verified target result set, no module
  failure, and byte-equivalent bundled contracts/provenance; deleting intent
  cannot manufacture success.
+ Stale/range/UTF-8/no-op/reused/non-proposal/proposer-error and nonverified
  candidates are rejected or referee-blocked without modifying the source file.
+ Froze first-shot success and two-attempt exhaustion plus CLI check behavior.
- No blockers.
Evidence: focused repair-loop tests -> 13/13; both frozen logs -> exact; full
reference suite -> 537/537 in 267.047 s; commit: this stage commit.
Next: E1.3 - add append-only repair metrics telemetry.

## 2026-08-07 - E1.3: append-only repair metrics telemetry - DONE

+ Added strict codeskeptic.repair-metrics/v1 rows linked to exact repair bundle,
  loop, and obligation identities with content-addressed metric IDs.
+ Isolated monotonic nanosecond measurement immediately around the deterministic
  harness call; injected durations cannot change proposals, decisions, or loop
  artifacts.
+ Added canonical append-only JSONL validation that preserves prior bytes and
  rejects duplicate loop/metric IDs or malformed existing ledgers before write.
+ Added exact order-independent aggregation, record/summary CLI behavior, and
  frozen successful/exhausted metric rows.
+ Documented telemetry boundaries and usage.
- No blockers.
Evidence: focused repair-metrics tests -> 12/12; full reference suite -> 549/549
in 291.930 s; commit: this stage commit.
Next: E2.0 - expand the consciousness experiment into bounded stages.

## 2026-08-07 - E2.0: bounded consciousness-experiment expansion - DONE

+ Replaced the coarse experiment bullets with three executable stages covering
  a twenty-case corpus, paired isolated-context trials, and exact reporting.
+ Froze the four-proposal cap, referee-only outcomes, cap-plus-one exhaustion
  scoring, all-case medians, and reduced-rational threshold comparison.
+ Required strict context isolation, immutable proposal provenance, complete
  paired traceability, and fail-closed contamination/tamper checks.
+ Limited conclusions to the recorded proposer evidence class; the protocol
  cannot establish consciousness, general model behavior, or causality.
+ The immediately preceding E1.3 gate passed the full 549/549 suite.
- No blockers.
Next: E2.1 - implement the seeded-bug experiment corpus.

## 2026-08-07 - E2.1: seeded-bug experiment corpus - DONE

+ Added a strict content-addressed corpus manifest with twenty unique standalone
  supported-subset functions, compiler/test contexts, and separate repair
  oracles.
+ Every original has one isolated concrete replayable postcondition violation;
  every one-line non-contract oracle produces a complete all-verified result.
+ Arm-A contexts preserve line numbers while blanking all contracts and exclude
  obligations, IR, bundles, counterexamples, and oracle records.
+ Added hash/path/schema/file-set/UTF-8/canonical-data negatives, relocation
  stability, deterministic checker CLI behavior, and local LF enforcement.
- No blockers.
Evidence: corpus checker -> 20/20 violated, 20/20 independently replayed, and
20/20 repaired/verified; focused corpus tests -> 14/14; full reference suite ->
563/563 in 326.171 s; commit: this stage commit.
Next: E2.2 - run the paired two-arm repair trials.

## 2026-08-07 - E2.2: paired two-arm repair trials - PARTIAL

+ Paired contexts, proposal transcripts, forty referee-run trial rows, CLI, and
  14/14 focused tests are implemented.
- Full discovery exposed order-dependent setup failures: e2-case-09's repaired
  oracle was not fully verified, then e2-case-01 lacked one replayable target.
- Resume by reproducing the test-order leak before tests.test_experiment_corpus
  and tests.test_experiment_e2; do not stage or commit until 577/577 is green.
Evidence: `python -m unittest discover -s tests` -> 549 executed with 2 setup
errors in 437.196 s.

## 2026-08-07 - E2.4: batched corpus frontend calibration - DONE

+ Replaced sixty repeated per-case frontend passes with one sorted combined
  original pass and one sorted combined repaired pass.
+ Preserved all twenty isolated violation decisions and replayed each exact
  obligation independently with the same affine referee.
+ Preserved every standalone source, content hash, diagnostic, oracle edit,
  contract, and 20/20 repaired-verification outcome.
+ Added no retry, cache, approximation, timing, or skipped case.
- No blockers.
Evidence: focused corpus tests -> 14/14; full reference suite to be recorded by
this stage gate; commit: this stage commit.
Next: resume E2.2 from the protected `wip/e2.2-before-corpus-calibration` stash.

## 2026-08-07 - E2.4: verification addendum - DONE

+ The isolated calibration worktree passed the complete ratcheted suite with no
  recurrence of the prior order-dependent frontend failure.
- No blockers.
Evidence: focused corpus tests -> 14/14; full reference suite -> 563/563 in
560.590 s; commit: this stage commit.
Next: resume E2.2 from the protected stash.

## 2026-08-07 - E2.2: paired two-arm repair trials - DONE

+ Added forty strict paired trial rows over the same twenty sources, affine
  referee, repair harness, and fixed four-proposal cap.
+ Arm A exposes only contract-redacted source plus one black-box test failure;
  arm B exposes exactly the replay-attested E1.1 bundle.
+ Frozen scripts carry one immutable recorded-scripted-proxy provenance class;
  only complete verifier acceptance produces success, and exhaustion scores 5.
+ Embedded every repair-loop log and enforced exact corpus/context/script/
  proposal/bundle/source links plus contamination and tamper negatives.
+ Raw outcomes are compiler_test 16/20 verified and semantic_bundle 20/20; E2.3
  owns the predeclared median calculation and bounded conclusion.
- No blockers. The earlier order-dependent frontend failure was resolved and
  committed independently as E2.4 before this stage resumed.
Evidence: focused paired-trial tests -> 14/14; frozen generate/check -> exact;
full reference suite -> 577/577 in 358.904 s; commit: this stage commit.
Next: E2.3 - generate the honest paired experiment report.

## 2026-08-07 - E2.3: honest paired experiment report - DONE

+ Added strict codeskeptic.experiment-report/v1 recomputation from all forty
  linked rows; the four exhausted trials remain scored at cap-plus-one.
+ Computed exact medians 7/2 and 1, exact semantic-bundle reduction 5/7, and the
  predeclared 2/5 threshold using reduced rational arithmetic only.
+ The frozen recorded-scripted-proxy protocol passes because 5/7 >= 2/5; every
  case cites both trial and repair-loop identities for raw traceability.
+ Documented that this result does not measure an independently sampled model
  and cannot establish consciousness, general model behavior, or causality.
+ Added strict score/median/threshold/outcome/link/provenance/limitation tamper
  negatives and deterministic generate/check CLI behavior.
- No blockers.
Evidence: focused report tests -> 13/13; frozen report check -> exact and passed;
full reference suite -> 590/590 in 323.640 s; commit: this stage commit.
Next: E3.0 - expand the assumption declaration stages.

## 2026-08-07 - E3.0: bounded assumption-protocol expansion - DONE

+ Replaced the coarse assumption bullets with immutable declaration, linked
  resolution, and real declaration-before-code pilot stages.
+ Froze exact input snapshots, one-to-one dispositions, evidence path/hash/
  anchor checks, and honest uncheckable reasons that never become verified.
+ Required a separate pilot declaration commit before any resolving tool, test,
  or overlay artifact exists.
+ The immediately preceding E2.3 commit hook passed the full 590/590 suite.
- No blockers.
Next: E3.1 - implement the immutable assumption manifest and resolution overlay.

## 2026-08-07 - E3.1: immutable assumption manifest and resolution - DONE

+ Added immutable content-addressed declaration manifests with exact normalized
  UTF-8 input snapshots and risk/disposition-tagged assumptions.
+ Added a separately content-addressed one-to-one resolution overlay for exact
  contract/test evidence paths, hashes, and anchors or honest uncheckable reasons.
+ Uncheckable rows reject evidence, never count as verified, and remain distinct
  in deterministic summaries; evidence links never claim referee/test success.
+ Added strict path/root/symlink, snapshot/evidence/hash/anchor, coverage,
  disposition, UTF-8, JSON, identity, relocation, and schema checks plus CLI.
- No blockers.
Evidence: focused assumption-manifest tests -> 14/14; frozen fixture summary ->
1 contract, 1 test, 1 uncheckable; full reference suite -> 604/604 in 350.621 s;
commit: this stage commit.
Next: E3.2 - run the repository-local declaration-before-code pilot.

## 2026-08-07 - E3.2: repository-local assumption pilot - PARTIAL

+ Froze the pilot declaration before authoring any resolving overlay, pilot
  checker, or pilot evidence test.
+ Declaration `sha256:13ecfcb8a49d419ad196106836d3d26818399d6eb8d77d0d69d89cd996c55ebb`
  snapshots five exact existing inputs and declares six assumptions.
+ Five assumptions intend repository tests; one external-model generalization
  claim is explicitly intended to remain uncheckable.
- Closure artifacts intentionally do not exist in this declaration sub-gate.
Resume after this commit by creating `pilots/assumption_protocol/e3-pilot.resolution.json`,
`tools/run_assumption_pilot.py`, and `tests/test_assumption_pilot.py` without
changing the declaration bytes or ID.

## 2026-08-07 - E3.2: repository-local assumption pilot - DONE

+ Preserved declaration `sha256:13ecfcb8a49d419ad196106836d3d26818399d6eb8d77d0d69d89cd996c55ebb`
  byte-for-byte after its separately committed declaration sub-gate.
+ Linked five checkable assumptions to exact test evidence hashes and anchors;
  all five pass through the declared repository test command.
+ Retained external-model generalization as one evidence-free uncheckable row;
  it never contributes to a verified or resolved-checkable claim.
+ Added deterministic closure summary/check execution, relocation and stale-
  evidence negatives, and an honest bounded pilot report.
- No blockers.
Evidence: focused pilot tests -> 9/9; frozen pilot check -> 5 test, 1
uncheckable; full reference suite -> 613/613 in 296.899 s; declaration commit
`ad3667d` precedes this closure commit; commit: this stage commit.
Next: E4.0 - expand the referee-guided search stage.

## 2026-08-07 - E4.0: bounded referee-guided search expansion - DONE

+ Replaced the coarse search bullet with an exhaustive twenty-case, N=4
  candidate/evaluation contract and exact rank-1 single-shot comparator.
+ Froze all-eighty independent checks, no early stop or sequential mutation,
  lowest-rank verified selection, and an absolute uplift threshold of 2/5.
+ Classified the calibration as an oracle-seeded recorded scripted proxy that
  cannot establish proposer-model behavior or causal search uplift.
+ The immediately preceding E3.2 commit hook passed 613/613 tests.
- No blockers.
Next: E4.1 - implement and measure exhaustive Best-of-4 search.
## 2026-08-07 - E4.0: bounded referee-guided search expansion - PARTIAL

+ The detailed E4.1 contract and active TODO were authored within the declared
  planning-only file set.
- The mandatory hook exposed that the E3.2 pilot validates its historical
  PLAN.md snapshot against the evolving live worktree; the suite failed 604/613
  before E4.0 could commit.
- No E4 implementation files were created. Insert corrective E3.3 before
  resuming this stage; preserve the E3.2 declaration bytes and identity.
Evidence: pre-commit full suite -> 604 passed, 1 setUp error in
`tests.test_assumption_pilot.AssumptionPilotTests`; exact cause:
`manifest snapshot hash is stale: PLAN.md`.
Resume from PLAN.md by defining E3.3 historical snapshot replay, then update
`tools/run_assumption_pilot.py` and `tests/test_assumption_pilot.py` only under
that declared corrective stage.
## 2026-08-07 - E3.3: historical pilot snapshot replay - DONE

+ Archived all five declaration-commit snapshot paths at their exact normalized
  hashes without changing the E3.2 manifest bytes or identity.
+ Split immutable archive validation from live repository test execution through
  explicit CLI roots; no validation-time git or mutable-root inference remains.
+ Archived the exact cited evidence file and retained all five evidence hashes/
  anchors plus the honest uncheckable external-model boundary.
+ Added archive completeness, live-PLAN divergence, byte-tamper, relocation,
  repeated-summary, and CLI-root coverage within the existing nine tests.
- No blockers. This corrective gate resolves the E4.0 hook failure.
Evidence: focused pilot tests -> 9/9; frozen pilot check -> exact; full reference
suite -> 613/613 in 344.166 s; commit: this stage commit.
Next: resume E4.0 and commit the already-authored search expansion.
## 2026-08-07 - E4.0: bounded referee-guided search expansion - DONE (resumed)

+ Resumed only after E3.3 committed the historical-pilot correction and its
  hook passed the complete 613-test suite.
+ The previously authored E4.1 contract remains unchanged: twenty cases, four
  original-source candidates each, eighty mandatory checks, rank-1 comparator,
  lowest-rank verified selection, and exact 2/5 absolute-uplift threshold.
+ No candidate, evaluator, result, or model evidence was created in this stage.
- No blockers.
Evidence: E3.3 full suite and commit hook -> 613/613; commit: this stage commit.
Next: E4.1 - implement and measure exhaustive Best-of-4 search.
## 2026-08-07 - E4.1: exhaustive Best-of-N referee search calibration - DONE

+ Added content-addressed twenty-case/four-candidate artifacts with eighty unique
  original-source proposals and explicit oracle-seeded scripted provenance.
+ Evaluated all eighty candidates in one deterministic referee batch, including
  every rank after an earlier success; no early stop or sequential mutation.
+ Selected only the lowest-rank completely verified candidate: rank-1
  single-shot succeeded 4/20 and exhaustive Best-of-4 succeeded 18/20.
+ Exact absolute uplift is 7/10 and passes the predeclared 2/5 threshold.
+ Added strict loaders/schemas, relocation/repetition, linkage, contract/no-op,
  incomplete/false-selection/status-promotion/arithmetic/JSON/CLI negatives,
  and an honest proxy-only report.
- No blockers. The result is not model output and establishes no model search
  uplift, general behavior, consciousness, or causality.
Evidence: focused search tests -> 11/11; frozen generate/check -> exact, 80/80;
full reference suite -> 624/624 in 302.480 s; commit: this stage commit.
Next: E5.0 - expand the memo-only RLVF stage before E5.1.
## 2026-08-07 - E5.0: bounded RLVF memo expansion - DONE

+ Replaced the coarse RLVF bullet with a memo-only design contract covering
  categorical eligibility, immutable provenance/splits, and raw event audit.
+ Froze null reward for unknown/unsupported/error/partial/stale/unreplayed
  evidence and retained the ordinary referee as the only acceptance authority.
+ Required selection-bias and reward-hacking threats, replay/audit rules,
  limitations, and unresolved decisions without any claimed training result.
+ The immediately preceding E4.1 commit hook passed 624/624 tests.
- No blockers.
Next: E5.1 - author the bounded referee-as-reward design memo.
## 2026-08-07 - E5.1: referee-as-reward design and data-schema memo - DONE

+ Added a non-executable research memo with an explicit AI/proposer versus
  deterministic-referee trust boundary and fail-closed terminal state table.
+ Specified a draft content-addressed reward-event field contract and canonical
  illustrative example without creating an executable schema or collector.
+ Defined immutable ancestry-grouped splits, full candidate accounting,
  append-only raw events, deterministic derivation, replay, and audit queries.
+ Covered contract/unsupported/timeout/retry/leakage/verifier/provenance/privacy
  reward-hacking threats, mitigations, incident handling, and open decisions.
- No blockers. No RLVF dataset, training/model run, optimizer, service, measured
  reward-learning result, or production recommendation exists.
Evidence: full reference suite -> 624/624 in 335.750 s; no implementation/test
files added; commit: this stage commit.
Next: F1.0 - expand the benchmark corpus, runner, and trend gates.
## 2026-08-07 - F1.0: bounded benchmark/trend expansion - DONE

+ Expanded F1 into a forty-function/four-tier corpus, append-only run evidence,
  and an exact three-point logical trend with prospective A-gate policy.
+ Isolated monotonic batch timing as informational evidence that cannot affect
  verification, rate arithmetic, trend selection, or red/green decisions.
+ Required three honestly labeled current-version calibration observations
  rather than fabricating historical A-gate runs.
+ Froze red fail-closed transitions for verified loss, violated promotion,
  increased unknown/unsupported/error coverage, and incomplete case/point data.
+ The immediately preceding E5.1 commit hook passed 624/624 tests.
- No blockers.
Next: F1.1 - build the curated supported-subset benchmark corpus.
## 2026-08-07 - F1.1: curated benchmark corpus - PARTIAL

+ Authored the initial forty-function translation unit and probed all raw
  referee statuses before creating a manifest, loader, tests, or status claims.
- The probe correctly showed nonlinear multiplication is affine-referee
  `unsupported`, not the `unknown` required by the frozen F1.1 contract.
- Stop before manifest/evidence authoring. Insert F1.4 to replace the planned
  tier with supported deterministic-search-frontier cases; never relabel the
  observed unsupported results.
Evidence: initial batch -> 40 functions, 20 verified, 10 violated, 0 unknown,
10 unsupported; representative six-parameter affine frontier probe ->
contract-consistency unknown, postcondition verified, zero unsupported nodes.
Resume after F1.4 by replacing only the ten untracked nonlinear source cases,
then implement the declared F1.1 file set.
## 2026-08-07 - F1.1: curated supported-subset benchmark corpus - DONE (resumed)

+ Added a content-addressed forty-function corpus with four explicit ten-case
  tiers and one exact combined affine-referee pass.
+ Frozen outcomes are 20 verified, 10 replay-attested violated, 10 supported
  checker unknown, and 0 unsupported; every function matches its declaration.
+ The corrected deterministic-search frontier uses only affine expressions and
  keeps unknown distinct from unsupported without changing checker budgets.
+ Added strict manifest/schema/file/function/tier/status/evidence/replay checks,
  relocation/repetition, malformed/tamper negatives, CLI, and documentation.
- No blockers. F1.4 corrected the initially detected plan mismatch before this
  manifest or any F1.1 evidence claim was authored.
Evidence: focused corpus tests -> 9/9; corpus CLI -> 40/40 exact; full reference
suite -> 633/633 in 402.860 s; commit: this stage commit.
Next: F1.2 - add append-only benchmark run evidence.
## 2026-08-07 - F1.2: append-only benchmark run evidence - DONE

+ Added strict content-addressed benchmark-run rows with complete forty-function
  statuses, exact counts/reduced rates, explicit label/date/revision, and pinned
  referee/toolchain configuration.
+ Isolated monotonic batch duration from `logic_sha256`; changing timing changes
  the raw event identity but never status, rate, acceptance, or logical identity.
+ Recorded real `f1-calibration-001` at F1.1 revision
  `f46fbdfce48934c12b2038aa8d38a78571cfa887`: 15,488,756,000 ns,
  20 verified, 10 violated, 10 unknown, and 0 unsupported.
+ Added prefix-preserving append, strict ledger row/history validation,
  timing/config/count/rate/case/tamper negatives, relocation, summary, and CLI.
- No blockers. The recorded duration is informational and is not a threshold or
  performance claim.
Evidence: focused run-evidence tests -> 9/9; frozen ledger -> 1 complete row;
full reference suite -> 642/642 in 412.528 s; commit: this stage commit.
Next: F1.3 - add the three-point logical trend and red regression gate.

## 2026-08-07 - F1.3: three-point logical trend and red regression gate - DONE

+ Added a deterministic `codeskeptic.benchmark-trend/v1` artifact derived from
  every complete ledger row in append order, with separate raw and logical
  identities and explicit zero solver-error coverage.
+ Captured real `f1-calibration-002` and `f1-calibration-003` observations at
  revision `552e2b587e8d0b837bbb85c48686b0e090396537`; all three current-version
  points retain 20 verified, 10 violated, 10 unknown, and 0 unsupported.
+ The current trend is green with no regressions; timing remains displayed but
  excluded from `logic_sha256` and every acceptance decision.
+ Verified-loss, violated-promotion, unknown/unsupported growth, unreviewed
  promotion, missing/error rows, omitted/reordered/cherry-picked points, stale
  identity, false historical labels, and noncanonical artifacts fail closed.
+ Expanded the declared F1.3 file set before adapting the F1.2 tests: exact
  first-row assertions remain, while the obsolete permanent-one-row assumption
  no longer conflicts with valid append-only growth.
+ Documented the future A-gate real-observation rule and explicit reviewed-
  baseline requirement; the gate cannot approve its own baseline change.
- No blockers. Initial F1 labels are calibration observations, never fabricated
  historical A-gate evidence, and their operational durations are not a speed
  claim.
Evidence: F1.2 + F1.3 focused suites -> 19/19; frozen ledger/trend -> 3 complete
points, green, trend `sha256:f5fa9e0d3c4fbf3c6bc2c117c38a08a8f0c167ec762d0fba13a214a59888a172`;
generate/check CLI -> 0/0; full reference suite -> 652/652 in 444.040 s;
commit: this stage commit.
Next: FINAL - audit every plan stage, gate, ledger entry, and invariant.

## 2026-08-07 - F1.4: supported-unknown tier correction - DONE (historical ledger repair)

+ Linked the planning-only correction commit `8eca621f3afb8bd5535f43b1873f2711fc96fffb`
  to its declared stage: nonlinear affine-unsupported cases were replaced in the
  F1.1 contract by supported deterministic-search-frontier unknown cases.
+ Preserved the original forty-case size, 20/10/10/0 target, checker budget,
  status taxonomy, and implementation boundary; the subsequent F1.1 evidence
  contains zero unsupported cases and genuine supported checker unknowns.
- The original F1.4 commit updated PLAN/TODO and appended the interrupted F1.1
  record but omitted a dedicated F1.4 DONE heading. This append-only historical
  ledger repair corrects that bookkeeping omission without changing evidence.
Evidence: original six-parameter affine probe -> contract-consistency unknown,
postcondition verified, zero unsupported nodes; correction commit changed only
PLAN.md, PROGRESS.md, and TODO.md; F1.1 later passed 633/633.
Next: closure audit.

## 2026-08-07 - chore: full roadmap closure audit - DONE

+ Matched all 111 declared PLAN stage IDs to DONE ledger records after the
  explicit F1.4 bookkeeping repair; no stage is missing and PLAN carries no
  completion status.
+ Confirmed 108 stage-ID commits plus the combined F0 bootstrap commit covering
  F0.1-F0.3; every PARTIAL stage (D2.3, D3.1, E2.2, E3.2, E4.0, F1.1) has a
  later DONE record.
+ Rechecked deterministic semantic and fact fixtures; scaling, fixed-width, and
  semantic-extension gates; architecture policy and exact expected violation;
  E2 corpus/trials/report; E3 archived pilot; exhaustive referee search; and F1
  corpus/trend artifacts.
+ Confirmed the 652-test ratchet, `.githooks` activation, repository object
  integrity, green three-point trend, complete counterexample replay coverage,
  and fail-closed status separation through the full guarded suite.
- No product blocker remains in this reference roadmap. `AGENTS.md` remains an
  intentionally untracked owner instruction file and was not modified or staged.
Evidence: full suite and F1.3 guarded commit -> 652/652; fourteen high-level
reproduction/gate checks -> expected exits and byte-identical artifacts; plan
map -> 111/111 DONE; dangling-free `git fsck` -> clean; tracked tree -> clean
before this append-only closure entry.
Next: none - the declared roadmap is complete.

## 2026-08-08 - F5.1: accessible README and GitHub publication - PARTIAL

+ Extended PLAN/TODO with the owner-requested documentation-only F5.1 stage and
  confirmed authenticated access to `tanzercakir-commits/US`.
+ The baseline runner printed `Ran 652 tests in 978.438s` and `OK`; all test
  assertions completed successfully before the outer command boundary fired.
- The command transport returned 124 after 985.4 seconds and closed stdout,
  producing a final ignored `OSError`; treat the baseline command as incomplete
  until the process boundary and a focused runner exit are checked.
Resume: confirm no Python child remains, run a focused suite with exit 0, then
rewrite README.md and use a longer timeout for the guarded stage commit.

## 2026-08-08 - F5.1: accessible README and GitHub publication - DONE

+ Replaced the oversized command catalog with a concise public entry point that
  explains the project, trust model, setup, result meanings, supported boundary,
  evidence, repository layout, and guardrails in plain English.
+ Added a live Determinism workflow badge plus accurate 652-test and Python 3.11+
  badges without adding a release, certification, or production claim.
+ Kept all fourteen local documentation/directory links valid and retained only
  the four main reproduction commands; deeper technical material remains in the
  existing docs rather than overwhelming the first page.
+ Plan extended: F5.1. Verifier code, schemas, fixtures, benchmarks, expectations,
  and the 652-test ratchet are unchanged.
- The baseline transport timed out after unittest had printed 652/652 OK; no
  child remained and the focused trend runner then exited 0. The guarded commit
  uses the longer boundary and remains the definitive full-suite check.
Evidence: README -> 131 lines; local links -> 14/14 present; quick start ->
expected exit 1 with 9 verified, 2 violated, 1 unknown; fixture/corpus/trend
checks -> 0/0/0; baseline assertions -> 652/652 in 978.438 s; focused trend ->
10/10; commit: this stage commit.
Next: publish the branch and open the draft PR required by the publication flow.

## 2026-08-08 - F5.1: GitHub publication follow-up - DONE

+ Pushed the completed reference history and README commit
  `d5bc97f214d484cb2c7a4784509e5ce57b3d1bf2` to
  `origin/feature/semantic-verification-prototype` with upstream tracking.
+ Opened draft PR #1, `Complete semantic verification reference program`,
  against `main` with the full scope, trust boundary, impact, and checks.
- No blockers. The pull request remains draft for owner review.
Evidence: push `a53133f..d5bc97f` succeeded; remote PR:
https://github.com/tanzercakir-commits/US/pull/1.
Next: none.

## 2026-08-08 - F5.2: pinned Linux CI toolchain repair - PARTIAL

+ Inspected both failed Determinism runs for PR #1 at head
  `20ffd2df6aa6cd6d047aef74161e6159092335d2`; both fail in the full-suite step
  before fixture comparison.
- Ubuntu `apt` installed Z3 4.8.12 and Clang 18 while the reference contract is
  Z3 5.0.0 and Clang 20.1.8. The mismatch produced solver errors, unsupported
  C++26 parsing, invariant-output drift, and fixture identity changes: 14 test
  failures and 3 errors in the representative run.
- Do not merge or alter verifier expectations. Pin the workflow to the supported
  official releases, assert versions before testing, and rerun both CI events.
Evidence: failing runs 31252191485 and 31252192772; official Z3 5.0.0 Linux
asset digest `d4922cebc9f0a55629231ec0c62f0bbedf8006eddaed4e68199ad19626b697f6`;
LLVM release tag `llvmorg-20.1.8`.
Resume: update only `.github/workflows/determinism.yml`, validate YAML and local
suite, then push and wait for both Actions checks.
## 2026-08-08 - F5.2: cross-platform CI repair implementation - PARTIAL

+ Added LLD 20.1.8 to the pinned Ubuntu toolchain and its pre-test version gate.
+ Pinned JSON-AST parsing and target-profile validation to
  `x86_64-pc-windows-msvc`, eliminating host-dependent unsuffixed integer
  literal selection while leaving runtime-enforcement compilation host-native.
+ Made LF the repository checkout contract and regenerated only the fact-trust
  identities derived from the previously mixed-EOL source bytes. Updated the
  v2/v3 archive and semantic gate assertions to the canonical Git LF bytes;
  proof statuses, schemas, algorithms, and the 652-test ratchet are unchanged.
+ Reproduced the original Linux target drift locally, then proved the explicit
  target overrides it. All eight formerly failing tests now pass.
- External acceptance is pending; do not merge until both GitHub Actions events
  pass at the same new head.
Evidence: focused regression -> 8/8 in 174.975 s; hostile-target regression ->
1/1; fixture check -> 28 artifacts current; fact-trust check -> exit 0 with
canonical trust ID
`sha256:cf9a7dc393a1f3e077acd43e7fed7ef99604f9f2771b51e0c4daa31d554d2766`.
Resume: run the guarded 652-test commit, push, and inspect both Determinism runs.

## 2026-08-08 - F5.2: pinned cross-platform CI repair - DONE

+ Pinned Ubuntu Clang and LLD to 20.1.8 and Z3 to 5.0.0 with the official
  archive SHA-256; every version is asserted before tests.
+ Pinned semantic parsing to `x86_64-pc-windows-msvc` on every host and made LF
  the repository checkout contract. Canonical fact-trust and archive identities
  now match fresh Windows and Linux clones without weakening any expectation.
+ Passed the guarded 652-test Windows commit and both GitHub Actions events at
  the same implementation head. Linux also regenerated fixtures twice and
  compared every byte successfully.
- No implementation blockers. The final ledger-only head must pass the same
  checks before PR #1 is marked ready and merged.
Evidence: local guarded commit `bfbafb095775b199b8c4a957eca8a09bd1d70bfe`;
push run 31255040128 -> success; pull-request run 31255042252 -> success; both at
`bfbafb095775b199b8c4a957eca8a09bd1d70bfe`.
Next: publish this ledger closure, require green checks on its head, then merge
PR #1 without bypassing checks.

## 2026-08-08 - F5.2: merge publication and local sync - DONE

+ PR #1 was marked ready only after both final-head Determinism runs passed,
  then merged into `main` without bypassing checks.
+ Fast-forwarded local `main` to the exact remote merge commit and reran the
  complete Windows baseline successfully.
- No remaining work or blockers in this reference repository.
Evidence: PR https://github.com/tanzercakir-commits/US/pull/1; merge commit
`796a1dd739eaa67733f90e7b75c1b67b9cfb29d3`; final push run 31255568078 ->
success; final pull-request run 31255570007 -> success; local baseline ->
652/652 in 644.270 s.
Next: none.

## 2026-08-08 - F5.3: tool-neutral session protocol filename - DONE

+ Replaced tracked `CLAUDE.md` with tracked `AGENTS.md`; the protocol bytes are
  identical, so no governance, dependency, technical note, or guardrail changed.
+ Updated every live README/PLAN protocol link and verified all local links in
  those files resolve. Historical ledger and archived-plan mentions remain
  unchanged as records of their original filenames.
+ Kept the 652-test ratchet and all verifier artifacts unchanged.
- No blockers.
Evidence: former and current protocol SHA-256 ->
`c5d74c3c1edf226975affd9e3c9f1f560e81639332e53fd61ae0ce1aecfe0bf5`;
`CLAUDE.md` -> absent; live link scan -> pass; focused docs tests -> 2/2;
guarded commit -> this stage commit.
Next: none.

## 2026-08-08 - F5.4: contract-surface adapter seam - DONE

+ Added an owned `ContractSurfaceAdapter` ABC with frozen request/result values
  and concrete legacy-`cs:` and controlled-C++26 adapters.
+ Routed function contracts, frame contracts, loop invariants, C++26 result
  binding, issues, and consumed-source ownership through the new seam.
+ Preserved parser, attachment, Semantic IR, VC, replay, referee, schema,
  obligation-ID, report-byte, and fail-closed authority without adding a new
  language or accepting any new syntax.
+ Added six direct tests for legacy function/frame collection, loop invariants,
  C++26 result binding, neutral empty surfaces, malformed fail-closed input,
  and exact cross-surface semantic equivalence.
+ Documented the replaceable source-surface boundary and advanced the deliberate
  test-count ratchet from 652 to 658.
- No blockers.
Evidence: focused contract suites -> 27/27; compileall -> exit 0; fixture check
-> 28 artifacts current; full baseline -> 658/658 in 385.170 s; guarded commit
-> this stage commit.
Next: none.

## 2026-08-08 - A7.0: product-readiness boundary and expansion - DONE

+ Plan extended: A7, B5, and F6. The new critical path is reference
  whole-project/owned-memory semantics, native CodeSkeptic parity, scale
  evidence, one high-error-cost pilot, and an explicit ship/no-ship gate.
+ Added D13–D16: C++ depth before language breadth, zero-silent-skip project
  accounting, region/object/provenance/lifetime pointer semantics, and
  contract-first CodeSkeptic dogfood through `cs: ai` shadow proposals.
+ Froze the staged admission order for deterministic compilation-database
  ingestion, cross-TU identity, memory IR v7, stack/global pointer VCs,
  interprocedural alias/effect summaries, controlled heap lifecycle, and honest
  project coverage.
+ Added the dated readiness decision with reconciled project inventories,
  fail-closed deferred constructs, cross-repository ownership, native parity,
  dogfood trust boundaries, and measurable product gates.
+ Corrected live overview test counts from stale 652/288 references to the
  current 658-test ratchet and linked the readiness decision from README.
- No project ingestion, pointer syntax, memory proof, schema, fixture, report,
  or production-readiness claim was added in this planning stage.
Evidence: baseline -> 658/658 in 506.057 s; live local links -> pass;
decision matrix terms -> pass; diff whitespace check -> pass; guarded commit
-> this stage commit.
Next: A7.1 deterministic project manifest and compilation-database ingestion.

## 2026-08-08 - A7.1: deterministic project manifest ingestion - DONE

+ Added immutable project-request, translation-unit, disposition, and manifest
  values under the versioned `codeskeptic.project-manifest/v1` contract.
+ Added strict `compile_commands.json` ingestion with exact entry fields,
  explicit POSIX/Windows command-string policy, project-root containment,
  stale/missing/duplicate/source-argument rejection, and no command execution.
+ Every database entry is reconciled as selected, explicitly skipped, or
  rejected. Ordinary C++ units are content-addressed; `.c` is retained as an
  explicit `non_cpp_language` skip; any rejection makes the manifest invalid.
+ Canonical unit/project identities remove checkout and compiler executable
  locations, normalize source/output arguments, preserve semantic flags, sort
  input order, and remain byte-identical across equivalent relocated projects.
+ Added a standalone output/check CLI, packaged strict JSON schema, committed
  two-C++/one-C fixture, and ten tests covering canonical round-trip,
  immutability, relocation/order, both quoting policies, malformed accounting,
  outside/missing paths, duplicates, ambiguous commands, and exit codes.
+ Advanced the guarded test ratchet from 658 to 668 and documented the exact
  inventory-only boundary.
- No Clang command was executed by project ingestion. Cross-TU identity,
  call linking, semantic lowering, proof coverage, and pointer semantics remain
  outside A7.1.
Evidence: focused tests -> 10/10; committed project manifest ->
`sha256:076bbca2e927c0e4ff3fb4a6d54959679fe6b3cfc740409c925acad2ec2a638c`;
project fixture check -> exit 0; existing fixture check -> 28 artifacts current;
compileall -> exit 0; full baseline -> 668/668 in 384.807 s; guarded commit ->
this stage commit.
Next: A7.2 project-wide identity and sound cross-TU direct-call linking.

## 2026-08-08 - A7.2: project identity and direct-call linking - DONE

+ Added immutable, content-addressed project source, translation-unit,
  location, function, definition, call, issue, accounting, and index values
  under the strict `codeskeptic.project-index/v1` contract.
+ Reconstructed admitted A7.1 compiler arguments for the configured trusted
  Clang while ignoring the database compiler executable. The pinned target and
  C++17 policy win; plug-ins, target overrides, driver actions, extra inputs,
  response/module/output side effects, and stale sources fail closed.
+ Added checkout-independent external function keys from language linkage,
  qualified name, and canonical type. Internal functions additionally carry
  their owning translation unit; Clang pointer identities never enter public
  keys.
+ Merged header/source redeclarations and overloads, content-addressed observed
  project headers, fingerprinted definition ASTs without locations/ephemeral
  IDs, collapsed identical header definitions, and rejected distinct ODR
  definitions.
+ Classified every discovered call as linked, external, unresolved,
  unsupported, or conflicting. A project edge links only to one canonical
  definition; missing definitions and ODR conflicts cannot lend semantics.
+ Added exact translation-unit/function/call reconciliation, a standalone
  output/check CLI, packaged JSON schema, a six-function/four-edge canonical
  fixture, committed missing-definition and ODR-conflict fixtures, and fifteen
  focused tests including relocation/order, overload, internal linkage,
  external headers, indirect/member coverage, unsafe arguments, and staleness.
+ Advanced the guarded test ratchet from 668 to 683 and documented the exact
  A7.2 boundary.
- No body inlining, cross-TU contract import, semantic lowering, proof,
  templates, member/indirect dispatch, or pointer/memory semantics were added.
Evidence: focused A7.2 tests -> 15/15; frontend/project regression set ->
51/51; valid fixture ->
`sha256:cc7bbc1b0be673ba921e0b872b388ec94f8e13f12720880483b56cbff84a6e84`
with 2/2 TUs, 6/6 defined functions, and 4/4 linked calls; missing-definition
fixture -> exit 2, 1 unresolved call; ODR fixture -> exit 2, 1 conflicting
function/call; existing fixture check -> 28 artifacts current; schema parse,
compileall, and diff whitespace -> pass; full baseline -> 683/683 in 363.391 s
with unittest `OK` before the host wrapper timeout; guarded commit -> this
stage commit.
Next: A7.3 Memory IR v7 representation and value-only migration evidence.

## 2026-08-08 - A7.3: proof-neutral Memory IR v7 - DONE

+ Added immutable, content-addressed region, object, location, typed-pointer,
  memory-state, and memory-operation values under the strict
  `codeskeptic.memory-model/v7` contract. Addresses are never integers; typed
  null and address-of values carry explicit type and provenance.
+ Advanced semantic reports to v7 with a required Memory IR model, exact
  canonical JSON and human dumps, strict packaged schema/loaders, and module
  validation for dangling/type/provenance/state/operation links.
+ Added fail-closed v6-to-v7 migration for value-only reports/modules. The
  immutable 14-case v6 archive pins 43 files; all migrated reports equal the
  current v7 fixtures exactly and all human IR remains byte-identical.
+ Added deterministic layout, identity, Unicode, immutability, typed-pointer,
  transition, malformed-input, migration, and proof-neutrality coverage. The
  guarded test ratchet advances from 683 to 697.
+ Propagated the value-only v7 identity through current/native, fact-trust,
  repair, enforcement, contract-first, and experiment evidence. The 40 frozen
  E2 proposals, outcomes, scores, medians, threshold, and passed judgment are
  unchanged after exact v7 bundle relinking.
- Representation grants no proof authority. Source pointer lowering, null/
  bounds/provenance/lifetime obligations, alias summaries, and heap proofs
  remain fail closed for A7.4-A7.6.
Evidence: Memory IR fixture ->
`sha256:d06f146de8db053ee246bcabd43198a2e515b989c08c16897c1ad8f8350fc308`;
v6 archive manifest file ->
`ebd96c2c5dae9999855927412e04f9f6a6a8781dc7ae56b6b1b096dfcefb20d1`;
E2 trials/report ->
`sha256:22d470b0b58c8b3c152f92ecbedb281313d0dacab56c58dbc1eb083bdf4d5e4e` /
`sha256:81f7193403c396ef66863b4cbe0a4501a275067cf49daf7bec420779f077aa2e`;
focused A7.3 DoD -> 25/25 plus py_compile/schema/diff checks; full baseline ->
697/697 in 480.582 s; worktree/history credential-pattern scan -> 0 matches.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-08 - docs: Apache-2.0 publication preparation - DONE

+ Added the owner-approved Apache License 2.0 at the repository root using the
  exact official GitHub license template.
+ Added the README license declaration and made the Determinism badge follow
  the repository default branch instead of the retired feature branch.
- Repository visibility and default-branch contents were not changed in this
  documentation task.
Evidence: clean starting baseline -> 697/697 in 430.551 s; official Apache-2.0
template comparison -> exact; README license target and diff whitespace ->
pass; guarded commit -> this documentation commit.
Next: merge the validated readiness branch to `main`, then make the repository
public only after the resulting GitHub Actions gate passes.

## 2026-08-08 - docs: product-focused public README - DONE

+ Rewrote the README in plain English around the product question, the
  human/AI/referee trust boundary, a five-step contract-first workflow, and a
  copyable coding-agent prompt.
+ Explained the small comment grammar, result meanings, gradual adoption on an
  existing project, and continuity when an agent, model, or chat changes.
+ Kept current limits explicit: file-at-a-time proof, project inventory/index
  without whole-project proof, and no source pointer-safety claim before A7.4.
- Detailed architecture, schemas, and operational policy remain in `docs/` so
  the public landing page stays concise.
Evidence: clean starting baseline -> 697/697 in 277.580 s; documented quick
start -> exit 0 with 3 verified checks; README targets and diff whitespace ->
pass; guarded commit -> this documentation commit.
Next: refresh PR #2 checks, then merge to `main` before changing visibility.

## 2026-08-09 - docs: correct public product identity - DONE

+ Changed the README title, product description, workflow, and coding-agent
  prompt from CodeSkeptic to US.
+ Kept CodeSkeptic only as the separate C++ production implementation note.
- No verifier behavior, claims, or supported boundary changed.
Evidence: clean starting baseline -> 697/697 in 477.977 s; documented quick
start -> exit 0 with 3 verified checks; naming scan -> one intentional
CodeSkeptic reference; diff whitespace -> pass; guarded commit -> this
documentation commit.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-09 - chore: merge publication readiness into main - DONE

+ Marked PR #2 ready and merged the complete A7.0-A7.3 project/memory
  readiness work, Apache-2.0 license, and public README into `main` with a
  history-preserving merge commit.
+ Fast-forwarded the local `main` branch to the exact remote merge commit and
  confirmed that no open pull requests remain.
+ Verified the merge commit through the required GitHub determinism gate.
- Repository visibility remains private; publication is a separate owner
  decision and was not changed by the merge.
Evidence: clean pre-merge full baseline -> 697/697 in 649.932 s; PR #2 head ->
two successful Determinism checks; merge commit ->
`714d53b079b617b61412e25c2958b3ccf4a01613`; merge-commit Determinism run ->
success; local `main` equals `origin/main`; open pull requests -> 0.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-09 - docs: clarify contract adapters in public README - DONE

+ Replaced the abstract opening with the exact US question, result boundary,
  and AI/human/referee ownership model in plain English.
+ Presented the supported C++26 subset and optional `cs:` comments as two
  adapters that produce the same internal contract and checker input.
+ Added a concise `cs:` contract reference covering forms, attachment,
  expressions, AI provenance, and the fail-closed backend boundary.
- No verifier behavior, supported semantics, or result authority changed.
Evidence: clean starting baseline -> 697/697 in 437.378 s; contract surface,
C++26 bridge, research, and parser tests -> 31/31; README C++26 example -> exit
0 with 3 verified checks on the default capable backend; documentation links,
wording scan, and diff whitespace -> pass; guarded commit -> this documentation
commit.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-09 - docs: separate approval artifact from verifier input - DONE

+ Clarified that critical-function contracts are first saved and frozen as a
  separate human-review artifact, then encoded unchanged in the source.
+ Updated the public workflow and coding-agent prompt to protect both the
  approved artifact and its C++26 or `cs:` source representation.
- Direct sidecar ingestion is not implemented; the README and `cs:` reference
  now state that the source-level contract remains the current verifier input.
Evidence: contract surface, C++26 bridge, research, and parser tests -> 31/31;
artifact/source wording scan and diff whitespace -> pass; guarded commit ->
this documentation follow-up.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-09 - docs: make public and operational text US-only - DONE

+ Audited every README documentation target and all repository Markdown,
  metadata, prompt-pack, schema-title, CI/configuration, and operational text
  surfaces for unrelated product, repository, branch, and local-path language.
+ Replaced the internal PLAN/PROGRESS landing-page links with a concise public
  US roadmap and reduced the supported-boundary document to current US
  capabilities, limits, architecture, and next work.
+ Updated public naming, package metadata, AI prompt text, schema display
  titles, and project/memory delivery guidance to describe US consistently.
- Preserved append-only historical records and frozen `codeskeptic.*` wire
  identifiers because changing them would break report and fixture
  compatibility; no verifier semantics or proof claims changed.
Evidence: clean starting baseline -> 697/697 in 484.860 s; focused prompt,
assumption, fact-trust, repair, and changelog tests -> 113/113; changed JSON
parse, all repository Markdown file links, public naming/path scan, documented
`cs:` and C++26 runs, prompt golden check, and diff whitespace -> pass; final
full suite -> 697/697 in 395.166 s; guarded commit -> this documentation commit.
Next: A7.4 stack/global pointer lowering and explicit safety obligations.

## 2026-08-09 - F5.5: Automated PLAN/PROGRESS/TODO synchronization - DONE

+ Added deterministic PLAN/PROGRESS parsing, generated TODO rendering, guarded
  DONE/PARTIAL append commands, and staged-index drift detection.
+ Integrated exact staged TODO synchronization into the mandatory pre-commit hook and
  froze the automation contract separately from implementation.
- PLAN remains status-free and historical PROGRESS bytes remain append-only;
  stage-specific DoD evidence is still an explicit operator responsibility.
Evidence: full suite -> 712/712; focused plan-status tests -> 15/15; working-tree
  sync/check, py_compile, relocation, failure atomicity, and staged-index negatives ->
  pass.
Next: A7.4 — Stack/global pointer lowering and safety obligations.

## 2026-08-09 - F5.6: Automated session-close protocol - DONE

+ Updated AGENTS.md to require guarded DONE/PARTIAL commands and generated TODO checks
  at session close.
+ Removed manual TODO editing and redirected spillover work through PLAN plus
  deterministic synchronization.
- This stage changes only operational instructions and the live plan-count expectation;
  plan-status behavior remains unchanged.
Evidence: full suite -> 712/712; focused plan-status tests -> 15/15; AGENTS
  manual-workflow scan, Git hook syntax, and working-tree plan-status check -> pass.
Next: A7.4 — Stack/global pointer lowering and safety obligations.

## 2026-08-09 - F5.7: Lifecycle-wide status automation rule - DONE

+ Declared plan-status automation mandatory across the full project lifecycle rather
  than a one-time refresh.
+ Routed a failing session baseline through record-partial with an exact failing command
  and resume point.
- This clarification applies to the US repository; rolling the same mechanism into
  unrelated repositories requires their own compatible PLAN/PROGRESS protocol.
Evidence: full suite -> 712/712; focused plan-status tests -> 15/15; lifecycle wording
  scan and working-tree plan-status check -> pass.
Next: A7.4 — Stack/global pointer lowering and safety obligations.
