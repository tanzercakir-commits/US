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
- Exact file set: CodeSkeptic
  `src/verification/{CheckerBackend,SmtLib,Z3ProcessRunner,
  CounterexampleReplay,SemanticVerificationRule,VerificationResult}.{h,cpp}`;
  `src/core/Rule.h`; `src/engine/{RuleEngine.h,RuleEngine.cpp}`;
  `src/analyzer/{StaticAnalyzer.h,StaticAnalyzer.cpp}`; `src/CMakeLists.txt`;
  `tests/{CMakeLists.txt,SmtLibTest.cpp,Z3ProcessRunnerTest.cpp,
  CounterexampleReplayTest.cpp,SemanticVerificationRuleTest.cpp,
  NativeRefereeFixtureTest.cpp}`; reference `PLAN.md`, `PROGRESS.md`, and
  `TODO.md`.
- Boundaries: Z3 remains an unlinked subprocess (D4); fixed solver options and
  sorted serialization only; every reported model is replayed against its
  original obligation; missing/crashed solver is `solver_error`, timeout is
  `unknown`, and unsupported is never promoted.
- DoD: native status summaries equal the manifest-pinned reference summaries
  for all 14 fixtures; replayed scalar counterexamples and resolved traces match
  their original obligations; corrupt-model injection proves replay rejection;
  deterministic repeat, missing-Z3, timeout, crash, unsupported, and backend-
  interface tests pass; the verification rule coexists with legacy findings;
  full suites pass.
- Depends: B2.1.

#### B2.3 — SARIF semantic-verification output
- Goal: expose obligations, statuses, counterexamples, and replay-safe traces in
  standard report output without changing legacy finding semantics.
- Output: versioned SARIF properties/result mapping for every verification
  status plus deterministic serialization and compatibility fixtures.
- Exact file set: CodeSkeptic
  `src/reporter/{Reporter.h,SarifReporter.h,SarifReporter.cpp}`;
  `src/analyzer/StaticAnalyzer.cpp`; `tests/SarifReporterTest.cpp`; reference
  `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Boundary: the base reporter overload preserves every legacy reporter and
  existing one-argument SARIF byte contract; semantic results are appended in
  obligation order with a versioned property bag, while rule IDs remain sorted.
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
- Exact file set: CodeSkeptic `src/server/{McpServer.h,McpServer.cpp}`;
  `src/analyzer/StaticAnalyzer.h`; `src/engine/RuleEngine.h`;
  `src/verification/{SemanticVerificationRule.h,SemanticVerificationRule.cpp,
  VerificationConditionGenerator.h,VerificationConditionGenerator.cpp}`;
  `tests/McpServerTest.cpp`; reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Boundary: a plain selector must identify one function name, while a canonical
  signature key selects an overload exactly; error candidates are sorted and
  capped, injected backends remain a test seam, and production always defaults
  to the native Z3 referee.
- DoD: tool discovery advertises the stable schema; exact/ambiguous/missing
  function selection is tested; verified/violated/unknown/unsupported/
  solver-error responses are structured and deterministic; no AI judgment
  enters the referee path; full suites pass.
- Depends: B2.3.

### Phase B3 — Sidecar contract database

#### B3.0 — Sidecar contract database expansion

- Goal: replace the coarse B3 headings with bounded stages that connect the
  existing adjacent `.csk` parser to native verification, add a deliberately
  small standard-library model set, and make contract packs distributable.
- Output/exact file set: reference `PLAN.md`, `PROGRESS.md`, and `TODO.md` only.
- DoD: B3.1-B3.3 each declare Goal/Output/file boundary/DoD/Depends; load and
  conflict precedence, provenance, supported model scope, schema failure, and
  offline distribution rules are explicit; full production/reference suites
  remain green.
- Depends: B2.4.

#### B3.1 — Adjacent `.csk` contracts on the native verification path

- Goal: bind contracts from the declaring file's existing adjacent `.csk`
  sidecar into owned Semantic IR so a bodiless external declaration can create
  call preconditions, assumed postconditions, and contract well-formedness
  obligations without source edits.
- Output: provenance-preserving inline/sidecar semantic merge, strict typed
  binding through the existing contract grammar, and end-to-end CLI/SARIF/MCP
  evidence for a sidecar-contracted external call.
- Exact file set: CodeSkeptic `CONTRACTS.md`;
  `src/contracts/{ContractInfo.h,ContractInfo.cpp}`;
  `src/verification/VerificationConditionGenerator.cpp`;
  `tests/{SemanticLowererTest.cpp,McpServerTest.cpp}`; reference `PLAN.md`,
  `PROGRESS.md`, and `TODO.md`.
- Wiring decision: semantic contract adaptation loads inline and adjacent
  sidecar sources separately, binds each against the same parameter/type
  environment, then merges them inline-first. Targeted VCG emits direct callee
  contract consistency/well-formedness dependencies before trusting ensures.
- Boundaries: B3.1 reads only adjacent `<declaring-file>.csk` files; inline
  clauses remain first in source order and sidecar clauses retain their `.csk`
  file/absolute line provenance. Conflicting or malformed clauses are never
  silently selected or dropped. Package search and built-in models wait for
  B3.2-B3.3.
- DoD: a bodiless external declaration plus sidecar `requires` produces a call
  obligation and a false call violates; sidecar `ensures` is assumed only after
  its well-formedness obligation and can prove a caller postcondition; malformed,
  unbound, duplicate/conflicting, missing, and edited-sidecar cases fail closed
  with deterministic `.csk` locations; repeated IR/obligations/MCP bytes match;
  legacy sidecar and full production/reference suites pass.
- Depends: B2.4.

#### B3.2 — First value-semantic standard-library mini-models

- Goal: model only scalar, heap-free `abs`, `min`, and `max` calls under the
  pinned C++17 integer profile, including namespace/header declarations, without
  claiming alias, heap, floating-point, comparator, or initializer-list behavior.
- Output: an offline built-in mini-model registry keyed by qualified canonical
  signature; referenced external-declaration synthesis in lowering; sound
  `abs` minimum-value preconditions and homogeneous `min`/`max` postconditions;
  positive/negative examples and focused tests.
- Exact file set: CodeSkeptic
  `src/contracts/{StdlibModels.h,StdlibModels.cpp}`;
  `src/semantic/SemanticLowerer.cpp`;
  `src/verification/VerificationConditionGenerator.cpp`; `src/CMakeLists.txt`;
  `tests/{CMakeLists.txt,StdlibModelsTest.cpp,SemanticLowererTest.cpp,
  VerificationConditionTest.cpp}`; `examples/stdlib_models.cpp`;
  `CONTRACTS.md`, `README.md`; reference `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Wiring decision: source-header `FunctionDecl` identities are matched before
  lowering against an offline registry, then synthesized as bodyless,
  signature-unique value-semantic functions. Calls and models share that
  collision-proof semantic name; unsupported declarations keep their ordinary
  name and the existing fail-closed external-call path.
- Boundaries: exact qualified signatures only; `abs` covers signed i32/i64 with
  the minimum value excluded, and `min`/`max` cover homogeneous i32/u32/i64/u64
  value observations. Unsupported overloads remain explicit; user functions
  named `abs`, `min`, or `max` never inherit a model. No filesystem/network
  package discovery is introduced in this stage.
- DoD: supported calls no longer emit `uncontracted external call`; valid
  boundary examples verify and wrong caller/postcondition variants violate with
  replayed models; signed-min, mixed-type, floating, comparator, initializer-
  list, pointer/reference-alias, and lookalike user functions fail closed or
  remain unmodeled; model lookup and results repeat byte-identically; full
  production/reference suites pass.
- Depends: B3.1.

#### B3.3 — Versioned contract packages and offline distribution

- Goal: move built-in and user-supplied model sets behind a versioned,
  relocatable, deterministic contract-package format with no network access on
  the analysis path.
- Output: manifest/schema and hash-checked loader, explicit package search
  configuration, deterministic conflict policy and provenance, migration of the
  B3.2 mini-models, release/Docker/action packaging, and adoption documentation.
- Exact file set: CodeSkeptic `contract-packs/**`;
  `src/contracts/{ContractPackage.h,ContractPackage.cpp,StdlibModels.h,
  StdlibModels.cpp}`; `src/config/{Config.h,Config.cpp}`;
  `src/analyzer/StaticAnalyzer.cpp`; `src/server/McpServer.cpp`;
  `src/CMakeLists.txt`; `tests/{CMakeLists.txt,ContractPackageTest.cpp,
  ConfigTest.cpp,McpServerTest.cpp,SemanticLowererTest.cpp,
  StdlibModelsTest.cpp}`;
  `scripts/package_release.sh`, `Dockerfile`,
  `action.yml`, `CONTRACTS.md`, `README.md`, `docs/usage.md`; reference
  `PLAN.md`, `PROGRESS.md`, and `TODO.md`.
- Wiring decision: the built-in registry is loaded from the same v1 package
  schema as explicit local packs. Runtime discovery checks a relocatable
  executable-relative share tree before the compiled source-tree fallback;
  explicit paths are additive and sorted. Canonical signatures are deduplicated
  only when their complete models are identical; conflicting claims are removed
  and remain blocked rather than receiving precedence.
- Boundaries: discovery is bundled-default plus explicit local paths only;
  manifests pin schema major, package identity/version, target profile, sorted
  files, and SHA-256 hashes. Unknown majors, hash mismatch, traversal, malformed
  entries, target mismatch, and non-identical duplicate signature claims fail
  closed; there is no silent precedence override.
- DoD: source-tree, relocated release, Docker, and action layouts resolve the
  same bundled pack; explicit local packs load in sorted order; missing optional
  packs are reported without changing proof status, while corrupt/incompatible/
  conflicting packs block affected claims; repeated manifests, diagnostics, IR,
  obligations, and results are byte-identical; packaging smoke tests and full
  production/reference suites pass.
- Depends: B3.2.

### Phase B4 — CI and adoption path

#### B4.0 — CI and adoption path expansion

- Goal: replace the coarse B4 headings with bounded stages that expose native
  semantic verification through an opt-in production CI gate and make its
  existing SARIF records stable for real editor/code-scanning consumers.
