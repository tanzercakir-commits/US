# SEMANTIC VERIFICATION PROGRAM — MASTER PLAN

> Vision: the AI proposes, a deterministic referee decides. Lower C++ into
> provable semantic facts, produce machine-readable counterexamples, and make
> AI mistakes detectable. "Consciousness is the system that can see its own
> errors."

This file is the project's **single roadmap**. It carries NO status — the only
source of truth for "done" is [PROGRESS.md](PROGRESS.md); the current work item
lives in [TODO.md](TODO.md). Session protocol: [CLAUDE.md](CLAUDE.md).

---

## 0. How to use this plan

### 0.1 File roles

| File | Role | Change rule |
|---|---|---|
| PLAN.md | Hierarchical roadmap (program → phase → stage) | Rarely; extend/cancel only. Never carries status. |
| PROGRESS.md | Append-only ledger: finished stages + evidence | Entries are APPENDED every session, never deleted. |
| TODO.md | Active set (≤7 items): now + next + blockers | Updated at the end of every session. |
| CLAUDE.md | Session protocol (auto-loaded) | Rarely. |

### 0.2 Resume protocol — when the model/session drops

1. Read [TODO.md](TODO.md) → learn the active stage.
2. Read the last ~20 lines of [PROGRESS.md](PROGRESS.md) → what finished last,
   any `PARTIAL` entry.
3. Read only the active stage's phase in PLAN.md (not the whole file).
4. Verify the baseline: `python -m unittest discover -s tests`
5. Work against the stage's DoD. If you cannot finish, write a `PARTIAL`
   entry to PROGRESS (exact file/command to resume from).

### 0.3 Session ritual

- **Start:** steps in 0.2. If tests are red, log that to PROGRESS first.
- **During:** ONE stage at a time. If work would spill outside the stage's
  `Output` file set, STOP and add a scope note to TODO.
- **End:** (1) run the DoD commands, record results; (2) append a PROGRESS
  entry; (3) update TODO (remove done, pull next from plan); (4) commit with
  the stage ID in the message (`A1.2: z3 runner`); (5) for work >30 min, add
  interim PROGRESS notes against interruption risk.

### 0.4 Numbering and growth

- Identity: `<Program><Phase>.<Stage>` → e.g. `A1.3`. **IDs are never reused
  or renumbered.** A cancelled stage is kept and marked `[CANCELLED: reason]`.
- **Rolling wave:** only the active phase and the next one are detailed to
  stage level (Goal/Output/DoD). Distant phases stay at heading level and are
  expanded by an `Fx.0 Expansion` stage when their turn approaches. Numbering
  supports growth toward a 100–1000 stage horizon.

### 0.5 Guardrails (enforced, not advisory)

Git hooks under `.githooks/` (activate once per clone:
`git config core.hooksPath .githooks`):

