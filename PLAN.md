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
- DoD: `python -m unittest tests.test_budgets` is green; injected solver timeout
  and file-budget exhaustion deterministically yield `unknown`, never
  `verified`; repeated budgeted JSON is byte-identical; zero/unlimited boundary
  cases, cross-check behavior, full suite, and fixture check are green.
- Depends: A5.2.

#### A5.4 — Scaling phase gate
- Goal: freeze A5 operational behavior and demonstrate that scaling changes
  work performed, not proof meaning.
- Output: `examples/scaling_slice.cpp`, updated scaling decision/operations
  documentation, deterministic evidence in `PROGRESS.md`.
- DoD: uncached and warm-cache reports for the scaling slice are byte-identical;
  the warm run records zero backend calls; two budgeted runs are byte-identical;
  the path-growth probe and any A5.1 implementation benchmark meet their
  recorded target; `python -m unittest discover -s tests` and
  `python tools/regenerate_fixtures.py --check` are green.
- Depends: A5.1–A5.3 and A5.5.

### Phase A6 — Semantic extensions (far horizon; each expands when due)

- A6.0 — Expansion stage
- A6.1 — **Decision point (reopens D9):** int64/unsigned/bit ops → QF_BV vs
  mathematical ints + extra obligations
- A6.2 — Arrays (restricted QF_ARRAY)
- A6.3 — Value-type structs
- A6.4 — Restricted references (provably alias-free cases)
- A6.5 — `modifies` / frame conditions ("and nothing else changed")
- A6.6 — CHC/Spacer invariant inference (research spike; path to reducing
  user-written invariants)

---

## 6. PROGRAM B — Production (CodeSkeptic integration)

Goal: carry the lab-proven architecture into CodeSkeptic's real Clang
infrastructure. Reference: prototype fixtures = the specification.

### Phase B1 — Native adapter (M4)

#### B1.1 — Fixture export: IR + obligation JSONs for a corpus from the
  prototype (`fixtures/` directory, generator script)
- DoD: `python tools/export_fixtures.py` produces a deterministic corpus; two
  runs byte-identical.
#### B1.2 — Standalone semantic module skeleton in CodeSkeptic (NO reporter
  dependency; `src/semantic/` — without touching the Rule.h seam)
#### B1.3 — ASTContext → Semantic IR lowering (v0 subset, exact)
#### B1.4 — Byte-for-byte comparison harness: fixture equality inside the
  in-memory Clang test harness
- DoD: C++-produced JSON == Python fixture JSON across the corpus.
#### B1.5 — Extend the existing `cs:` parser with arithmetic; ContractInfo
  adaptation

### Phase B2 — VC + referee on the production path (expand via B2.0)

- B2.0 — Expansion + decision: port VC generation to C++ or keep a Python
  helper process (recommendation: VC is small → port; solver is subprocess
  anyway)
- B2.1 — VC generator (chosen route), fixture equality
- B2.2 — Verification rule at the `Rule::check` seam; extend the Diagnostic
  model to carry POSITIVE results/unknown/unsupported (current shape only
  carries findings — Codex's observation)
- B2.3 — SARIF output: obligations + results + counterexamples (M6a)
- B2.4 — MCP surface: `verify_function` tool (AI agents get direct referee
  access — the first end of SCI)

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