- Output/exact file set: reference `PLAN.md`, `PROGRESS.md`, and `TODO.md` only.
- Route decision: legacy CLI/rule defaults, finding baselines, and exit bytes
  remain unchanged unless semantic verification is explicitly enabled. The
  semantic gate owns a separate deterministic obligation baseline because a
  legacy diagnostic key cannot safely identify a proof obligation. SARIF is
  the first editor/host integration boundary; no custom editor extension is
  introduced in B4.
- DoD: B4.1-B4.2 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  semantic enablement, gate modes, exit precedence, baseline matching/status
  escalation, SARIF fingerprints, consumer behavior, and rollout defaults are
  explicit; full production/reference suites remain green.
- Depends: B3.3.

#### B4.1 — Opt-in semantic-verification CI gate

- Goal: run the native referee from the normal CLI and packaged Action with a
  gradual-adoption gate where historical semantic debt is recorded but a new
  or worsened obligation cannot pass as verified.
- Output: `--semantic-verify`; `--semantic-gate
  report|violations|complete`; deterministic semantic baseline read/write;
  console/SARIF summaries; Action inputs/outputs; and an end-to-end CI fixture.
- Exact file set: CodeSkeptic `src/main.cpp`;
  `src/config/{Config.h,Config.cpp}`; `src/core/ExitPolicy.h`;
  `src/verification/{SemanticVerificationRule.h,
  SemanticVerificationRule.cpp,VerificationResult.h,VerificationResult.cpp,
  VerificationBaseline.h,VerificationBaseline.cpp}`;
  `src/analyzer/{StaticAnalyzer.h,StaticAnalyzer.cpp}`;
  `src/reporter/{ConsoleReporter.h,ConsoleReporter.cpp}`; `src/CMakeLists.txt`;
  `tests/{CMakeLists.txt,ConfigTest.cpp,MacSdkPathTest.cpp,
  SemanticVerificationGateTest.cpp,VerificationBaselineTest.cpp}`;
  `tests/fixtures/semantic_gate/**`; `action.yml`;
  `.github/workflows/action-selftest.yml`; `README.md`;
  `docs/{usage.md,integrations.md}`; reference `PLAN.md`, `PROGRESS.md`, and
  `TODO.md`.
- Gate/exit decision: semantic verification is disabled by default. When
  enabled, `report` never gates semantic statuses, `violations` gates only
  replayed violations, and `complete` also gates unknown/unsupported results;
  solver/checker errors always fail. After baseline classification, precedence
  is solver error=3, incomplete proof or existing zero-coverage failure=2,
  violation/legacy finding=1, clean=0. The Action remains report-only by
  default and exposes the raw analyzer code plus status counts.
- Baseline decision: `--write-semantic-baseline` writes sorted v1 entries for
  non-verified results; `--semantic-baseline` affects gating only, never deletes
  results from reports. Keys use a deterministic semantic fingerprint plus the
  exact status, so line shifts and counterexample minimization do not create
  churn while `unknown`/`unsupported` becoming `violated`, or any solver error,
  resurfaces. A requested missing/malformed/incompatible baseline fails loud.
- Boundaries: no implicit proof run, no AI judgment, no solver-result caching,
  and no weakening of replay. JSON/HTML semantic rendering remains outside
  this stage and must reject or explicitly identify unsupported combinations;
  legacy invocations retain their current output and exit behavior.
- DoD: CLI and Action report all five statuses; every gate-mode/status/baseline
  row has an exit-code test; historical violations are visible but non-gating,
  new/worsened violations gate, unknown/unsupported never become verified, and
  solver errors are never baseline-suppressed; repeated baseline/summary/SARIF
  bytes match; the packaged-binary CI fixture and full production/reference
  suites pass.
- Depends: B4.0.

#### B4.2 — SARIF editor and code-scanning consumer integration

- Goal: make semantic-verification SARIF actionable and stable in GitHub code
  scanning and generic SARIF viewers without changing the legacy no-semantic
  report contract.
- Output: stable semantic rule descriptors and partial fingerprints; baseline
  state/gate metadata; navigable counterexample code flows; a deterministic
  SARIF consumer fixture/validator; Action upload/self-test coverage; and an
  editor/code-scanning adoption guide.
- Exact file set: CodeSkeptic
  `src/reporter/{SarifReporter.h,SarifReporter.cpp}`;
  `src/verification/{VerificationResult.h,VerificationResult.cpp}`;
  `tests/{CMakeLists.txt,SarifReporterTest.cpp,
  SemanticSarifConsumerTest.cpp}`; `tests/fixtures/semantic_sarif/**`;
  `action.yml`; `.github/workflows/action-selftest.yml`; `README.md`;
  `docs/{integrations.md,usage.md}`; reference `PLAN.md`, `PROGRESS.md`, and
  `TODO.md`.
- Boundaries: retain SARIF 2.1.0 and the versioned semantic property bag;
  fingerprints identify the logical obligation rather than line number,
  message text, solver model, or absolute checkout root. Verified remains a
  `pass`; violated, unknown, unsupported, and solver-error records remain
  visibly distinct and never masquerade as a passing result. No editor-specific
  extension, network lookup, or report-time AI is added.
- DoD: a pinned five-status fixture validates against the supported SARIF
  consumer contract; GitHub-style fingerprints survive checkout relocation and
  source-line shifts but change with obligation semantics; baseline status and
  gate relevance are explicit; physical/logical locations and replay traces
  navigate to source; the Action uploads the semantic SARIF and its self-test
  asserts the expected violation/status counts; legacy empty-semantic SARIF is
  byte-identical, repeated bytes match, and full production/reference suites
  pass.
- Depends: B4.1.

---

## 7. PROGRAM C — Intent layer

### Phase C1 — `cs: ai` proposal loop

#### C1.1 — Offline contract-proposal prompt pack

- Goal: turn a caller-supplied C++ function body and owned context into a
  deterministic, vendor-neutral prompt pack for candidate contracts.
- Output: versioned request/response JSON schemas; a self-contained system
  prompt; a frozen request/prompt fixture; a dependency-free renderer and CLI;
  and operator documentation for external model adapters.
- Exact file set: `semantic_verifier/contract_proposals.py`;
  `tools/contract_proposal.py`; `semantic_verifier/prompt_packs/contract_proposal/v1/**`;
  `fixtures/contract_proposals/**`; `tests/test_contract_proposals.py`;
  `docs/contract_proposal_loop.md`; `README.md`; `pyproject.toml`; `PLAN.md`, `PROGRESS.md`,
  `TODO.md`, and `guardrails/test_baseline.txt`.
- Boundaries: no network or model call, no source rewrite, no verifier verdict,
  and no accepted-intent claim. Output contracts carry the `cs: ai` marker;
  function bodies and context are data supplied by the caller, never guessed.
- DoD: both schemas parse and reject undeclared fields by construction; the
  frozen fixture renders byte-identically twice and matches its golden prompt;
  request identity ignores checkout location but changes with signature, body,
  or owned context; instructions and response schema preserve machine
  provenance and cannot represent an accepted contract; the focused and full
  suites pass.
- Depends: A1.

#### C1.2 — Deterministic proposal pre-screening

- Goal: keep malformed, contradictory, unsupported, unknown, or solver-error
  proposals away from the human review queue by running the normal referee.
- Output: request/response parser; strict candidate-to-source overlay; ordinary
  well-formedness/satisfiability pre-screen report; rejected/eligible fixtures;
  and CLI/documentation updates.