- **pre-commit** runs the full test suite; blocks on failure.
- **Test-count ratchet:** the suite size must equal
  `guardrails/test_baseline.txt`; fewer blocks (constitution #8), more
  requires bumping the staged baseline — growth is deliberate, never silent.
- **Ledger enforcement:** staged code changes (`semantic_verifier/`, `tests/`,
  `tools/`, `examples/`) without a staged PROGRESS.md are rejected.
- **commit-msg** requires a stage ID (`A1.2: ...`) or an allowed prefix
  (`plan|docs|chore|fix|test|wip`).

Do not bypass hooks (`--no-verify`) without explicit owner approval.

---

## 1. Problem model (why this plan)

Failure layers of AI-assisted development with estimated weights (calibrated
judgment from the discussion sessions, not measurements):

| Layer | Weight | Symptom | Answer in this plan |
|---|---|---|---|
| 1. Context / world model | ~35% | lost in the forest | Program D (fact index, SCI) |
| 2. Grounding / verification | ~25% | over-assuming, plausible-but-wrong code | Programs A + B (the referee) |
| 3. Goal management | ~15% | goal drift | Program F + this plan system itself |
| 4. Intent specification | ~15% | unstated requirements | Program C (contract-first) |
| 5. Raw capability | ~10% | genuinely hard work | Program E (referee-guided search; long-term RLVF) |

Core insights (from the source document + discussions):

- An annotation without enforcement is hope; with enforcement it is knowledge.
- Compilers already prove facts and throw the proofs away; SCI keeps them and
  serves them to the AI.
- AI's typical error is not "crash" but "plausible-wrong"; only intent-bearing
  contracts catch it.
- The referee is also a clean-training-data factory (AlphaZero analogy).

## 2. Decision log

Decisions are not re-litigated; changing one requires a new entry.

- **D1 — Take over:** the Codex prototype (commit `4326583`) is adopted, not
  rewritten. Rationale: it passed an independent audit (64/64 tests;
  fail-closed behavior confirmed adversarially; sound result taxonomy).
- **D2 — Two languages, one schema:** Python = lab/reference implementation;
  C++17 (CodeSkeptic) = production. Bridge: the
  `codeskeptic.semantic-verification` JSON schemas + fixtures. No third
  language.
- **D3 — OOP discipline:** abstract interfaces at swappable seams
  (`CheckerBackend`, `Frontend`); frozen (immutable) value objects for IR and
  results; composition over inheritance. Rationale: a type signature is a
  declared assumption; class boundaries narrow the AI's guessing space.
- **D4 — No solver linking:** SMT integration is subprocess + SMT-LIB2 text
  (same pattern as the Clang bridge). Z3 primary; schema stays
  solver-agnostic.
- **D5 — Status separation:** PLAN static; PROGRESS append-only single source
  of "done"; TODO small active set.
- **D6 — Permanent IDs:** stage IDs are never renumbered.
- **D7 — Rolling wave:** distant phases are deliberately coarse; detail comes
  when their turn approaches.
- **D8 — The referee is never an AI:** AI proposes (contracts, patches,
  invariants); only the deterministic tool judges. No exceptions.
- **D9 — Number model:** v0 keeps mathematical integers + 32-bit safety
  obligations. The bitvector (QF_BV) question reopens at A6.1 when
  `unsigned`/bit operations arrive.
- **D10 — Language policy:** all repository artifacts (plan, progress, todo,
  docs, code, diagnostics, commit messages) are in English. Conversation with
  the project owner is in Turkish. Working narrative stays minimal; the owner
  reads the final report and the +/- notes.
- **D11 — Note convention:** in PROGRESS/TODO notes, positives are marked `+`,
  negatives/blockers `-`, for fast remote scanning.
- **D12 — Native production referee:** CodeSkeptic ports VC generation,
  deterministic SMT-LIB emission, solver orchestration, model replay, and
  result routing to C++17. Python remains the lab/reference oracle, not a
  production helper dependency. Z3 remains an unlinked subprocess per D4.

## 3. Constitution (invariants for every stage)

1. `unknown`/`unsupported` is never promoted to `verified`.
2. Unsupported constructs are never silently approximated — explicit
   `unsupported` (fail-closed).
3. Every counterexample is replayed against the original obligation; a model
   that does not replay is reported as `solver_error`, never shown as a
   counterexample.
4. Referee output is deterministic: no wall clock, no randomness, no unordered
   iteration on the logic path; all serialization sorted.
5. AI proposes, the referee decides (D8).
6. Every stage's DoD contains runnable commands; "looks done" is invalid.
7. Schema changes are versioned (v0 → v1); old fixtures are kept.
8. The test count never decreases; soundness tests
   (`tests/test_checker_soundness.py`, `tests/test_frontend_soundness.py`)
   are never weakened. Enforced by the ratchet (§0.5).
9. Final signature on contracts is human (the spec-correctness problem);
   `cs: ai` proposals are not accepted intent until a human removes the `ai`
   marker.
10. Scope guard: work spilling outside the stage's declared file set = STOP +
    TODO note (the goal-drift brake).

## 4. Program map

| Program | Name | Layer | Origin in prior discussion |
|---|---|---|---|
| A | Referee (core verifier) | 2 | M1, M2, M3 + 2a |
| B | Production (CodeSkeptic integration) | 2 | M4, M6a + sidecars |
| C | Intent (contract-first, syntax bridges) | 4 | 4a, 4b, C++26 |
| D | World model (fact index / SCI) | 1 | 1a, 1b, 1c, 1d |
| E | AI loop (repair, experiment, search) | 2+5 | M5, 2d, 5a, the "consciousness experiment" |
| F | Process & infrastructure | 3 | 3a–3d, M6b, this plan system |

**Critical path:** A1 → A2 → A3 → E1 → E2. B1, D1, F1 can run in parallel.
C1 is light; anytime after A1.

---

## 5. PROGRAM A — Referee

Goal: raise the lab verifier to "feels real" strength: dry up the unknowns,
support calls and loops, make counterexample quality AI-loop ready.

### Phase A1 — Z3 backend (formerly M1)

Target: `examples/vertical_slice.cpp` → `unknown=0`. The affine checker stays
(cross-check + dependency-free mode).

#### A1.1 — SMT-LIB2 emitter
- Goal: `Obligation` → QF_LIA SMT-LIB2 text; validity = assert negated
  conclusion + `(check-sat)`, satisfiability = direct; deterministic output
  (sorted symbols, reversible name mapping `y#0` → `y_v0`).
- Output: `semantic_verifier/smtlib.py`, `tests/test_smtlib.py`
- DoD: `python -m unittest tests.test_smtlib` green; same obligation emitted
  twice → byte-identical (repeat test).
- Depends: none.

#### A1.2 — Z3 process runner
- Goal: `discover_z3` (env `SEMANTIC_VERIFIER_Z3`, PATH, known locations —
  same pattern as clang discovery); timeout parameter; mapping
  `sat/unsat/unknown/timeout/crash` → result taxonomy (timeout → `unknown`,
  crash → `solver_error`); fixed determinism options (`smt.random_seed` etc.).
- Output: `semantic_verifier/z3_backend.py`, `tests/test_z3_backend.py`
- DoD: tests green on a machine with Z3; without Z3, graceful degradation:
  configuration failure reported as `solver_error`, rest of pipeline alive
  (symmetric to the missing-frontend pattern).
- Depends: A1.1.

#### A1.3 — Model parser + replay
- Goal: parse `(get-model)` into counterexample bindings; per constitution #3
  replay every model through the existing `evaluate()` against the original
  obligation; mismatch → `solver_error` (no blind trust in Z3).
- Output: `z3_backend.py` extension + tests
- DoD: injected corrupt model yields `solver_error` in test; real violations
  return bindings.
- Depends: A1.2.

#### A1.4 — CheckerBackend interface and selection (implements D3)
- Goal: `CheckerBackend` ABC (`check(Obligation) -> VerificationResult`);
  adapt `AffineChecker` and `Z3Checker`; CLI `--backend=affine|z3|both`;
  `both` = cross-check mode (definitive disagreement → `solver_error` +
  report — a soundness alarm).
- Output: `semantic_verifier/backend.py`, adaptations in `checker.py`/`cli.py`
- DoD: all existing tests green under both backends; `both` mode on
  `vertical_slice.cpp` shows no disagreement.
- Depends: A1.3.

#### A1.5 — Solver decision document
- Goal: the record the Codex doc required: Z3 license (MIT), platform
  packaging (Win/Linux/mac install paths), timeout policy, determinism
  options, unknown handling, model serialization.
- Output: `docs/solver_decision.md`
- DoD: document exists; linked from README.
- Depends: A1.2.

#### A1.6 — Phase gate: golden tests
- Goal: `transitive_chain` now `verified`; suite growth (target ≥85 tests);
  determinism repeat tests including Z3.
- DoD: `python -m semantic_verifier examples/vertical_slice.cpp --format text`
  → `unknown=0, solver_error=0`; suite green; PROGRESS entry with numbers.
- Depends: A1.1–A1.5.

### Phase A2 — Call return values and modular verification (M2)

#### A2.1 — IR: call-with-result node
- Goal: `target := call(f, args)` node; lowering for calls in init/assign
  position (controlled relaxation of today's "calls nested inside
  expressions" rejection: ONLY `int q = f(x);` and `q = f(x);` forms).
- Output: `lowering.py`, `model.py` extension + tests
- DoD: new forms lower; other nested calls still `unsupported` (fail-closed
  kept, boundary test added).

#### A2.2 — VC: havoc + assumed ensures
- Goal: call result becomes a fresh symbol (havoc); callee `ensures` added as
  assumption after parameter substitution; `requires` obligations unchanged.
- Output: `vc.py` + tests
- DoD: a two-function chain example (`withdraw`/`validate` style) verifies
  end-to-end; added under `examples/`.

#### A2.3 — Recursion policy
- Goal: detect direct/mutual recursion in the call graph → `unsupported` (for
  now; a variant/decreasing-measure design is a separate future decision).
- DoD: recursive example rejected with explicit reason.

#### A2.4 — Phase gate
- DoD: multi-function example file: chain `verified`; deliberately violated
  variant `violated` with counterexample; suite green.

### Phase A3 — Loops + invariants (M3)

#### A3.1 — `cs: invariant` syntax (contracts.py; block bound to a `while` only)
#### A3.2 — `while` lowering: invariant node + havoc of loop-modified variables
#### A3.3 — VC triple: (i) invariant holds on entry, (ii) inductive
  preservation, (iii) exit knowledge `I ∧ ¬cond`; missing invariant →
  `unsupported` (never guessed)
#### A3.4 — Termination: explicit NON-GOAL record (variant later, separate phase)
#### A3.5 — Phase gate: sum-loop example (`sum 0..n`) `verified`; same example
  without invariant `unsupported`; deliberately wrong invariant `violated`
  with counterexample

### Phase A4 — Counterexample quality (AI-loop prerequisite)

#### A4.1 — Model minimization: shrink variable count while preserving the
  violation (greedy elimination; deterministic order)
#### A4.2 — Relevance projection: report only variables in the obligation's
  cone (ends the irrelevant `x=-2147483648` noise next to `input=0`)
#### A4.3 — Trace explanation: path assumptions → source line mapping
  ("when this branch is taken"), machine-readable field + human-readable text

### Phase A5 — Scaling

Phase constraint: scaling is an optimization layer, never a new referee. It may
reuse or skip work only under explicit semantic keys and budgets. Cache misses,
corruption, inconclusive subsumption, timeout, and budget exhaustion never
produce `verified`.

#### A5.0 — Expansion stage (rolling wave)
- Goal: replace the coarse A5 headings with bounded stages, declared file sets,
  soundness constraints, runnable DoD commands, and a phase gate.
- Output: `PLAN.md`, `TODO.md`, `PROGRESS.md` only.
- DoD: A5.1–A5.4 each declare Goal/Output/DoD/Depends; local links remain valid;
  `python -m unittest discover -s tests` is green.
- Depends: A4.3.

#### A5.1 — Path-growth measurement and merge-point VC decision spike
- Goal: measure obligation/path growth on deterministic synthetic diamonds;
  distinguish exact duplicate elimination from unsafe logical subsumption; make
  a written implement/defer decision for merge-point VCs with a soundness
  argument. The spike must add any implementation stage required before A5.4;
  it must not approximate or silently drop paths.
- Output: `tools/path_scaling_probe.py`, `tests/test_path_scaling.py`,
  `docs/path_scaling_decision.md`; optional PLAN extension for the chosen
  implementation stage; required test-ratchet/count updates in
  `guardrails/test_baseline.txt`, `README.md`, and the prototype document. No
  production VC rewrite belongs to this spike.
- DoD: `python -m unittest tests.test_path_scaling` is green; probe runs for
  1/2/4/8 synthetic diamonds and emits byte-identical sorted JSON twice; the
  decision records measured counts, exact-key definition, rejected unsound
  shortcuts, chosen architecture, and whether a new pre-gate stage is required.
- Depends: A5.0.

#### A5.5 — Exact structured merge-point compaction (inserted by A5.1)
- Goal: replace explicit post-join path lists with an equivalent factored
  disjunction of incoming state conjunctions; eliminate only structurally exact
  duplicates/identities; retain compact guarded trace templates that resolve to
  the existing source-ordered TraceStep values after full-model replay.
- Output: `semantic_verifier/model.py`, `semantic_verifier/vc.py`,
  `semantic_verifier/checker.py`, `semantic_verifier/z3_backend.py`, backend
  trace resolution, `tests/test_path_scaling.py`, `tests/test_z3_backend.py`,
  `tests/test_determinism.py`, updates to `docs/path_scaling_decision.md` plus
  result-schema/changelog documentation, and required ratchet/count updates in
  `guardrails/test_baseline.txt`, `README.md`, and the prototype document.
- DoD: `python -m unittest tests.test_path_scaling` is green; the probe's
  post-join assertion counts for 1/2/4/8 empty diamonds become 1/1/1/1 instead
  of 2/4/16/256; nested and assignment-bearing diamond verdicts match an
  unmerged reference; true/false trace directions resolve from replayed models;
  unsupported resolution falls back or fails closed; full suite and fixture
  check are green.
- Depends: A5.1.

#### A5.2 — Persistent obligation-result cache
- Goal: compute a deterministic SHA-256 semantic key over schema, backend
  identity/configuration, obligation mode/assumptions/conclusion, and relevant
  solver policy; reuse only matching entries and reconstruct current IDs/source
  metadata. Cache I/O is an optimization outside the logic path: missing,
  malformed, stale, or unsupported entries are ignored and recomputed, never
  trusted as proof.
- Output: `semantic_verifier/cache.py`, backend/pipeline/CLI integration,
  `tests/test_cache.py`, result-schema/adoption/changelog documentation.
  Stage file set also includes `semantic_verifier/backend.py`,
  `semantic_verifier/pipeline.py`, `semantic_verifier/cli.py`,
  `semantic_verifier/z3_backend.py`, `README.md`,
  `docs/semantic_verification_prototype.md`, `PLAN.md`, `PROGRESS.md`, `TODO.md`,
  and `guardrails/test_baseline.txt` for the required integration, consumer
  surface, ledger, active-set, and test-ratchet updates.
- DoD: `python -m unittest tests.test_cache` is green; two identical runs are
  byte-identical and the second makes zero wrapped-backend calls; changing one
  obligation invalidates only its entry; schema/backend/config changes miss;
  malformed cache bytes recompute safely; full suite and fixture check are green.
- Depends: A5.5.

#### A5.3 — Deterministic resource budgets
- Goal: enforce a per-obligation solver timeout and deterministic per-file work
  budget (obligation/check units, not wall-clock proof logic). Every unstarted or
  timed-out supported obligation returns `unknown` with an explicit reason;
  existing definitive results remain intact and exit-code precedence is
  unchanged.
- Output: budget value objects plus pipeline/backend/CLI integration,
  `tests/test_budgets.py`, result-schema/adoption/changelog documentation.
  Stage file set also includes `semantic_verifier/budget.py`,
  `semantic_verifier/backend.py`, `semantic_verifier/pipeline.py`,
  `semantic_verifier/cli.py`, `semantic_verifier/z3_backend.py`, `README.md`,
  `docs/solver_decision.md`, `docs/semantic_verification_prototype.md`,
  `PLAN.md`, `PROGRESS.md`, `TODO.md`, and `guardrails/test_baseline.txt` for the
  required policy, consumer surface, ledger, active-set, and ratchet updates.
- DoD: `python -m unittest tests.test_budgets` is green; injected solver timeout
  and file-budget exhaustion deterministically yield `unknown`, never
  `verified`; repeated budgeted JSON is byte-identical; zero/unlimited boundary
  cases, cross-check behavior, full suite, and fixture check are green.
- Depends: A5.2.

#### A5.4 — Scaling phase gate
- Goal: freeze A5 operational behavior and demonstrate that scaling changes
  work performed, not proof meaning.
- Output: `examples/scaling_slice.cpp`, updated scaling decision/operations
  documentation, deterministic evidence in `PROGRESS.md`. Stage file set also
  includes `tools/scaling_phase_gate.py`, `tests/test_scaling_gate.py`,
  `docs/path_scaling_decision.md`, `docs/scaling_operations.md`, `CHANGELOG.md`,
  `README.md`, `docs/semantic_verification_prototype.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and `guardrails/test_baseline.txt` for the executable
  gate, consumer surface, ledger, active-set, and test-ratchet updates.
- DoD: uncached and warm-cache reports for the scaling slice are byte-identical;
  the warm run records zero backend calls; two budgeted runs are byte-identical;
  the path-growth probe and any A5.1 implementation benchmark meet their
  recorded target; `python -m unittest discover -s tests` and
  `python tools/regenerate_fixtures.py --check` are green.
- Depends: A5.1–A5.3 and A5.5.

### Phase A6 — Semantic extensions (far horizon; each expands when due)

Phase rule: each source family is admitted only through owned IR, exact VCs,
backend capability checks, schema/migration review, and fail-closed tests. A
backend-specific unsupported result remains unsupported in default cross-check
mode; a single capable backend is never silently substituted. Decision stages
may append implementation stages after A6.7 without renumbering existing IDs.

#### A6.0 — Expansion stage
- Goal: turn the semantic-extension horizon into ordered, independently
  reviewable stages with explicit trust, schema, backend, and unsupported
  boundaries before any parser acceptance grows.
- Output: detailed A6.1–A6.7 contracts in this plan,
  `docs/semantic_extensions_roadmap.md`, README navigation, PROGRESS/TODO.
- DoD: every stage has Goal/Output/DoD/Depends; integer, aggregate, alias,
  frame, and inference boundaries are explicit; no stage treats unsupported or
  inferred facts as proof; full suite and fixture check are green.
- Depends: A5.4.

#### A6.1 — Fixed-width integer-semantics decision point (reopens D9)
- Goal: choose and document the exact representation for int64, unsigned
  arithmetic, conversions, comparisons, bitwise operators, and shifts: QF_BV,
  mathematical integers plus safety/range obligations, or a typed hybrid.
  Preserve the current int32 claim until migration is explicit.
- Output: `docs/integer_semantics_decision.md`; operator/type/conversion truth
  tables; backend and default cross-check capability policy; schema-major and
  fixture migration impact; appended implementation stages after A6.7 with
  declared file sets and dependencies; `tests/test_integer_semantics_decision.py`.
  Stage file set also includes `PLAN.md`, `PROGRESS.md`, `TODO.md`, `README.md`,
  `docs/semantic_verification_prototype.md`, and `guardrails/test_baseline.txt`
  for decision navigation, ledger, active-set, and documentation-test ratchet.
- DoD: examples cover signed overflow, unsigned wrap, mixed signedness,
  narrowing/widening, negative/oversized shifts, and bitwise results; every
  operator maps to exact IR/SMT semantics or explicit unsupported; the affine
  boundary and Z3 logic identity are stated; selected stages are added without
  renumbering; documentation tests, full suite, and fixture check are green.
- Depends: A6.0.

#### A6.2 — Restricted arrays (QF_ARRAY)
- Goal: support a reviewed fixed-size array subset with exact select/store and
  bounds obligations. Dynamic allocation, decay to pointers, multidimensional
  arrays, aliasing, and unmodeled library operations remain unsupported.
- Output: owned array type/value/index IR; frontend/lowering/VC/SMT support;
  contract expression indexing; schema/migration updates; `tests/test_arrays.py`;
  result/adoption/prototype/changelog documentation.
- Expanded exact file set: `semantic_verifier/{array_types,model,lowering,
  contracts,vc,checker,counterexample,query_fragment,smtlib,z3_backend,backend,
  cache,schema}.py`; `tests/{test_arrays,test_integer_types,test_fixtures,
  test_integer_phase_gate,test_changelog,test_counterexample_quality,
  test_determinism,test_frontend_failures,test_unsigned}.py`;
  `examples/array_slice.cpp`; current fixture
  manifest/case/expected artifacts, immutable `fixtures/versions/v2/**`, and
  `tools/{regenerate_fixtures,integer_phase_gate}.py`;
  `docs/{result_schema,schema_versioning,adoption_guide,
  semantic_verification_prototype,solver_decision,integer_operations,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: constant and symbolic reads/writes verify; in-range facts prove access;
  feasible out-of-bounds access violates with replayed evidence; unknown bounds
  never verify; array copy/store isolation is exact; decay/alias/dynamic cases
  fail closed; deterministic JSON/SMT, schema fixtures, full suite, and fixture
  check are green.
- Depends: A6.1 and every prerequisite implementation stage it appends.

#### A6.3 — Value-type structs
- Goal: support aggregate-by-value records whose fields are already-supported
  scalar/array/value-record types, with field-sensitive SSA and copy semantics.
  Methods, inheritance, unions, bitfields, padding/layout claims, references,
  pointers, and escaping addresses remain unsupported.
- Output: record type/field IR; frontend/lowering/VC/SMT projection/update;
  contract field access; schema/migration updates; `tests/test_structs.py`;
  result/adoption/prototype/changelog documentation.
- Expanded exact file set: `semantic_verifier/{record_types,model,lowering,
  contracts,vc,checker,counterexample,query_fragment,smtlib,z3_backend,backend,
  cache,schema,dump}.py`; `tests/{test_structs,test_integer_types,test_fixtures,
  test_integer_phase_gate,test_changelog,test_counterexample_quality,
  test_determinism,test_frontend_failures,test_frontend_soundness,test_lowering,
  test_unsigned,test_arrays}.py`;
  `examples/struct_slice.cpp`; current fixture manifest/case/expected artifacts,
  immutable `fixtures/versions/v3/**`, and
  `tools/{regenerate_fixtures,integer_phase_gate}.py`;
  `docs/{result_schema,schema_versioning,adoption_guide,
  semantic_verification_prototype,solver_decision,integer_operations,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: construction, field read/write, nested value copy, branch merge, calls by
  value, contracts, and counterexamples are exact; updating one field preserves
  all others; unsupported C++ record features fail closed; serialization and
  solver output are deterministic; full suite and fixture check are green.
- Depends: A6.2 (arrays may be fields; record lvalue paths become the shared
  aggregate update mechanism).

#### A6.4 — Restricted references with proved alias discipline
- Goal: admit only reference bindings whose single target and lifetime are
  statically established and whose allowed reads/writes can be lowered to the
  same aggregate lvalue path. No general alias analysis is inferred.
- Output: reference target/lifetime IR; frontend escape and mutation checks;
  exact lowering/VC rules; explicit unsupported diagnostics;
  `tests/test_references.py`; result/adoption/prototype/changelog documentation.
- Expanded exact file set: `semantic_verifier/{model,lowering,dump,schema}.py`;
  `tests/{test_references,test_integer_types,test_fixtures,
  test_integer_phase_gate,test_changelog,test_counterexample_quality,
  test_determinism,test_frontend_failures}.py`; `examples/reference_slice.cpp`;
  current fixture manifest/case/expected artifacts, immutable
  `fixtures/versions/v4/**`, and
  `tools/{regenerate_fixtures,integer_phase_gate}.py`;
  `docs/{result_schema,schema_versioning,adoption_guide,
  semantic_verification_prototype,integer_operations,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: unique local bindings, const reads, permitted writes, aggregate-field
  targets, and branch lifetimes match direct-target behavior; multiple possible
  targets, rebinding patterns, temporary/dangling, parameter/return escape, and
  unsupported aliasing fail closed; no snapshot approximation is used; full
  suite and fixture check are green.
- Depends: A6.3.

#### A6.5 — `modifies` contracts and frame conditions
- Goal: specify and prove which caller-visible aggregate/reference locations a
  modular call may change, including the exact fact that every other reachable
  modeled location is unchanged.
- Output: strict `cs: modifies` parser/attachment; normalized lvalue-path IR;
  call summaries and frame VCs; schema fields/migration; diagnostics;
  `tests/test_frame_conditions.py`; result/adoption/prototype/changelog docs.- Expanded exact file set: `semantic_verifier/{contracts,model,lowering,vc,
  dump,schema}.py`; `tests/{test_frame_conditions,test_contracts,
  test_integer_types,test_fixtures,test_integer_phase_gate,test_changelog,
  test_counterexample_quality,test_determinism,test_frontend_failures}.py`;
  `examples/frame_conditions.cpp`; current fixture manifest/case/expected
  artifacts, immutable `fixtures/versions/v5/**`, and
  `tools/{regenerate_fixtures,integer_phase_gate}.py`;
  `docs/{result_schema,schema_versioning,adoption_guide,
  semantic_verification_prototype,integer_operations,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: empty/single/multiple/nested modifies sets work; permitted updates are
  havoced and constrained by ensures while unlisted locations retain equality;
  invalid, duplicate, inaccessible, aliased, or missing required frame specs
  fail closed; caller proofs demonstrate both change and non-change; full suite
  and fixture check are green.
- Depends: A6.4.

#### A6.6 — CHC/Spacer invariant-inference research spike
- Goal: measure whether deterministic Horn-clause candidates can reduce manual
  loop invariants without adding an inference engine to the trusted referee.
- Output: isolated CHC emitter/runner, fixed benchmark corpus, sorted candidate
  artifact schema, timeout/budget policy, decision memo, and spike tests. No
  inferred candidate enters ordinary proof assumptions directly.
- Expanded exact file set: `semantic_verifier/invariant_research.py`;
  `tools/invariant_research.py`; `tests/test_invariant_research.py`;
  `benchmarks/invariant_inference/**`; `docs/invariant_inference_decision.md`;
  `README.md`, `CHANGELOG.md`, `PLAN.md`, `PROGRESS.md`, `TODO.md`, and the test
  ratchet.
- DoD: repeated clauses/candidates are byte-identical under a pinned solver;
  useful, insufficient, timeout, unsupported, and malformed cases are recorded;
  every candidate accepted for evaluation is reattached as a proposal and
  proved by the ordinary loop entry/preservation VCs; inference failure remains
  unknown/no-candidate; full suite and fixture check are green.
- Depends: A6.5; reuses A3 loop semantics and A5 resource policy.

#### A6.7 — Semantic-extension phase gate
- Goal: freeze the combined A6 support matrix and prove that added types,
  aggregates, alias discipline, frames, and optional inference preserve the
  existing int32/report behavior and fail-closed boundary.
- Output: combined extension examples/fixtures, backend capability matrix,
  schema migration evidence, deterministic phase-gate tool, operations docs,
  and PROGRESS evidence.
- Expanded exact file set: `tools/semantic_extensions_phase_gate.py`;
  `tests/{test_semantic_extensions_gate,test_fixtures}.py`;
  `examples/semantic_extensions_gate.cpp`;
  `fixtures/{manifest.json,cases/semantic_extensions_gate.cpp,
  expected/semantic_extensions_gate.{ir,report.json}}`;
  `docs/semantic_extensions_operations.md`; `README.md`, `CHANGELOG.md`,
  `PLAN.md`, `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: all A6 feature and negative-boundary tests are green; legacy v1 fixtures
  remain archived/unchanged; current fixtures regenerate twice byte-identically;
  capable-backend results replay; default cross-check never hides unsupported;
  inferred candidates are independently proved or rejected; full suite and
  fixture check are green.
- Depends: A6.1–A6.6 and any implementation stages appended by A6.1.

#### A6.8 — Fixed-width type profile and schema v2
- Goal: introduce owned signedness/width type identities under a pinned C++17
  target profile before accepting new source types. Existing `int` semantics
  become explicit `i32`; bool remains distinct.
- Output/file set: integer type/profile value objects; model/frontend/lowering/
  contract/checker/cache/serializer updates; `i32`/`u32`/`i64`/`u64` type
  spellings and canonical decimal-string integer evidence;
  `codeskeptic.semantic-verification/v2`; immutable archived v1 fixtures;
  `tests/test_integer_types.py`; schema/result/adoption/prototype/changelog,
  fixture, README, PLAN/PROGRESS/TODO, and ratchet updates.
- Expanded exact file set: `semantic_verifier/{integer_types,model,frontend,
  lowering,contracts,vc,checker,smtlib,z3_backend,counterexample,cache}.py`;
  direct type/schema assertions in `tests/{test_cache,test_checker_soundness,
  test_contract_consistency,test_contracts,test_counterexample_quality,
  test_determinism,test_frontend_failures,test_lowering,test_z3_backend,
  test_integer_types}.py`; current and archived fixtures;
  `docs/{result_schema,schema_versioning,adoption_guide,
  semantic_verification_prototype,solver_decision}.md`; `CHANGELOG.md`,
  `README.md`, `PLAN.md`, `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: the frontend validates the pinned 32/64-bit, two's-complement, arithmetic
  right-shift target assumptions or fails closed; v1 corpus bytes stay immutable;
  current int32 reports migrate deterministically to v2 without proof-status
  changes; mixed report/IR majors are rejected; full suite and fixtures pass.
- Depends: A6.1.

#### A6.9 — Signed int64 QF_LIA lane
- Goal: add `long long`/`i64` arithmetic and exact i32/i64 promotions while
  retaining mathematical integers plus explicit C++17 definedness obligations.
- Output/file set: frontend/literal/lowering/VC/affine/SMT-LIB/replay support;
  width-parameterized range/overflow/division checks; `tests/test_int64.py`;
  examples, result/adoption/prototype/changelog, fixtures, PROGRESS/TODO/ratchet.
- Expanded exact file set: `semantic_verifier/{integer_types,model,frontend,
  lowering,contracts,vc,checker,smtlib,z3_backend,counterexample}.py`;
  `tests/{test_int64,test_integer_types,test_contracts,test_checker_soundness,
  test_smtlib,test_fixtures}.py`; `examples/int64_slice.cpp`; current fixture
  manifest/case/expected artifacts; `docs/{result_schema,adoption_guide,
  semantic_verification_prototype,solver_decision,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: i64 boundaries, widening, narrowing under the pinned profile, unary
  negation, add/sub/mul/div/rem, calls/contracts/loops, violation replay, and
  deterministic serialization pass; overflow and min/-1 never verify; `long`,
  extended integers, and unsupported literal types fail closed; full suite and
  fixtures pass.
- Depends: A6.8.

#### A6.10 — Unsigned integers and homogeneous QF_BV lane
- Goal: support u32/u64 arithmetic, assignments, and usual arithmetic
  conversions with exact modulo behavior; classify any unsigned/mixed query as
  pure QF_BV rather than mixing Int and BitVec sorts.
- Output/file set: query-fragment classifier; deterministic QF_BV emitter;
  signed/zero extension and truncation; BV model parse/replay/minimization;
  cache/backend logic identity; `tests/test_unsigned.py` and
  `tests/test_smtlib_bv.py`; docs/examples/fixtures/changelog/ledger/ratchet.
- Expanded exact file set: `semantic_verifier/{integer_types,model,query_fragment,
  lowering,contracts,vc,checker,smtlib,z3_backend,backend}.py`;
  `tests/{test_unsigned,test_smtlib_bv,test_integer_types,test_contracts,
  test_int64,test_fixtures}.py`;
  `examples/unsigned_slice.cpp`; current fixture manifest/case/expected
  artifacts and `tools/regenerate_fixtures.py`; `docs/{result_schema,adoption_guide,
  semantic_verification_prototype,solver_decision,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: unsigned wrap, mixed i32/u32/i64/u64 conversion table, comparisons,
  arithmetic, division/remainder definedness, calls/contracts/loops, replay,
  and cache separation pass; no query mixes Int and BitVec; affine and default
  cross-check return explicit unsupported for BV-required obligations while
  `--backend z3` decides them; full suite and fixtures pass.
- Depends: A6.9.

#### A6.11 — C++17 bitwise and shift operators
- Goal: add `~`, `&`, `|`, `^`, `<<`, and `>>` under integral promotions,
  usual conversions, and the pinned C++17 target profile.
- Output/file set: contract/frontend/lowering/IR/VC QF_BV operators; shift-count
  and signed-left-shift definedness obligations; arithmetic/logical right-shift
  selection; `tests/test_bitwise.py`; docs/examples/fixtures/changelog/ledger.
- Expanded exact file set: `semantic_verifier/{integer_types,frontend,lowering,
  contracts,model,query_fragment,vc,checker,smtlib,z3_backend,backend}.py`;
  `tests/{test_bitwise,test_contracts,test_integer_types,test_unsigned,test_fixtures}.py`;
  `examples/bitwise_slice.cpp`; current fixture manifest/case/expected artifacts
  and `tools/regenerate_fixtures.py`; `docs/{result_schema,adoption_guide,
  semantic_verification_prototype,solver_decision,
  integer_semantics_decision}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`,
  `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: positive/negative bit patterns, mixed signedness, De Morgan, masks, and
  32/64-bit shifts replay exactly; negative or width-exceeding counts and
  invalid signed left shifts never verify; negative signed right shift follows
  the pinned arithmetic-shift profile; unsupported compound/rotate/library
  operations fail closed; deterministic SMT/reports, full suite, fixtures pass.
- Depends: A6.10.

#### A6.12 — Fixed-width integer phase gate
- Goal: freeze the selected target profile, LIA/BV classifier, backend support
  matrix, migration, and proof equivalence for legacy int32 obligations.
- Output/file set: combined integer example/fixtures, deterministic phase-gate
  tool, operations/capability docs, schema migration evidence, PROGRESS/TODO.
- Expanded exact file set: `examples/fixed_integer_gate.cpp`;
  `fixtures/{manifest.json,cases/fixed_integer_gate.cpp,
  expected/fixed_integer_gate.{ir,report.json}}`;
  `tools/{integer_phase_gate,regenerate_fixtures}.py`;
  `tests/{test_integer_phase_gate,test_fixtures}.py`;
  `docs/{integer_operations,integer_semantics_decision,solver_decision,
  adoption_guide,semantic_verification_prototype,result_schema,
  schema_versioning}.md`; `CHANGELOG.md`, `README.md`, `PLAN.md`, `PROGRESS.md`,
  `TODO.md`, and the test ratchet. Archived v1 fixtures are read-only evidence.
- DoD: every A6.1 truth-table row has positive/negative evidence; legacy v1 is
  immutable and migrated v2 status-equivalent; LIA queries remain cross-checked;
  BV queries are replayed by explicit Z3 mode and fail closed in affine/both;
  repeated gate/fixture bytes match; full suite and fixture check pass.
- Depends: A6.8–A6.11.

---

## 6. PROGRAM B — Production (CodeSkeptic integration)

Goal: carry the lab-proven architecture into CodeSkeptic's real Clang
infrastructure. Reference: prototype fixtures = the specification.

### Phase B1 — Native adapter (M4)

#### B1.1 — Fixture export: IR + obligation JSONs for a corpus from the
  prototype (`fixtures/` directory, generator script)
- Goal: publish a self-describing, backend-independent native-adapter corpus
  from the reference frontend/lowering/VC pipeline.
- Output: canonical Semantic IR and obligation JSON envelopes for every
  current fixture case, a hash-bearing export manifest, and check/write CLI.
- Expanded exact file set: `tools/export_fixtures.py`;
  `tests/test_fixture_export.py`; `fixtures/native_adapter/**`; `README.md`,
  `CHANGELOG.md`, `PLAN.md`, `PROGRESS.md`, `TODO.md`, and the test ratchet.
- DoD: `python tools/export_fixtures.py` produces a deterministic corpus; two
  runs are byte-identical; `python tools/export_fixtures.py --check` matches
  committed bytes; exported IR/obligations match the current report corpus;
  full suite and fixture checks are green.
#### B1.2 — Standalone semantic module skeleton in CodeSkeptic (NO reporter
  dependency; `src/semantic/` — without touching the Rule.h seam)
- Goal: establish owned semantic value objects and a validation seam in the
  production C++17 core before any Clang AST lowering is admitted.
- Output: CodeSkeptic `src/semantic/SemanticIR.{h,cpp}`, build integration, and
  focused unit tests; no Rule, Diagnostic, reporter, or server dependency.
- Expanded exact file set: CodeSkeptic `src/semantic/SemanticIR.{h,cpp}`,
  `src/CMakeLists.txt`, `tests/SemanticIRTest.cpp`, and `tests/CMakeLists.txt`;
  reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- DoD: the standalone module builds as part of `codeskeptic_core`; owned
  expressions/statements/functions/modules preserve source order and reject
  malformed identity/location structure; focused tests and the full production
  suite pass without modifying `src/core/Rule.h`; the reference suite stays
  green.
#### B1.3 — ASTContext → Semantic IR lowering (v0 subset, exact)
- Goal: lower a deliberately small scalar C/C++ subset directly from Clang's
  `ASTContext` into owned Semantic IR without pointer leakage or silent
  approximation.
- Output: a production `SemanticLowerer` seam, deterministic source/function/
  symbol/node identities, exact scalar expression and structured-statement
  lowering, explicit unsupported records, build integration, and focused tests.
- Expanded exact file set: CodeSkeptic
  `src/semantic/{SemanticIR,SemanticLowerer}.{h,cpp}`, `src/CMakeLists.txt`,
  `tests/{SemanticIR,SemanticLowerer}Test.cpp`, and `tests/CMakeLists.txt`;
  reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Supported v0 boundary: main-file free-function definitions; `void`, `bool`,
  and fixed 32/64-bit integer types; named parameters and initialized scalar
  locals; scalar assignment; direct calls; return; `if`/`else`; integer and
  boolean literals; variable references; exact supported unary/binary
  operators and implicit scalar casts. Every other declaration, type,
  expression, or statement that affects a selected function is recorded as
  unsupported and is never approximated.
- DoD: two lowerings of the same in-memory TU are structurally identical;
  supported nodes retain canonical types, source locations, source order, and
  stable identities; shadowed variables remain distinct; representative
  unsupported types/statements/calls fail closed with stable reasons; no
  `Rule`, reporter, or server dependency is introduced; focused and full
  production suites and the reference suite pass.
#### B1.4 — Byte-for-byte comparison harness: fixture equality inside the
  in-memory Clang test harness
- Goal: make the exported Python adapter corpus an executable compatibility
  specification for the production C++ frontend and owned IR.
- Output: canonical native-adapter JSON serialization; a vendored hash-checked
  copy of the B1.1 source/IR corpus; an in-memory Clang fixture runner; exact
  aggregate/reference/frame/loop/SSA lowering needed by the corpus; and a
  per-case byte-comparison gate with deterministic diagnostics.
- Expanded exact file set: CodeSkeptic
  `.gitattributes`; `src/semantic/{SemanticIR,SemanticJson,SemanticLowerer}.{h,cpp}`;
  `src/contracts/{ContractParser,ContractInfo}.{h,cpp}`; `src/CMakeLists.txt`;
  `tests/{CMakeLists.txt,SemanticIRTest.cpp,SemanticLowererTest.cpp,
  NativeAdapterFixtureTest.cpp}`; `tests/fixtures/native_adapter/**`; reference
  `PLAN.md`, `PROGRESS.md`, and `TODO.md`. The B1.1 exported corpus is copied
  byte-for-byte and is not hand-edited in production.
- Compatibility lanes: (1) canonical envelope/value serialization and scalar
  cases; (2) arrays/value records, references, modular frames, and SSA merges;
  (3) while-loop invariants/termination metadata and full-corpus gate. Every
  lane keeps unsupported constructs explicit until its exact lowering lands.
- DoD: all 14 vendored source hashes and Python IR hashes equal the B1.1
  manifest; native serialization is byte-identical to every corresponding
  `*.semantic-ir.json`; two complete native renders are byte-identical;
  mismatch output names the case and first byte/line; no Python process or
  fixture substitution participates in native rendering; focused/full
  production and reference suites pass.
- Depends: B1.5 (contract-bearing fixtures require native contract adaptation).
#### B1.5 — Extend the existing `cs:` parser with arithmetic; ContractInfo
  adaptation
- Goal: make the production contract surface express the reference scalar
  contract language and adapt accepted clauses into owned Semantic IR without
  weakening the existing rule-facing contract recognizers.
- Output: a precedence-correct owned contract-expression tree; strict typed
  scalar adaptation for native parameters and `return`; requires/ensures IR
  attachment and requires-assume lowering; explicit deterministic adaptation
  issues; updated grammar documentation and focused compatibility tests.
- Expanded exact file set: CodeSkeptic `CONTRACTS.md`;
  `src/contracts/{ContractParser,ContractInfo}.{h,cpp}`;
  `src/semantic/{SemanticIR,SemanticLowerer}.{h,cpp}`;
  `tests/{Contract,SemanticIR,SemanticLowerer}Test.cpp`; reference `PLAN.md`,
  `PROGRESS.md`, and `TODO.md`.
- Supported scalar grammar: boolean and fixed-width integer names, `return`,
  decimal literals, `true`/`false`, parentheses, unary `! - ~`, multiplicative,
  additive, shift, relational, equality, bitwise, and logical operators with
  the reference precedence and pinned usual-arithmetic conversions. Pointer
  `null`, guarded ensures, effects, policies, arrays, records, and invariants
  remain available to their existing consumers but are outside scalar IR
  adaptation and fail closed there.
- DoD: legacy contract/parser/rule tests remain green; arithmetic precedence,
  literal bounds, signed/unsigned conversion, unknown names, type mismatch,
  non-boolean clauses, provenance, text, and locations have positive/negative
  tests; valid native requires/ensures equal the reference expression shape;
  requires become source-ordered assume nodes; malformed or unadaptable
  clauses never disappear; focused/full production and reference suites pass.

### Phase B2 — VC + referee on the production path

#### B2.0 — Native VC/referee route decision
- Goal: choose the production execution boundary before porting proof logic;
  compare a native C++ VC generator with a Python helper without weakening D2,
  D3, D4, packaging, determinism, or fail-closed behavior.
- Output: `docs/semantic-verification-vc-decision.md` in CodeSkeptic with the
  measured reference dependency surface, alternatives, trust boundaries,
  selected route, rejected route, staged rollout, and reopen criteria; detailed
  B2.1-B2.4 contracts below.
- Decision: port VC generation and referee orchestration to C++17. Keep Z3 as
  the only external logic process through deterministic SMT-LIB2 text; do not
  add Python to the CodeSkeptic runtime or release package.
- Exact file set: CodeSkeptic
  `docs/semantic-verification-vc-decision.md`; reference `PLAN.md`,
  `PROGRESS.md`, and `TODO.md`.
- DoD: the record inventories the current native seams and the direct Python
  helper dependency surface; scores both routes against soundness, packaging,
  determinism, portability, schema drift, diagnostics, and testability; names
  the chosen interfaces and stage ownership; introduces no runtime/code change;
  full production and reference suites pass and both worktrees are clean.
- Depends: B1.4.

#### B2.1 — Native verification-condition generator and fixture equality
- Goal: deterministically transform owned native Semantic IR into the same
  obligations as the Python reference without invoking a checker.
- Output: immutable native obligation/trace-template value objects; a pure
  `VerificationConditionGenerator`; canonical obligation JSON; vendored B1.1
  obligation payloads; and a full 14-case byte-equality harness.
- Exact file set: CodeSkeptic
  `src/verification/{VerificationIR,VerificationConditionGenerator,
  VerificationJson}.{h,cpp}`; `src/CMakeLists.txt`;
  `tests/{CMakeLists.txt,VerificationConditionTest.cpp,
  NativeObligationFixtureTest.cpp}`;
  `tests/fixtures/native_adapter/{manifest.json,*.obligations.json}`; reference
  `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Boundaries: consume only validated owned IR; preserve source/order/IDs; emit
  explicit unsupported obligations for unsupported modules, recursion,
  unannotated loops, heterogeneous query fragments, and every omitted rule;
  no Z3/process/Rule/Diagnostic dependency in this stage.
- DoD: every vendored obligation hash matches B1.1; all 14 native obligation
  payloads are byte-identical to Python; repeated generation is identical;
  expression safety, contract consistency, calls, frames, branches, loops,
  merges, trace templates, and negative boundaries have focused tests; full
  production and reference suites pass.
- Depends: B2.0.

#### B2.2 — Native deterministic referee and verification rule
- Goal: check native obligations at the `Rule::check` seam while preserving the
  complete result taxonomy and constitution-level counterexample replay.
- Output: `CheckerBackend` interface; deterministic SMT-LIB2 emitter; Z3 path,
  timeout, subprocess, model parser, and replay components; a
  `SemanticVerificationRule`; and a result carrier that represents
  `verified`, `violated`, `unknown`, `unsupported`, and `solver_error` rather
  than forcing positive/non-finding states into the legacy finding shape.
- Planned file set (confirm before edits): CodeSkeptic
  `src/verification/{CheckerBackend,SmtLib,Z3ProcessRunner,
  CounterexampleReplay,SemanticVerificationRule,VerificationResult}.{h,cpp}`;
  `src/core/{Diagnostic.h,Rule.h}`; `src/engine/{RuleEngine.h,RuleEngine.cpp}`;
  `src/analyzer/{StaticAnalyzer.h,StaticAnalyzer.cpp}`; `src/CMakeLists.txt`;
  corresponding focused tests and `tests/CMakeLists.txt`; reference
  `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Boundaries: Z3 remains an unlinked subprocess (D4); fixed solver options and
  sorted serialization only; every reported model is replayed against its
  original obligation; missing/crashed solver is `solver_error`, timeout is
  `unknown`, and unsupported is never promoted.
- DoD: native referee results equal reference result fixtures for the selected
  corpus; corrupt-model injection proves replay rejection; deterministic repeat,
  missing-Z3, timeout, crash, unsupported, and backend-interface tests pass;
  the verification rule coexists with legacy findings; full suites pass.
- Depends: B2.1.

#### B2.3 — SARIF semantic-verification output
- Goal: expose obligations, statuses, counterexamples, and replay-safe traces in
  standard report output without changing legacy finding semantics.
- Output: versioned SARIF properties/result mapping for every verification
  status plus deterministic serialization and compatibility fixtures.
- Planned file set (confirm before edits): CodeSkeptic
  `src/reporter/{SarifReporter.h,SarifReporter.cpp}` and verification result
  adapters; `tests/SarifReporterTest.cpp`, semantic SARIF fixtures, and
  `tests/CMakeLists.txt`; reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- DoD: positive, violation, unknown, unsupported, and solver-error records are
  distinguishable; counterexamples/traces retain obligation IDs and locations;
  old SARIF fixtures remain unchanged; repeated reports are byte-identical;
  full suites pass.
- Depends: B2.2.

#### B2.4 — MCP `verify_function` referee surface
- Goal: give agents a narrow production referee tool for one selected function,
  using exactly the same native pipeline and status semantics as CLI analysis.
- Output: `verify_function` MCP schema/handler, deterministic function
  selection, structured obligations/results/counterexamples, and bounded error
  responses.
- Planned file set (confirm before edits): CodeSkeptic
  `src/server/{McpServer.h,McpServer.cpp}` plus the minimal analyzer/
  verification wiring; `tests/McpServerTest.cpp`, focused fixtures, and
  `tests/CMakeLists.txt`; reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- DoD: tool discovery advertises the stable schema; exact/ambiguous/missing
  function selection is tested; verified/violated/unknown/unsupported/
  solver-error responses are structured and deterministic; no AI judgment
  enters the referee path; full suites pass.
- Depends: B2.3.

### Phase B3 — Sidecar contract database

- B3.0 — Expansion
- B3.1 — Wire `.csk` sidecars into verification (bodiless external function +
  sidecar contract = call obligations)
- B3.2 — First stdlib mini-models (value-semantic, heap-free functions only:
  `abs`, `min`, `max` level; vector/string EXCLUDED — no heap model before A6)
- B3.3 — Contract package versioning/distribution format

### Phase B4 — CI and adoption path

- B4.0 — Expansion
- B4.1 — CI gate mode: exit codes, baseline suppression (new violation ≠
  historical debt — the adoption key)
- B4.2 — Editor/report integration (SARIF consumers)

---

## 7. PROGRAM C — Intent layer

### Phase C1 — `cs: ai` proposal loop

- C1.1 — Proposal template: body → candidate contracts (offline prompt pack;
  model calls live outside this repo, output format defined here)
- C1.2 — Referee pre-screening: proposals pass satisfiability /
  well-formedness checks before any human sees them (contradictory proposals
  never reach the human)
- C1.3 — Approval flow: `cs: ai` → human edits and removes the `ai` marker →
  "accepted intent" (the mechanism of constitution #9)

### Phase C2 — Contract-first workflow (4a)

- C2.1 — Task template: prose request → proposed contract set → approval →
  code → verification; `docs/contract_first_workflow.md` + one end-to-end run
- C2.2 — Pilot the workflow on this project itself (one A-phase stage run this
  way; comparison note in PROGRESS)

### Phase C3 — C++26 contracts bridge (far; expand via C3.0)

- C3.0 — Research: `pre`/`post`/`contract_assert` ↔ `cs:` mapping
- C3.1 — Accept standard syntax when compiler support matures

### Phase C4 — Enforcement ladder (2b) — from contract to test

- C4.0 — Expansion
- C4.1 — Unproven obligation → auto-generated property-test skeleton (what
  cannot be proven does not silently vanish; it steps one rung down)
- C4.2 — Runtime assert generation (last rung); end-to-end demo that all
  three rungs derive from one `cs:` source

*(C5 — RuleDSL bridge: deliberately PARKED. Not opened before A/B mature.)*

---

## 8. PROGRAM D — World model (fact index / SCI)

### Phase D1 — Fact extraction v0

- D1.1 — Fact schema: symbols, def/use, call graph, mutation sets, purity
  flags; deterministic JSON (same discipline as the IR schema)
- D1.2 — Extractor v0: in the lab from Clang AST JSON (reuse the existing
  frontend); in production from ASTContext (after B1)
- D1.3 — Tests: determinism + golden files over an example corpus

### Phase D2 — Query interface

- D2.1 — CLI queries: `who-calls X`, `who-mutates Y`, `neighborhood X k=2`
- D2.2 — Query endpoint as an MCP tool (the agents' map — the stage where the
  "Semantic Compiler Interface" is born)
- D2.3 — Context-pack generator (1c): given a symbol, emit a compact
  fact-based context bundle for an AI session (target ≤2K tokens)

### Phase D3 — Architectural rules (1b)

- D3.0 — Expansion
- D3.1 — Dependency rule definition (allowed/forbidden edges between layers)
- D3.2 — Enforcement as a CodeSkeptic rule + SARIF report

### Phase D4 — Incrementality (1d): file-hash invalidation; re-extract only
  changed TUs

### Phase D5 — Verified facts: trust labels (`derived` | `proved`); the
  referee-provable subset of `pure` claims promotes to `proved` (expand via
  D5.0)

---

## 9. PROGRAM E — AI loop

### Phase E1 — Repair loop (M5)

- E1.1 — Repair-bundle format: obligation + counterexample + source slice +
  related contracts (one machine-readable JSON)
- E1.2 — Loop harness: bundle → model → patch → re-verify → (≤N iterations);
  every step logged
- E1.3 — Metrics log: iteration count, success, time per obligation

### Phase E2 — The "consciousness experiment" (measurable hypothesis)

- E2.1 — Seeded-bug corpus: ≥20 functions with known violations
- E2.2 — Two arms: (a) compiler/test errors only, (b) the E1.1 repair bundle;
  metric: iterations to a verified patch
- E2.3 — Report: hypothesis "(b) median ≥40% lower"; whatever the outcome, it
  is written honestly to PROGRESS + `docs/experiment_e2.md`

### Phase E3 — Assumption declaration protocol (2d)

- E3.0 — Expansion
- E3.1 — `assume-manifest` format: the agent dumps its assumptions before
  coding; each is converted to a contract/test or explicitly marked
  uncheckable
- E3.2 — Pilot in our own sessions

### Phase E4 — Referee-guided search (5a)

- E4.0 — Expansion
- E4.1 — Best-of-N: N patch candidates → verify all → select the passing one;
  measure uplift vs single-shot

### Phase E5 — RLVF design note (far; MEMO ONLY, no implementation)

- E5.1 — Design/data-schema note on using the referee as a reward signal

---

## 10. PROGRAM F — Process & infrastructure

### Phase F0 — Plan-system bootstrap

- F0.1 — Plan files (PLAN/PROGRESS/TODO/CLAUDE.md)
- F0.2 — Guardrails: `.githooks/` (pre-commit: tests + ratchet + ledger;
  commit-msg: stage ID), `guardrails/test_baseline.txt`, `.gitattributes`
  (LF for hooks), README workflow section, `core.hooksPath` activation
- F0.3 — First commit of the plan system

### Phase F1 — Benchmark set (M6b)

- F1.1 — Corpus: 30–50 curated functions (inside the supported subset, with a
  difficulty ladder)
- F1.2 — Runner: `verified/unknown/violated/unsupported` rates + timings →
  `benchmarks/results/` (dated, append-only)
- F1.3 — Trend tracking: run at every A-phase gate; regression = red

### Phase F2 — Golden/fixture infrastructure

- F2.1 — `fixtures/` layout + regeneration script (`tools/`)
- F2.2 — Determinism CI job: suite + fixtures twice, byte comparison

### Phase F3 — Documentation upkeep

- F3.1 — `docs/semantic_verification_prototype.md` updated at every phase
  gate (keep the implemented / partial / proposed distinction)
- F3.2 — Result-taxonomy + schema reference page
- F3.3 — Adoption guide (path into a new codebase)

### Phase F4 — Versioning

- F4.1 — Schema version policy (v0→v1 triggers; the A2.1 IR extension is the
  first candidate)
- F4.2 — CHANGELOG discipline

---

## 11. Non-goals (permanent)

- A new general-purpose programming language.
- General FOL / quantified proof search (leaving decidable fragments requires
  a new D-decision).
- Full C++ verification claims; heap/alias/ownership models (in no form
  before A6), templates/exceptions/concurrency (without a separate decision).
- AI as referee (D8 — no exceptions).
- Production-certification claims.
- Converting DataflowEngine into the Semantic IR (different contract,
  different job).

## 12. Success criteria (program gates)

- **A1:** vertical_slice → `unknown=0`; suite ≥85 tests, green under both
  backends.
- **A2:** multi-function chain example `verified` + violated variant with
  counterexample.
- **A3:** invariant-annotated sum loop `verified`; without invariant
  `unsupported`.
- **B1:** fixture corpus byte-identical between C++ and Python.
- **D2:** `neighborhood` query <1 s; context pack ≤2K tokens.
- **E2:** experiment report published (whatever the outcome).
- **F1:** benchmark trend file contains ≥3 data points.

## 13. Extension rule

New work = a new phase/stage inside an existing program (ID rules apply); if
it fits no program, open a new program letter (G, H, ...). The extending
session writes "plan extended: <IDs>" to PROGRESS.