- Exact file set: `semantic_verifier/contract_proposals.py`;
  `tools/contract_proposal.py`; `semantic_verifier/prompt_packs/contract_proposal/v1/**`;
  `fixtures/contract_proposals/**`; `tests/test_contract_proposals.py`;
  `docs/contract_proposal_loop.md`; `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: the proposal remains `cs: ai`; pre-screening is deterministic and
  offline, uses the ordinary parser/referee, never weakens replay, and never
  changes rejected/unknown/unsupported/error outcomes into acceptance.
- DoD: malformed and contradictory candidates are rejected before review;
  only independently well-formed and satisfiable proposals become eligible;
  unknown, unsupported, and solver-error outcomes remain distinct rejections;
  overlays never mutate the input source; repeated reports are byte-identical;
  focused and full suites pass.
- Depends: C1.1.

#### C1.3 — Human approval and accepted-intent boundary

- Goal: make the constitution #9 transition explicit: an eligible `cs: ai`
  proposal is review material until a human edits it and removes `ai`.
- Output: deterministic review bundle and state checker; candidate-overlay
  export; accepted-intent validation; audit metadata; fixtures, CLI, tests, and
  workflow documentation.
- Exact file set: `semantic_verifier/contract_proposals.py`;
  `tools/contract_proposal.py`; `fixtures/contract_proposals/**`;
  `tests/test_contract_proposals.py`; `docs/contract_proposal_loop.md`;
  `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: tooling may emit `cs: ai` overlays but never removes `ai` on a
  human's behalf; accepted intent must be read back from separately edited
  source, and proposal/pre-screen evidence is not proof of specification truth.
- DoD: the state machine distinguishes proposed, rejected, reviewable, and
  accepted; only a separately supplied source with edited marker-free contracts
  can become accepted; stale or semantically changed approvals fail closed;
  audit output is deterministic and location-independent; focused and full
  suites pass.
- Depends: C1.2.

### Phase C2 — Contract-first workflow (4a)

#### C2.1 — Executable contract-first task template

- Goal: make prose request → proposed contracts → approval → code →
  verification a deterministic, inspectable workflow.
- Output: a versioned task manifest and Markdown template; a dependency-free
  workflow checker/CLI; separate proposed, accepted, and implemented artifacts;
  one frozen end-to-end run; operator documentation; and a golden run report.
- Exact file set: `semantic_verifier/contract_first.py`;
  `tools/contract_first_workflow.py`; `templates/contract_first_task.md`;
  `fixtures/contract_first/**`; `tests/test_contract_first.py`;
  `docs/contract_first_workflow.md`; `README.md`; `PLAN.md`, `PROGRESS.md`,
  `TODO.md`, and `guardrails/test_baseline.txt`.
- Boundaries: no model call, code generation, source-tree mutation, or simulated
  human identity. Proposed contracts retain `cs: ai`; accepted contracts are a
  separate operator-supplied artifact; the ordinary verifier alone decides the
  implementation result. Every input and transition is content-addressed.
- DoD: the template covers request, proposal, approval, implementation, and
  verification evidence; the runner rejects missing markers, unapproved or
  changed implementation contracts, path traversal, hash drift, unsupported,
  unknown, violation, and solver error; the frozen task completes with every
  obligation verified; repeated report bytes match the golden; focused and full
  suites pass.
- Depends: C1.3.

#### C2.2 — Contract-first pilot on the verifier project

- Goal: use the C2.1 workflow for one small A-style verification increment in
  this repository and compare it with the earlier implementation-first process.
- Output: a guarded-absolute-value pilot with prose task, proposed and accepted
  contracts, implementation, frozen workflow report, and comparison note.
- Exact file set: `pilots/contract_first/guarded_absolute/**`;
  `tests/test_contract_first.py`; `docs/contract_first_workflow.md`;
  `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: no retrospective claim that the historical A stages used this
  process; the pilot uses only already-owned verifier semantics and records the
  human-attestation limitation. It does not alter the trusted checker.
- DoD: the pilot starts from prose and marker-bearing proposals, records a
  separate marker-free approval before implementation, verifies the final C++
  through the ordinary referee with all statuses visible, detects a seeded
  contract/code mismatch, reproduces byte-identically, and records a concise
  artifact/defect-detection comparison in PROGRESS; focused and full suites
  pass.
- Depends: C2.1.

### Phase C3 — C++26 contracts bridge

#### C3.0 — Research and bridge expansion

- Goal: freeze the C++26 P2900 contract surface, current compiler evidence, and
  a sound mapping decision for the existing `cs:`/IR trust boundary.
- Output: a human-readable research note, machine-readable evidence matrix, and
  a fully declared C3.1 implementation stage.
- Exact file set: `docs/cpp26_contracts_bridge.md`;
  `research/cpp26_contracts_bridge.json`;
  `tests/test_cpp26_contracts_research.py`; `README.md`; `PLAN.md`;
  `PROGRESS.md`, `TODO.md`, and `guardrails/test_baseline.txt`.
- Boundaries: official WG21 working-draft/paper and compiler-project sources
  only for normative/support claims; dated support evidence is not a runtime
  dependency. This stage changes no parser, frontend, IR, VC, or checker
  behavior and makes no claim that `cs: invariant` or `cs: modifies` has a
  standard C++26 spelling.
- DoD: record the exact `pre`, `post`, and `contract_assert` grammar and
  evaluation boundary; map each form to an existing owned semantic concept;
  distinguish result binding, postcondition normal-exit scope, attributes,
  redeclarations, and evaluation semantics; record the SD-6 macro and both
  Clang/GCC status; reproduce a local Clang probe; choose a fail-closed bridge
  policy; expand C3.1 with exact files/boundaries/DoD; focused and full suites
  pass.
- Depends: C2.2.

#### C3.1 — Accept standard syntax through a fail-closed source bridge

- Goal: accept a controlled P2900 spelling subset now, while the Clang JSON-AST
  frontend still lacks native contract nodes, and lower it to exactly the same
  trusted contracts/assertions as the existing source forms.
- Output: a deterministic lexical bridge for function `pre`/`post` and
  statement `contract_assert`, integrated ahead of Clang and lowering, with
  frozen positive/negative fixtures.
- Exact file set: `semantic_verifier/cpp26_contracts.py`;
  `semantic_verifier/frontend.py`; `semantic_verifier/lowering.py`;
  `semantic_verifier/contracts.py`; `tests/test_cpp26_contracts.py`;
  `fixtures/cpp26_contracts/**`; `docs/cpp26_contracts_bridge.md`;
  `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: bridge input is UTF-8 and compiler text remains byte/line stable;
  comments, strings, raw strings, and preprocessing text are never recognized
  as contracts. Only attribute-free contracts on an otherwise supported,
  first-and-only non-virtual function definition are admitted. A postcondition
  result binder is normalized token-wise to `result`; standard const-use
  restrictions remain enforced. `contract_assert` maps to the existing source
  assertion obligation, never to a loop invariant. Mixed standard and `cs:`
  function contracts, attributes, malformed nesting, unsupported declarations,
  or uncertain binding fail closed as unsupported. No approximation is allowed,
  and native compiler runtime evaluation policy is outside static proof.
- DoD: `pre`, `post` with/without result binding, and
  `contract_assert` generate the same canonical IR/obligations/results as
  equivalent existing forms; standard spelling verifies and violates through
  the ordinary referee with replay; compiler source preserves length/newline
  positions and reports original locations; result binding cannot capture or
  rewrite member names; comment/string/preprocessor lookalikes are inert;
  malformed, attributed, mixed, redeclared, virtual, and const-rule cases are
  explicit unsupported results; repeated text/JSON/IR bytes match; the existing
  suite and a focused bridge matrix pass.
- Depends: C3.0.

### Phase C4 — Enforcement ladder (2b) — from contract to test

#### C4.0 — Enforcement-ladder policy and expansion

- Goal: define a deterministic, fail-closed routing policy from referee status
  to static completion, defect handling, property-test fallback, runtime
  fallback, manual handling, or infrastructure repair.
- Output: a human-readable decision record, machine-readable policy matrix, and
  fully declared C4.1/C4.2 implementation stages.
- Exact file set: `docs/enforcement_ladder.md`;
  `research/enforcement_ladder_policy.json`;
  `tests/test_enforcement_ladder_policy.py`; `README.md`; `PLAN.md`;
  `PROGRESS.md`, `TODO.md`, and `guardrails/test_baseline.txt`.
- Boundaries: no source, IR, checker, report, or exit-code behavior changes in
  this stage. `verified` stops at rung 1; `violated` remains a replayed
  defect; `solver_error` remains an infrastructure failure. Only exact,
  callable contract surfaces from `unknown`/`unsupported` results may descend
  to generated enforcement. No fallback result ever promotes to `verified`.
- DoD: freeze all five status routes and eligible/ineligible capability routes;
  define stable identity/provenance for generated artifacts; define the
  no-randomness, no-approximation, no-status-promotion rules; distinguish
  generated, executed, passed, guarded, manual, defect, and infrastructure
  states; declare C4.1/C4.2 exact files/boundaries/DoD; focused and full suites
  pass.
- Depends: C3.1.

#### C4.1 — Unproven obligation to property-test skeleton

- Goal: make eligible `unknown`/`unsupported` function contracts descend one
  rung into deterministic, framework-neutral C++ property-test skeletons while
  keeping the referee status visible.
- Output: a versioned enforcement manifest, generator library/CLI, and frozen
  positive/negative property-skeleton fixtures.
- Exact file set: `semantic_verifier/enforcement_ladder.py`;
  `tools/generate_property_skeleton.py`;
  `fixtures/enforcement_ladder/property/**`;
  `tests/test_enforcement_ladder.py`; `docs/enforcement_ladder.md`;
  `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: eligible targets are otherwise-supported, non-void functions with
  fixed scalar by-value parameters, no frame contract, at least one exact
  `ensures`, and predicates renderable without approximation. Generated C++17
  accepts caller-supplied deterministic cases, filters exact `requires`, calls
  the original function once, and checks exact `ensures`. It contains no
  random generator and claims only `generated_unexecuted`. Duplicate path
  obligations collapse by semantic contract identity. `verified`,
  `violated`, and `solver_error` never generate a fallback; ineligible
  `unknown`/`unsupported` entries become explicit `manual_required`.
- DoD: strict input/status validation; content-addressed source/report/skeleton
  identities; deterministic sorted route entries; compilable C++17 skeleton
  for eligible scalar contracts; exact requires/ensures preservation and
  single function evaluation; status/reason provenance in manifest and source;
  duplicate collapse; explicit verified/defect/infrastructure/manual routes;
  relocation and repeated-byte stability; malformed/stale input fails closed;
  focused and full suites pass.
- Depends: C4.0.

#### C4.2 — Runtime guard generation and three-rung demo

- Goal: generate the last-rung runtime wrapper from the same accepted `cs:`
  contracts and demonstrate static, property, and runtime artifacts as one
  provenance chain.
- Output: runtime-wrapper library/CLI, a combined demo command, and a frozen
  source whose static report, property skeleton, and runtime guard share one
  contract identity.
- Exact file set: `semantic_verifier/enforcement_ladder.py`;
  `semantic_verifier/runtime_assertions.py`;
  `tools/generate_runtime_assertions.py`;
  `tools/enforcement_ladder_demo.py`;
  `fixtures/enforcement_ladder/runtime/**`;
  `tests/test_runtime_assertions.py`; `docs/enforcement_ladder.md`;
  `README.md`; `PROGRESS.md`, `TODO.md`, and
  `guardrails/test_baseline.txt`.
- Boundaries: runtime wrappers use the same C4.1 scalar/value/no-frame contract
  subset, evaluate each argument/function call once, check every `requires`
  before the call and every `ensures` after normal return, and invoke an
  explicit failure hook. No `invariant`/`modifies` approximation, exception
  claim, randomness, checker change, or `verified` promotion is allowed.
  Runtime guarding is recorded as `runtime_guarded`, not proof.
- DoD: deterministic content-addressed wrapper and three-rung manifest; exact
  contract identity shared by static report, property skeleton, and runtime
  wrapper; generated C++17 compiles; satisfying calls return normally and a
  violated require/ensure reaches the failure hook in child-process tests;
  no double evaluation; all statuses and skipped/manual reasons remain visible;
  repeated output/relocation is byte-stable; focused and full suites pass.
- Depends: C4.1.

*(C5 — RuleDSL bridge: deliberately PARKED. Not opened before A/B mature.)*

---

## 8. PROGRAM D — World model (fact index / SCI)

### Phase D1 — Fact extraction v0

#### D1.1 — Deterministic fact schema

- Goal: define an independent, versioned world-model contract for source
  symbols, definitions, uses, direct calls, mutations, and derived purity.
- Output: immutable Python value objects, a strict loader/validator, canonical
  JSON serialization, a machine-readable JSON Schema, and a field reference.
- Exact file set: semantic_verifier/facts.py;
  semantic_verifier/fact_schema/v1/index.schema.json;
  tests/test_fact_schema.py; docs/fact_schema.md; README.md; PLAN.md;
  PROGRESS.md, TODO.md, and guardrails/test_baseline.txt.
- Boundaries: codeskeptic.fact-index/v1 is independent from verification-report
  schema versions. IDs are content-addressed from canonical owned fields; file
  separators and ordering are normalized; locations are one-based. Symbol,
  definition/use, call, mutation, purity, and limitation kinds are closed
  enums. References must resolve inside the index. Purity is derived tri-state
  metadata, never a proof claim. Unknown fields, duplicate identities, dangling
  references, malformed hashes/locations, and inconsistent ownership fail
  closed. This stage performs no Clang extraction, query, caching, or proof.
- DoD: strict JSON Schema and loader agree; immutable models round-trip;
  differently ordered valid inputs serialize byte-identically; semantic
  changes alter the index identity; invalid/unknown/dangling/duplicate cases
  reject explicitly; focused and full suites pass.
- Depends: C4.2.

#### D1.2 — Clang fact extraction v0

- Goal: populate the D1.1 schema from the existing Clang JSON-AST frontend.
- Output: a deterministic extractor for main-file C++17 declarations and
  expressions, with explicit coverage limitations.
- Exact file set: semantic_verifier/fact_extractor.py;
  tests/test_fact_extractor.py; docs/fact_schema.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: admit named functions, parameters, locals, globals, records and
  fields; definitions, reads, writes, direct calls, and mutation targets.
  Exclude compiler/system declarations and normalize frontend identities out of
  public artifacts. Overloads and scopes must not collide. Indirect/virtual
  dispatch, unresolved callees, macros without stable main-file locations, and
  unsupported AST forms are explicit limitations, never silently inferred.
  Purity is derived only when the admitted call/mutation surface is complete;
  otherwise it is unknown. No verification status or proof trust is created.
- DoD: representative main-file sources extract exact symbols, def/use edges,
  direct call graph, mutation sets, and purity; overload/scope identities are
  stable; unsupported constructs are visible; repeated extraction and fixed
  display-path relocation are byte-identical; focused and full suites pass.
- Depends: D1.1.

#### D1.3 — Fact determinism corpus

- Goal: freeze extractor behavior as reproducible evidence.
- Output: a small C++ corpus, golden fact-index JSON, a regeneration/check tool,
  and determinism/coverage tests.
- Exact file set: tools/regenerate_fact_fixtures.py; fixtures/facts/**;
  tests/test_fact_determinism.py; docs/fact_schema.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: the corpus covers scopes/overloads, call chains, local/global
  mutation, and at least one explicit unsupported limitation. Golden artifacts
  contain no checkout root, compiler path, clock, duration, random value, or
  unstable Clang node ID. Regeneration never changes verification fixtures.
- DoD: generate and check modes agree; every source has one declared golden;
  repeated extraction and relocated checkout inputs are byte-identical under
  the frozen display path; all edges resolve and arrays are canonically sorted;
  focused and full suites pass.
- Depends: D1.2.

### Phase D2 — Query interface

#### D2.1 — Deterministic world-model queries and CLI

- Goal: expose exact, deterministic navigation over one validated fact index.
- Output: a pure query library plus a CLI for who-calls, who-mutates, and
  undirected symbol neighborhood queries.
- Exact file set: semantic_verifier/fact_queries.py; tools/query_facts.py;
  tests/test_fact_queries.py; docs/fact_queries.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: load only codeskeptic.fact-index/v1 through the strict D1 loader.
  Selectors are exact content IDs or qualified names; ambiguous names fail with
  sorted typed candidates. who-calls accepts functions, who-mutates accepts
  variable/parameter/field storage, and neighborhood uses only owned symbol,
  call, definition, use, and mutation edges. Queries never infer missing edges,
  resolve D1 limitations, join translation units heuristically, or create proof
  trust. JSON/text output and errors are deterministic; empty exact results are
  successful.
- DoD: exact and ambiguous selector tests; caller and mutator answers with
  source sites; k=0/1/2 neighborhood coverage and depth validation; canonical
  result schemas/order/bytes; CLI JSON/text and exit-code tests over the frozen
  corpus; focused and full suites pass.
- Depends: D1.3.

#### D2.2 — MCP fact-query endpoint

- Goal: make the D2.1 map available to agents through a documented MCP tool.
- Output: a dependency-free JSON-RPC stdio MCP server and thin launcher over
  the exact D2.1 query API.
- Exact file set: semantic_verifier/fact_mcp.py;
  tools/fact_mcp_server.py; research/mcp_fact_query_evidence.json;
  tests/test_fact_mcp.py; docs/fact_queries.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: freeze official MCP protocol version 2026-07-28 and the required
  per-request metadata, server/discover, tools/list, tools/call, resultType,
  and cache behavior from primary specification evidence. Do not implement the
  removed initialize/notifications/initialized handshake. The server reads one
  caller-supplied,
  strictly validated fact index and exposes one read-only query tool. It uses
  newline-delimited JSON-RPC on stdio, emits no logs on stdout, performs no
  network/file mutation, and never invokes a model or referee. Unknown methods,
  malformed parameters, ambiguous symbols, and invalid depth return protocol
  errors or isError tool results without fabricated facts.
- DoD: dated official evidence artifact; subprocess discovery and tool listing;
  all three queries through tools/call; deterministic repeated responses;
  notification/no-response behavior; malformed JSON/request/params and query
  error coverage; stderr/stdout separation; clean EOF shutdown; focused and
  full suites pass.
- Depends: D2.1.

#### D2.3 — Compact fact-based context packs

- Goal: emit a useful symbol-centered AI context bundle within a hard
  conservative 2K-token upper bound.
- Output: deterministic relevance-ranked context-pack library/CLI and frozen
  golden artifact.
- Exact file set: semantic_verifier/fact_context.py;
  tools/generate_fact_context.py; fixtures/fact_context/**;
  tests/test_fact_context.py; docs/fact_queries.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: pack only facts present in one validated index. Include root
  identity, purity/limitations, and nearest ownership/call/mutation/use facts
  before farther neighborhood data. No source-body reconstruction, semantic
  guess, model call, proof promotion, clock, or randomness. Canonical output is
  ASCII JSON; a maximum UTF-8 byte count equal to the requested token budget is
  a conservative token upper bound. Default and maximum budget are 2000.
  Truncation is deterministic and reports omitted counts; the root/provenance
  envelope must fit or generation fails explicitly.
- DoD: frozen <=2000-byte golden; exact relevance/order and omission accounting;
  minimum/invalid budget behavior; repeated/relocated byte stability; CLI
  generate/check modes; no unstable paths or inferred facts; focused and full
  suites pass.
- Depends: D2.2.

### Phase D3 — Architectural rules (1b)

#### D3.0 — Expansion

- Goal: replace the architectural-rule heading with bounded policy and
  enforcement stages before accepting any rule syntax.
- Output: detailed D3.1–D3.2 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Boundaries: direct, resolved D1 call facts are the only enforceable
  dependency edges. Missing classification and every fact-index limitation
  remain explicit unknowns; architecture compliance is not proof.
- DoD: D3.1–D3.2 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  the full suite remains green.
- Depends: D2.3.

#### D3.1 — Strict architectural dependency policy

- Goal: define a deterministic, reviewable layer classifier and complete
  allowed/forbidden dependency matrix without implementation defaults.
- Output: strict content-addressed codeskeptic.architecture-policy/v1 value
  objects/loader, validation CLI, frozen policy fixture, and reference docs.
- Exact file set: semantic_verifier/architecture_policy.py;
  tools/validate_architecture_policy.py; fixtures/architecture/policy.json;
  tests/test_architecture_policy.py; docs/architecture_rules.md; README.md;
  PROGRESS.md, TODO.md, and guardrails/test_baseline.txt.
- Boundaries: layers use non-empty exact qualified-name, qualified-name-prefix,
  or normalized source-prefix selectors. Duplicate layers/selectors, unknown
  fields, unknown decisions, missing/duplicate ordered layer pairs, and stale
  policy IDs fail strict loading. Every ordered layer pair, including self,
  has exactly one allow or forbid decision. A symbol matching zero or multiple
  layers is preserved as an explicit classification outcome for D3.2; selector
  order never breaks ties. No glob/regex, source inference, fact extraction,
  model call, or proof/referee behavior belongs here.
- DoD: valid canonical round-trip and content ID; shuffled-input byte stability;
  exact/prefix/source selector coverage; complete matrix lookup; all strict
  schema/identity/duplicate/missing-pair negatives; validation CLI success and
  input-error exit; focused and full suites pass.
- Depends: D3.0.

#### D3.2 — Fact-based enforcement and deterministic SARIF

- Goal: decide every indexed direct call against D3.1 and expose actionable,
  source-located violations without treating an incomplete graph as clean.
- Output: codeskeptic.architecture-result/v1 enforcer, text/JSON/SARIF CLI,
  frozen result and SARIF goldens over the D1 world corpus.
- Exact file set: semantic_verifier/architecture.py;
  tools/check_architecture.py; fixtures/architecture/**;
  tests/test_architecture.py; docs/architecture_rules.md; README.md;
  PROGRESS.md, TODO.md, and guardrails/test_baseline.txt.
- Boundaries: consume one strictly validated fact index and one strict policy.
  Resolved direct call facts are checked exactly once. An allow rule is clean;
  a forbid rule records caller/callee symbols, layers, exact call ID/site, and
  policy decision. Zero/multiple endpoint classifications and every D1
  limitation produce sorted unknown findings, never an allowed edge or proof.
  Aggregate precedence is unknown, then violation, then clean; CLI exit codes
  are 2, 1, and 0 respectively, with 3 for input/checker errors. SARIF 2.1.0
  uses stable rule IDs, normalized artifact URIs, exact one-based regions, and
  no clock, absolute path, run timing, or model-generated content.
- DoD: allowed, forbidden, self-layer, unclassified, ambiguous, and limitation
  cases; violation/unknown aggregate precedence and exit codes; exact evidence
  and deterministic ordering; canonical result and SARIF goldens; repeated and
  relocated byte stability; malformed input failure; focused and full suites
  pass.
- Depends: D3.1.

### Phase D4 — Incrementality (1d)

#### D4.0 — Expansion

- Goal: replace the incrementality heading with a bounded cache/extraction
  contract before persisting any fact index.
- Output: the detailed D4.1 contract in PLAN.md plus PROGRESS.md and TODO.md.
- Boundaries: incrementality is an execution optimization only. Cached facts
  retain their original derived trust and are never joined, repaired, or
  promoted by cache reuse.
- DoD: D4.1 declares Goal/Output/exact file set/Boundaries/DoD/Depends; the
  full suite remains green.
- Depends: D3.2.

#### D4.1 — Content-addressed translation-unit extraction cache

- Goal: invalidate fact extraction by source content and re-extract exactly
  the changed translation units in a declared workspace.
- Output: strict codeskeptic.translation-units/v1 input and
  codeskeptic.fact-cache-manifest/v1 state, a dependency-free incremental
  extraction library/CLI, frozen multi-TU fixture, and reference docs.
- Exact file set: semantic_verifier/fact_incremental.py;
  tools/extract_facts_incremental.py; fixtures/fact_incremental/**;
  tests/test_fact_incremental.py; docs/fact_incrementality.md; README.md;
  PLAN.md, PROGRESS.md, TODO.md, and guardrails/test_baseline.txt.
- Boundaries: each TU declares a normalized workspace-relative source path
  and stable display path. UTF-8 source bytes, display path, fact schema, and
  extractor contract form its cache key. A hit is reused only after strict
  manifest, key, source hash, display path, and FactIndex identity validation;
  corrupt or mismatched cache state fails closed. A miss invokes the existing
  D1 extractor once and writes canonical ASCII JSON atomically. The current
  manifest contains no absolute path, clock, duration, random value, or stale
  entry; sorted current outputs remain separate per TU and are never
  heuristically merged. No include/dependency scanning, compiler-command
  database, parallel execution, garbage collection, model call, or proof
  promotion belongs here.
- DoD: cold run extracts every TU; identical warm run extracts none and reuses
  byte-identical indexes; one edited source re-extracts exactly that TU; added
  and removed TU accounting; relocated workspace byte stability; shuffled
  declaration stability; duplicate/path-escape/invalid-UTF-8/schema/cache
  corruption negatives; extractor failure leaves the prior current manifest
  intact; CLI exit and check-mode coverage; focused and full suites pass.
- Depends: D4.0.

### Phase D5 — Verified facts

#### D5.0 — Expansion

- Goal: replace the trust-promotion placeholder with bounded schema and
  referee-promotion stages before any derived fact can gain proof trust.
- Output: detailed D5.1-D5.2 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Boundaries: trust is a separate immutable overlay on D1 facts. Promotion is
  monotone only from derived pure to proved pure and never changes a fact
  value, hides a limitation, or treats an empty checker result as proof.
- DoD: D5.1-D5.2 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  the full suite remains green.
- Depends: D4.1.

#### D5.1 — Strict fact-trust overlay schema

- Goal: represent derived and proved trust without changing or duplicating the
  D1 fact index.
- Output: codeskeptic.fact-trust/v1 immutable value objects/strict loader,
  canonical content/claim identities, JSON Schema, and reference docs.
- Exact file set: semantic_verifier/fact_trust.py;
  semantic_verifier/fact_trust_schema/v1/index.schema.json;
  tests/test_fact_trust.py; docs/fact_trust.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: an overlay names one validated fact-index identity and contains
  exactly one sorted claim for every D1 purity row. Claim function/value must
  match that row. Trust is derived or proved; impure and unknown values can
  only be derived. A proved pure claim requires the fixed
  empty-frame-full-vc/v1 evidence shape: source hash, verification artifact
  hash/schema, recognized referee ID, non-empty unique obligation IDs, exact
  human-authored empty-frame location, and sorted proved direct-callee IDs.
  Derived claims carry no proof evidence. Claim and overlay identities cover
  every field. Unknown fields, duplicate JSON keys/items, stale identities,
  non-finite values, dangling/missing claims, and evidence on derived facts
  fail strict loading. The overlay never mutates D1 bytes and structural
  validity alone does not independently establish that evidence was produced.
- DoD: canonical derived/proved examples and JSON Schema parity; shuffled-input
  byte stability; exact D1 cross-validation; all trust/value/evidence/identity/
  duplicate/unknown/dangling/missing negatives; original fact-index bytes stay
  unchanged; focused and full suites pass.
- Depends: D5.0.

#### D5.2 — Referee-backed pure-claim promotion

- Goal: promote only the admitted, fully checked subset of derived pure claims
  and emit replayable deterministic evidence.
- Output: one-parse fact/trust verification pipeline and CLI plus frozen source,
  fact-index, verification-report, and trust-overlay goldens.
- Exact file set: semantic_verifier/fact_trust_promotion.py;
  tools/promote_fact_trust.py; fixtures/fact_trust/**;
  tests/test_fact_trust_promotion.py; docs/fact_trust.md; README.md;
  PROGRESS.md, TODO.md, and guardrails/test_baseline.txt.
- Boundaries: parse exact UTF-8 source/display bytes once, then derive both D1
  facts and Semantic IR from that FrontendUnit. Promotion requires a D1 pure
  function definition, one exact IR match, an explicit non-machine-proposed
  empty modifies frame, no module or contextual fact/IR limitation, a
  non-empty complete function obligation/result set whose every status is
  verified, and every indexed direct callee already proved in the same
  fixed-point run. Evidence cites the canonical full verification report and
  exact obligation IDs. Missing/ambiguous matches, absent/non-empty/machine
  frames, zero obligations, external/unproved callees, recursion, violated,
  unknown, unsupported, or solver-error results remain derived. No model call,
  fact rewrite, synthetic true obligation, solver-status override, cross-TU
  inference, or proof from derived callees is allowed.
- DoD: proved leaf and proved call chain; all boundary negatives above;
  impure/unknown values never promote; exact fact/report/evidence linkage;
  canonical goldens and schema validation; repeated and relocated byte
  stability under a frozen display path; CLI backend/error/exit coverage;
  focused and full suites pass.
- Depends: D5.1.
---

## 9. PROGRAM E — AI loop

### Phase E1 — Repair loop (M5)

#### E1.0 — Expansion

- Goal: replace the three repair-loop bullets with bounded bundle, loop, and
  telemetry contracts before a model can propose any patch.
- Output: detailed E1.1-E1.3 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Boundaries: the proposer is untrusted and never decides success. The existing
  deterministic verifier/referee accepts or rejects every candidate; source
  files are not mutated by the reference loop.
- DoD: E1.1-E1.3 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  the full suite remains green.
- Depends: D5.2.

#### E1.1 — Replay-attested repair bundle

- Goal: package one concrete violated obligation into a strict, useful,
  machine-readable repair context without adding model interpretation.
- Output: codeskeptic.repair-bundle/v1 immutable model/strict loader and JSON
  Schema, deterministic builder/CLI, frozen violated golden, and reference docs.
- Exact file set: semantic_verifier/repair_bundle.py;
  semantic_verifier/repair_bundle_schema/v1/index.schema.json;
  tools/generate_repair_bundle.py; fixtures/repair_bundle/**;
  tests/test_repair_bundle.py; docs/repair_loop.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: input is exact UTF-8 source/display content and one complete
  VerificationReport. Select one validity obligation whose unique result is
  violated with a concrete counterexample. Recheck that original serialized
  obligation through the same admitted built-in referee and require another
  violated result before bundling; unsupported, unknown, solver error,
  non-violated, missing/duplicate result, changed counterexample, or checker
  mismatch fails closed. The bundle contains source/report hashes, canonical
  obligation/result, bounded line-numbered source context around its exact
  location, and every human/machine provenance-preserving contract attached to
  that function. IDs cover every field. It contains no prompt, patch, inferred
  intent, absolute path, time, randomness, or proof claim.
- DoD: affine replayed violation golden and exact evidence linkage; optional Z3
  referee path when installed; source-slice boundary cases; contract provenance
  and canonical ordering; shuffled-input stability; duplicate/unknown/schema/
  identity/source/report/result/replay negatives; relocated byte stability;
  CLI backend/check/error exits; focused and full suites pass.
- Depends: E1.0.

#### E1.2 — Bounded untrusted-proposer repair harness

- Goal: execute bundle to proposal to patch to re-verification for at most N
  iterations while leaving every acceptance decision to the referee.
- Output: codeskeptic.repair-loop/v1 proposal/edit/log value objects, strict
  scripted proposer seam, deterministic line-edit applicator, harness/CLI,
  frozen successful and exhausted logs, and reference docs.
- Exact file set: semantic_verifier/repair_loop.py;
  tools/run_repair_loop.py; fixtures/repair_loop/**;
  tests/test_repair_loop.py; docs/repair_loop.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: PatchProposer is an abstract untrusted seam. The offline CLI reads
  predeclared strict proposals only; no network/model dependency is added.
  Each proposal names the current source hash and one non-overlapping,
  line-bounded replacement. Stale hashes, invalid ranges/UTF-8, no-op edits,
  proposal reuse, or proposer exceptions are logged as rejected and never
  mutate disk. After each valid edit, rebuild the target bundle/report and run
  the admitted referee. Success requires a non-empty complete target-function
  result set with every result verified and no module failure; the model never
  reports success. Stop at first success or exactly N attempts. The canonical
  log records every proposal, candidate hash, verifier artifact hash, statuses,
  diagnostic, and final accepted source/edit; no clock or random value enters
  decisions or identities.
- DoD: first-shot, later-shot, and N-exhausted runs; violated-to-verified repair;
  stale/range/overlap/no-op/proposer-error/referee unknown/unsupported/error
  negatives; exact N=1/max validation and early stop; every attempt logged and
  deterministic; original file unchanged; relocated bytes; CLI check/error
  exits; focused and full suites pass.
- Depends: E1.1.

#### E1.3 — Append-only repair metrics telemetry

- Goal: record iteration count, success, and elapsed time per obligation without
  allowing timing to affect proposals, verification, success, IDs, or ordering.
- Output: codeskeptic.repair-metrics/v1 strict metric row and append-only JSONL
  ledger, injected monotonic timing boundary, summary CLI, fixtures, and docs.
- Exact file set: semantic_verifier/repair_metrics.py;
  tools/record_repair_metrics.py; fixtures/repair_metrics/**;
  tests/test_repair_metrics.py; docs/repair_loop.md; README.md; PROGRESS.md,
  TODO.md, and guardrails/test_baseline.txt.
- Boundaries: the harness receives only start/stop duration values after its
  deterministic result exists. Production CLI measures monotonic elapsed
  nanoseconds at the orchestration boundary; tests/goldens inject exact integer
  durations. Rows cite bundle/loop IDs and record obligation, iterations,
  success/final status, and non-negative elapsed_ns. Timing never selects a
  candidate or changes a loop artifact. Ledger writes append one canonical line,
  preserve prior bytes, reject duplicate run IDs and malformed prior rows, and
  use no wall-clock timestamp, random value, model call, or overwrite.
- DoD: success/failure rows and exact aggregation; injected-duration stability;
  monotonic boundary called exactly twice and only outside the loop; append and
  prior-byte preservation; duplicate/malformed/negative/bool/unknown-field
  negatives; shuffled load stability; CLI append/summary/error exits; focused
  and full suites pass.
- Depends: E1.2.

### Phase E2 — The "consciousness experiment" (measurable hypothesis)

#### E2.0 — Bounded consciousness-experiment expansion

- Goal: replace the three coarse experiment bullets with a reproducible paired
  protocol whose evidence cannot be mistaken for an AI or consciousness claim.
- Output: detailed E2.1-E2.3 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Freeze twenty seeded cases, two isolated context
  arms, a four-proposal cap, referee-only outcomes, censored failure scoring,
  exact paired aggregation, immutable proposer provenance, and an explicit
  evidence-scope label. Do not create corpus data, run trials, or claim an
  outcome in this stage. External/model-produced proposals remain untrusted
  frozen inputs; the reference implementation adds no network/model package.
- DoD: E2.1-E2.3 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  arm contamination, survivor bias, missing/duplicate trials, result tampering,
  and overclaiming are fail-closed; the immediately preceding full suite is
  green; ledger/TODO updated; stage commit succeeds.
- Depends: E1.3.

#### E2.1 — Seeded-bug experiment corpus

- Goal: freeze twenty individually addressable supported-subset functions with
  known concrete violations and independently checkable repaired oracles.
- Output: codeskeptic.experiment-corpus/v1 strict content-addressed manifest;
  twenty standalone C++ sources; compiler/test-only diagnostics; hidden repair
  oracle records; deterministic corpus checker; fixtures, tests, and docs.
- Exact file set: semantic_verifier/experiment_corpus.py;
  tools/check_experiment_corpus.py; benchmarks/experiment_e2/corpus/**;
  tests/test_experiment_corpus.py; docs/experiment_e2.md; README.md; PROGRESS.md;
  TODO.md; guardrails/test_baseline.txt.
- Boundaries: exactly twenty unique case/function IDs and display paths. Every
  original compiles and yields exactly one replayable violated validity
  obligation with a concrete counterexample under the admitted affine referee;
  every oracle is one non-contract line edit and yields a non-empty all-verified
  target with unchanged human contracts. A compiler/test context preserves line
  numbers but redacts every contract and contains only source plus one frozen
  black-box failure diagnostic. Oracle edits and semantic evidence are never in
  that context. The manifest cites all source/context/oracle hashes and rejects
  missing, extra, relocated-escape, duplicate, stale, unknown, or non-canonical
  data. No wall clock, randomness, model output, or package dependency.
- DoD: corpus count exactly 20; all original violation/replay and repaired
  verification checks; contract-redaction and oracle-isolation assertions;
  unique identities; stale/hash/path/schema/unknown-field/duplicate/extra-file
  negatives; shuffled manifest load stability; relocated corpus bytes and
  checker output; CLI success/error exits; focused and full suites pass.
- Depends: E2.0, E1.1.

#### E2.2 — Paired two-arm repair trials

- Goal: execute the same twenty cases under a fixed four-proposal protocol for
  (a) compiler/test-only context and (b) the exact E1.1 semantic repair bundle.
- Output: codeskeptic.experiment-context/v1 arm packages,
  codeskeptic.experiment-trials/v1 strict forty-row result artifact, frozen
  arm-specific proposal scripts with immutable proposer/evidence provenance,
  deterministic runner, fixtures, tests, and docs.
- Exact file set: semantic_verifier/experiment_e2.py;
  tools/run_experiment_e2.py; benchmarks/experiment_e2/contexts/**;
  benchmarks/experiment_e2/proposals/**;
  benchmarks/experiment_e2/results/trials.json; tests/test_experiment_e2.py;
  docs/experiment_e2.md; README.md; PROGRESS.md; TODO.md;
  guardrails/test_baseline.txt.
- Boundaries: arm A packages only the contract-redacted source, source target
  hash, and frozen compiler/test diagnostic; obligation, contract, IR, bundle,
  counterexample, oracle, and arm-B bytes are forbidden. Arm B packages exactly
  one replay-attested E1.1 bundle and no oracle. Both use the same original,
  target, affine referee, PatchProposer seam, RepairHarness, and cap of four.
  Proposal scripts are recorded untrusted inputs, never proof; each cites its
  exact context and proposer class. The runner produces exactly one row per
  case/arm, records loop identity, verified/exhausted outcome, attempts, and a
  censored score of iterations on success or cap+1 on exhaustion. Only replayed
  all-verified loops count as success. No timing, randomization, network/model
  call, hidden retry, or hand-edited result row.
- DoD: 20 paired/40 total trials; exact corpus/context/proposal/loop links; both
  success and exhaustion paths; same cap/referee/source enforcement; arm-A
  forbidden-evidence and cross-arm contamination negatives; stale/reused/
  missing/duplicate/tampered/mixed-provenance negatives; shuffled load and run
  stability; source unchanged; repeated and relocated result bytes; CLI
  generate/check/error exits; focused and full suites pass.
- Depends: E2.1, E1.2.

#### E2.3 — Honest paired experiment report

- Goal: evaluate the predeclared hypothesis that arm B's median censored repair
  score is at least 40 percent lower than arm A's, without dropping failures or
  extending the evidence beyond the recorded proposer class.
- Output: codeskeptic.experiment-report/v1 strict report and analyzer CLI;
  frozen machine-readable report; complete human report in
  docs/experiment_e2.md; tests, README, ledger, and handoff.
- Exact file set: semantic_verifier/experiment_report.py;
  tools/report_experiment_e2.py; benchmarks/experiment_e2/results/report.json;
  tests/test_experiment_report.py; docs/experiment_e2.md; README.md; PROGRESS.md;
  TODO.md; guardrails/test_baseline.txt.
- Boundaries: primary population is all twenty predeclared paired cases. Each
  exhausted arm retains score five; no survivor filtering. Compute exact medians
  from sorted integer scores and improvement as a reduced rational before the
  threshold comparison. Report per-arm success/exhaustion counts, score vectors,
  medians, paired deltas, corpus/trial IDs, proposal provenance/evidence scope,
  and the pass/fail outcome. State explicitly that a scripted or recorded pilot
  cannot establish consciousness, general model behavior, or causality. No
  post-hoc threshold, excluded case, floating-point decision, timing claim, or
  prose-only arithmetic.
- DoD: exact independent recomputation from all 40 rows; frozen threshold and
  honest outcome; missing/duplicate/unpaired/corpus-mismatch/result-tamper/
  wrong-score/wrong-threshold/unknown-field negatives; order-independent bytes;
  CLI generate/check/error exits; documented limitations and raw traceability;
  focused and full suites pass.
- Depends: E2.2.

#### E2.4 — Batched corpus frontend calibration

- Goal: remove repeated per-case frontend pressure exposed by the full-suite
  order while preserving all twenty semantic violation, replay, and repair
  decisions.
- Output: one deterministic combined-original verification, exact independent
  replay of each target obligation, and one combined-repaired verification.
- Exact file set: semantic_verifier/experiment_corpus.py; PLAN.md; PROGRESS.md;
  TODO.md.
- Boundaries: verification infrastructure only. Keep all corpus files, hashes,
  contexts, oracle edits, checker, outcomes, and checker JSON unchanged. Join
  the twenty standalone translation units in sorted manifest order without
  rewriting them; identify evidence by exact function name; replay every
  obligation directly with the same affine referee; verify every repaired
  target. Add no cache, retry, approximation, timing, or skipped case.
- DoD: corpus checker still reports 20/20 isolated concrete violations, 20/20
  exact independent replays, and 20/20 repaired targets; focused 14/14 and full
  563/563 suites pass without the prior order-dependent frontend failure;
  ledger/TODO updated; stage commit succeeds.
- Depends: E2.1.

### Phase E3 — Assumption declaration protocol (2d)

#### E3.0 — Bounded assumption-protocol expansion

- Goal: replace the coarse assumption bullets with an immutable declaration and
  linked resolution protocol that distinguishes checkable evidence from honest
  uncheckable claims.
- Output: detailed E3.1-E3.2 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Freeze declaration-before-implementation ordering,
  content-addressed input snapshots, one resolution per assumption, exact
  contract/test evidence hashes and anchors, and explicit uncheckable reasons.
  A manifest or evidence link is never proof that a contract or test passed.
  Do not create protocol artifacts or claim pilot results in this stage.
- DoD: E3.1-E3.2 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  missing assumptions, post-hoc declarations, stale evidence, path escape,
  duplicate resolution, and uncheckable-to-verified promotion fail closed; the
  immediately preceding full suite is green; ledger/TODO updated; stage commit
  succeeds.
- Depends: E2.3.

#### E3.1 — Immutable assumption manifest and resolution overlay

- Goal: let an agent declare its concrete assumptions against an exact input
  snapshot before implementation, then resolve every declaration to a contract,
  test, or explicit uncheckable reason without rewriting history.
- Output: codeskeptic.assumption-manifest/v1 declaration and
  codeskeptic.assumption-resolution/v1 overlay models, strict loaders, JSON
  Schemas, repository evidence validator/summary CLI, fixtures, tests, and docs.
- Exact file set: semantic_verifier/assumption_manifest.py;
  semantic_verifier/assumption_manifest_schema/v1/**;
  tools/check_assumption_manifest.py; fixtures/assumption_manifest/**;
  tests/test_assumption_manifest.py; docs/assumption_protocol.md; README.md;
  PROGRESS.md; TODO.md; guardrails/test_baseline.txt.
- Boundaries: declarations are immutable content-addressed values with subject,
  sorted non-empty UTF-8 input snapshot paths/hashes, and sorted unique
  assumptions carrying ID, statement, scope, risk, and intended disposition of
  contract, test, or uncheckable. Resolutions link one exact manifest and contain
  exactly one row per declared ID. Contract/test rows require at least one
  canonical repository-relative evidence path, exact normalized UTF-8 hash, and
  non-empty anchor present in that artifact; their reason is null. Uncheckable
  rows require no evidence and a concrete non-empty reason. They remain
  uncheckable in every summary and never count as verified. Manifest creation
  never reads or predicts later evidence. Linked resolution validation may read
  only declared snapshot and cited evidence paths under the supplied root. No
  timestamp, randomness, model call, mutable status, path escape, symlink
  escape, inferred success, or package dependency.
- DoD: frozen contract/test/uncheckable fixture; declaration identity unchanged
  by resolution; exact snapshot/evidence/anchor checks; complete one-to-one
  coverage and deterministic summary; missing/extra/duplicate/unknown/stale/
  wrong-disposition/bool/noncanonical-path/path/symlink/UTF-8/hash/anchor and
  uncheckable-evidence negatives; shuffled JSON key and resolution-row load
  stability; relocation; matching JSON Schemas parse; CLI success/error exits;
  focused and full suites pass.
- Depends: E3.0.

#### E3.2 — Repository-local declaration-before-code pilot

- Goal: exercise E3.1 on a real bounded repository task while preserving proof
  that assumptions were frozen before their resolving evidence was authored.
- Output: a committed declaration sub-gate, later linked resolution overlay,
  at least five project assumptions spanning semantic evidence, documentation,
  and process boundaries, repository-local evidence tests, deterministic pilot
  summary/check command, and an honest report.
- Exact file set: pilots/assumption_protocol/**;
  tools/run_assumption_pilot.py; tests/test_assumption_pilot.py;
  docs/assumption_protocol.md; README.md; PROGRESS.md; TODO.md;
  guardrails/test_baseline.txt.
- Boundaries: first commit only the declaration manifest and snapshot inputs,
  with a PARTIAL ledger entry naming the declaration ID; resolving test/tool/
  overlay files must not exist in that commit. The closure commit must link that
  unchanged declaration. Use at least five unique assumptions, resolve every
  checkable claim to an exact test or contract artifact, and retain at least one
  genuinely uncheckable claim with a bounded reason. The pilot checker validates
  evidence hashes/anchors and runs the declared repository test command, but the
  manifest itself never claims execution success. Existing evidence may be
  cited only if it is part of the declaration snapshot. No rewritten manifest,
  post-hoc omitted failure, external service, model call, clock, random value,
  or uncheckable promotion.
- DoD: declaration commit precedes closure commit; declaration bytes/ID remain
  exact; >=5 complete resolutions with >=1 honest uncheckable; every contract/
  test evidence hash and anchor validates; declared test command passes; stale
  declaration/evidence, missing resolution, false uncheckable evidence, and
  path escape fail; repeated/relocated summary bytes; CLI success/error exits;
  focused and full suites pass; report states what the pilot cannot establish.
- Depends: E3.1.

#### E3.3 — Historical pilot snapshot replay (inserted during E4.0)

- Goal: keep the immutable E3.2 declaration reproducible after declared live
  inputs such as PLAN.md legitimately evolve in later stages.
- Output: a repository-local byte-exact archive of the declaration snapshot and
  current cited evidence, plus explicit split validation/execution roots in the
  pilot CLI and tests.
- Exact file set: PLAN.md; pilots/assumption_protocol/**;
  tools/run_assumption_pilot.py; tests/test_assumption_pilot.py; README.md;
  PROGRESS.md; TODO.md; guardrails/test_baseline.txt.
- Boundaries: the E3.2 manifest bytes and identity remain unchanged. Archive
  exactly the five declared snapshot paths at declaration commit ad3667d and
  the exact cited evidence path under canonical repository-relative names. The
  validation root is the immutable archive; the execution root is the live
  repository running the declared test command. Neither root may be inferred
  from mutable process state. Missing, extra, stale, symlinked, or escaped
  archive content fails closed. No git command at validation time, rewritten
  declaration, weakened snapshot check, network call, clock, randomness, or
  promotion of the uncheckable claim.
- DoD: archived declaration paths match every manifest hash and the declaration
  commit bytes; archived evidence matches the linked resolution hash/anchor;
  live PLAN.md may evolve without invalidating historical validation; changing
  any archived snapshot/evidence byte fails; relocation and repeated summary
  bytes hold; CLI requires explicit validation and execution roots; focused and
  full suites pass; E4.0 resumes only after this corrective commit.
- Depends: E3.2.
### Phase E4 — Referee-guided search (5a)

#### E4.0 — Bounded referee-guided search expansion

- Goal: replace the coarse Best-of-N bullet with a frozen candidate/evaluation
  contract and a non-model calibration measurement.
- Output: detailed E4.1 contract in PLAN.md plus PROGRESS.md and TODO.md.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Predeclare the existing twenty-case E2 corpus,
  N=4, one original-source candidate batch per case, rank-1 single-shot arm,
  exhaustive Best-of-4 arm, lowest-rank verified selector, and an exact absolute
  success-rate uplift threshold of 2/5. Every one of the eighty candidates must
  be independently checked from the same original source; no early stop,
  sequential mutation, candidate-to-candidate state, timing, randomness, model
  call, or proposer claim may affect selection. Candidate evidence is an
  oracle-seeded recorded scripted proxy and cannot measure model behavior.
- DoD: E4.1 declares Goal/Output/exact file set/Boundaries/DoD/Depends; incomplete
  evaluation, early stopping, stale linkage, contract edits, status promotion,
  false selection, arithmetic drift, and model-evidence promotion fail closed;
  the immediately preceding full suite is green; ledger/TODO updated; stage
  commit succeeds.
- Depends: E3.2.

#### E4.1 — Exhaustive Best-of-N referee search calibration

- Goal: verify every untrusted patch in a fixed N-candidate set, select only a
  referee-verified candidate, and measure exact success-rate uplift over the
  identical rank-1 single-shot candidate.
- Output: content-addressed codeskeptic.referee-search-candidates/v1 and
  codeskeptic.referee-search-report/v1 artifacts, strict loaders/evaluator,
  structural schemas, frozen twenty-case/four-candidate calibration, CLI,
  tests, and an honest report.
- Exact file set: semantic_verifier/referee_search.py;
  semantic_verifier/referee_search_schema/v1/**; tools/run_referee_search.py;
  benchmarks/referee_search/**; tests/test_referee_search.py;
  docs/referee_guided_search.md; README.md; PROGRESS.md; TODO.md;
  guardrails/test_baseline.txt.
- Boundaries: the candidate artifact links the exact E2 corpus identity and has
  exactly twenty sorted case rows, each with ranks 1..4 and four distinct
  codeskeptic.patch-proposal/v1 values based on that case's unchanged original
  source hash. Its provenance is recorded-oracle-seeded-scripted-proxy. The
  evaluator rejects contract-line edits, no-ops, stale sources, duplicate ranks
  or identities, and any cross-case link. It applies every candidate
  independently to the original source and runs the ordinary affine referee for
  all eighty candidates even when an earlier rank verifies. Unknown,
  unsupported, violated, rejected, or checker error never becomes eligible.
  The deterministic selector chooses the lowest-rank verified candidate or none;
  rank 1 is the exact single-shot comparator. The report retains every
  per-candidate status/evidence identity, exact integer counts and reduced
  rational rates, and passes only when the absolute Best-of-4 minus single-shot
  success-rate uplift is at least 2/5. No clock, random value, network/model
  call, retry, skipped case, early stop, sequential candidate state, floating
  point, or claim about model/consciousness/general behavior/causality.
- DoD: frozen 20x4 candidate artifact; exactly eighty complete independent
  evaluations in case/rank order; post-success ranks demonstrably evaluated;
  selected proposal always lowest-rank verified and none otherwise; rank-1
  comparator identity exact; exact reduced-rate/uplift/threshold arithmetic;
  repeated and relocated generation/check bytes; strict schemas parse; missing,
  extra, duplicate, reordered, stale corpus/source/proposal/report, contract
  edit, no-op, early-stop, promoted status, false selection, arithmetic/outcome,
  malformed JSON/UTF-8, and CLI error negatives; focused CLI check and full
  suites pass; report states the oracle-seeded proxy cannot establish model
  behavior or search uplift for a model proposer.
- Depends: E4.0, E2.3.

### Phase E5 — RLVF design note (far; MEMO ONLY, no implementation)

#### E5.0 — Bounded RLVF memo expansion

- Goal: replace the coarse RLVF bullet with a reviewable design-note contract
  while preserving the no-implementation boundary.
- Output: detailed E5.1 contract in PLAN.md plus PROGRESS.md and TODO.md.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Define categorical referee eligibility, a draft
  reward-event data contract, immutable provenance/splits, append-only raw
  evidence, anti-Goodhart controls, and explicit unresolved research questions.
  Verified may be proposed as positive reward only after complete ordinary
  referee acceptance; violated may be non-positive; unknown, unsupported,
  solver/checker error, malformed, stale, contract-changing, or unreplayed
  evidence is ineligible with null reward. No Python/C++, executable schema,
  training loop, model/API call, optimizer, collector, dependency, benchmark
  claim, or implementation artifact.
- DoD: E5.1 declares Goal/Output/exact file set/Boundaries/DoD/Depends; the memo
  must separate normative design from measured evidence, include a threat model
  and fail-closed reward state machine, and state that no training result exists;
  the immediately preceding full suite is green; ledger/TODO updated; stage
  commit succeeds.
- Depends: E4.1.

#### E5.1 — Referee-as-reward design and data-schema memo

- Goal: specify how a future research system could record deterministic referee
  outcomes as a bounded reward signal without making the AI the referee or
  promoting incomplete evidence.
- Output: one English memo with a draft reward-event field table/example,
  categorical eligibility/reward state machine, immutable dataset and split
  protocol, candidate sampling/accounting rules, threat model, audit/replay
  requirements, limitations, and open questions; README link.
- Exact file set: docs/rlvf_design.md; README.md; PROGRESS.md; TODO.md.
- Boundaries: memo only. The draft event records schema/version, content identity,
  dataset/split/sample/candidate/proposal/source/config/referee identities,
  complete sorted obligation statuses, replay evidence, eligibility, null-or-
  rational reward, rejection reason, and immutable provenance. Positive reward
  requires complete `verified` target evidence, preserved contracts, and any
  counterexample/replay gates required by the ordinary referee. `violated` is
  non-positive; `unknown`, `unsupported`, solver/checker error, malformed,
  missing, stale, leaked, contract-changing, partial, or unreplayed evidence is
  ineligible and reward null. Raw events are append-only; derived aggregates do
  not rewrite them. Splits group related source/function identities before
  sampling; all proposed candidates are retained to avoid success-only and
  early-stop bias. No executable schema, code, test, fixture, training run,
  model/service call, optimizer, reward shaping claim, dependency, production
  recommendation, or claim of model improvement/consciousness/causality.
- DoD: memo contains purpose/non-goals, trust boundary, draft event field table
  and canonical example, state diagram/table covering every admitted terminal
  class, exact identity/determinism/replay rules, split/leakage/selection-bias
  protocol, anti-reward-hacking threat model with mitigations, retention/privacy
  considerations, audit queries, failure handling, limitations and unresolved
  decisions; README links it; no implementation files exist; full suite passes;
  ledger/TODO updated; stage commit succeeds.
- Depends: E5.0, E4.1, E3.1.

---

## 10. PROGRAM F — Process & infrastructure

### Phase F0 — Plan-system bootstrap

- F0.1 — Plan files (PLAN/PROGRESS/TODO/CLAUDE.md)
- F0.2 — Guardrails: `.githooks/` (pre-commit: tests + ratchet + ledger;
  commit-msg: stage ID), `guardrails/test_baseline.txt`, `.gitattributes`
  (LF for hooks), README workflow section, `core.hooksPath` activation
- F0.3 — First commit of the plan system

### Phase F1 — Benchmark set (M6b)

#### F1.0 — Bounded benchmark/trend expansion

- Goal: replace the coarse F1 bullets with a deterministic corpus, append-only
  run evidence, and a fail-closed logical regression gate.
- Output: detailed F1.1-F1.3 contracts in PLAN.md plus PROGRESS.md and TODO.md.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Freeze forty standalone supported-lowering
  functions in four ten-case difficulty tiers, one combined frontend run,
  explicit expected per-function statuses, exact rates, injected monotonic
  duration measurement isolated from decisions, append-only raw run rows, and
  a >=3-point logical trend. Timing is informational and can never change a
  status, identity ordering, pass/fail result, or regression decision. The first
  three points are current-version calibration observations, not fabricated
  historical A-gate measurements; every future A gate must append a real point.
- DoD: F1.1-F1.3 each declare Goal/Output/exact file set/Boundaries/DoD/Depends;
  omitted/reordered/stale corpus cases, unsupported status promotion, rewritten
  run history, timing-based gates, cherry-picked points, false historical labels,
  and logical regression promotion fail closed; the immediately preceding full
  suite is green; ledger/TODO updated; stage commit succeeds.
- Depends: E5.1.

#### F1.4 — Supported-unknown tier correction (inserted during F1.1)

- Goal: correct the planned unknown tier before corpus implementation so affine-
  unsupported nonlinear logic is never mislabeled as checker unknown.
- Output: replace nonlinear-frontier with deterministic-search-frontier in the
  F1.1 contract and record the interrupted implementation boundary.
- Exact file set: PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: planning only. Unknown-tier functions remain entirely inside the
  supported affine logic/lowering and reach deterministic checker `unknown`
  because their satisfiable high-arity contract input lies beyond the fixed
  search budget. They contain no nonlinear operation and no unsupported result.
  Do not alter the 40/4x10 size, 20/10/10/0 aggregate, checker budget, status
  taxonomy, or any implementation file in this correction commit.
- DoD: one representative six-parameter affine contract produces one
  contract-consistency unknown and a verified postcondition with zero
  unsupported nodes; PLAN uses the corrected tier name; immediately preceding
  624-test suite remains green; ledger/TODO updated; correction commit succeeds.
- Depends: F1.0, A1.1.
#### F1.1 — Curated supported-subset benchmark corpus

- Goal: freeze a content-addressed 40-function benchmark that exercises a clear
  supported-subset difficulty ladder with known referee outcomes.
- Output: codeskeptic.benchmark-corpus/v1 strict manifest/loader/checker,
  structural schema, one LF-only standalone-function translation unit, CLI,
  tests, and benchmark documentation.
- Exact file set: semantic_verifier/benchmark_corpus.py;
  semantic_verifier/benchmark_corpus_schema/v1/**;
  tools/check_benchmark_corpus.py; benchmarks/corpus/**;
  tests/test_benchmark_corpus.py; docs/benchmark_suite.md; README.md;
  PROGRESS.md; TODO.md; guardrails/test_baseline.txt.
- Boundaries: exactly forty sorted unique named functions and four sorted tiers
  of ten: affine-basic verified, affine-counterexample violated, path-sensitive
  verified, and deterministic-search-frontier unknown. Every source function is declared
  once; no undeclared helper, unsupported lowering, solver/checker error, path
  escape, duplicate, or expected-status inference. The manifest snapshots exact
  source bytes and declares each expected terminal status. The checker runs one
  combined ordinary affine-referee pass, requires the exact function set and
  complete result coverage, classifies only from raw obligation statuses, and
  compares every function to its frozen expectation. Unknown remains unknown;
  the corpus creates no verification claims beyond the reported rows. No clock,
  random value, network/model call, retry, cache, package dependency, or timing.
- DoD: 40 functions/4x10 tiers; exact expected aggregate is 20 verified, 10
  violated, 10 unknown, 0 unsupported; all violated cases have concrete replayed
  counterexamples; all unknown rows are checker unknown rather than unsupported
  lowering; strict identity/schema/file-set/UTF-8/path/function/status checks;
  missing/extra/duplicate/reordered/stale/undeclared/wrong-expectation/status-
  promotion/malformed negatives; repeated and relocated check bytes; CLI
  success/error exits; focused and full suites pass.
- Depends: F1.0, F1.4, A3.1.

#### F1.2 — Append-only benchmark run evidence

- Goal: record exact benchmark statuses/rates plus isolated operational timing
  without allowing time to influence verification or pass/fail logic.
- Output: codeskeptic.benchmark-run/v1 value/strict loader, append-only JSONL
  ledger, record/summarize CLI, first explicit calibration observation, tests,
  and documentation.
- Exact file set: semantic_verifier/benchmark_results.py;
  tools/record_benchmark_run.py; benchmarks/results/**;
  tests/test_benchmark_results.py; docs/benchmark_suite.md; README.md;
  PROGRESS.md; TODO.md; guardrails/test_baseline.txt.
- Boundaries: a run row links the exact corpus, explicit caller-supplied
  observation label and source revision, referee/toolchain configuration,
  complete sorted per-function statuses, exact counts/reduced rational rates,
  and one non-negative monotonic batch duration in nanoseconds. Duration is
  informational, excluded from all logical identities used for comparison and
  from every acceptance/regression decision; tests inject the timer. Recording
  appends one canonical LF JSON line and validates every prior byte/row first.
  Existing rows are immutable, unique by content identity and observation label,
  and never regenerated in place. No implicit date/wall clock, random value,
  retry, dropped case, percentile claim, timing threshold, network/model call,
  or package dependency.
- DoD: one real current-version calibration row; exact 40-case statuses and
  20/10/10/0 counts/rates; timing captured but perturbing it changes no logical
  status/rate/decision; append preserves prefix bytes; strict duplicate/label/
  corpus/config/case/count/rate/duration/JSON/UTF-8 and truncation negatives;
  deterministic summary ignores timing for logic; relocation; CLI record/
  summarize/error exits; focused and full suites pass.
- Depends: F1.1.

#### F1.3 — Three-point logical trend and red regression gate

- Goal: derive an auditable >=3-point trend from complete append-only run rows
  and make supported logical regressions fail closed.
- Output: codeskeptic.benchmark-trend/v1 deterministic derived artifact,
  generate/check CLI and red exit, two additional explicitly labeled current-
  version calibration observations, tests, and prospective A-gate policy docs.
- Exact file set: semantic_verifier/benchmark_trend.py;
  tools/check_benchmark_trend.py; benchmarks/results/**;
  tests/test_benchmark_trend.py; docs/benchmark_suite.md; README.md;
  PROGRESS.md; TODO.md; guardrails/test_baseline.txt.
- Boundaries: trend points are all ledger rows in append order; no selection,
  omission, reordering, rewrite, or timing filter. The initial three labels are
  F1 calibration observations of the same current version and are explicitly
  not historical A-gate results. Thereafter every A-phase gate must append one
  real observation before completion. A regression is red when total/function
  coverage changes, a previously verified function is not verified, a previously
  violated function is not violated, or unknown/unsupported/solver-error
  coverage increases; an unknown may become verified only in a new reviewed
  baseline. Timing remains displayed but never gates. Unknown/unsupported/error
  never promotes to green, and a changed baseline requires a future explicit
  plan stage rather than self-approval.
- DoD: ledger and trend contain >=3 complete unique points; all three initial
  points are honestly labeled current-version calibration; generated/check
  artifact is byte-identical after relocation; green current trend; synthetic
  verified loss, violated promotion, unknown/unsupported increase, missing case,
  omitted/reordered/cherry-picked point, stale identity, false label, and timing-
  only change coverage (logic unchanged); CLI green=0, regression=1, strict
  error=2; future A-gate rule documented; focused and full suites pass; F1
  program success criterion is met.
- Depends: F1.2.

### Phase F2 — Golden/fixture infrastructure

- F2.1 — `fixtures/` layout + regeneration script (`tools/`)
- F2.2 — Determinism CI job: suite + fixtures twice, byte comparison

#### F2.3 — Calibrated fixture subprocess timeout (inserted during D3.1)

- Goal: restore a reliable fixture gate after measured cold Windows
  regeneration exceeded the original fixed 30-second subprocess limit.
- Output: a named 120-second fixture subprocess timeout with all determinism
  and byte-comparison assertions unchanged.
- Exact file set: tests/test_fixtures.py; PLAN.md; PROGRESS.md; TODO.md.
- Boundaries: test infrastructure only. Do not change fixture generation,
  manifests, expected bytes, verifier behavior, pass criteria, or guardrail
  count. A timeout remains mandatory; 120 seconds provides at least 2x
  headroom over the measured 59-second single regeneration.
- DoD: fixture infrastructure tests pass 3/3 from a clean process state; both
  independent outputs remain byte-identical; full suite passes.
- Depends: F2.2.

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
