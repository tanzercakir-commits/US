# Changelog

This file records consumer-visible changes to the verifier, report/IR schema,
CLI, proof evidence, supported boundary, fixtures, and migration requirements.
Detailed per-stage commands and evidence remain in `PROGRESS.md`.

## Discipline

- Add consumer-visible work to `Unreleased` in the same commit as the change.
- Prefix entries with the PLAN stage ID when one exists.
- Use `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, and
  `Migration` headings as applicable; omit empty headings in a release.
- A schema-major proposal must include a `Migration` entry, preserved old
  fixtures, and the steps required by `docs/schema_versioning.md`.
- A release moves relevant `Unreleased` entries under `## [X.Y.Z] - YYYY-MM-DD`.
- Released sections are append-only historical records; corrections use a new
  entry rather than rewriting behavior retroactively.
- Internal refactors with no consumer-visible effect stay in `PROGRESS.md` and
  do not require a changelog bullet.

## [Unreleased]

### Added

- A6.2 adds exact owned one-dimensional fixed-size arrays with canonical
  `array<element,length>` types, `array`/`select`/`store` expressions,
  whole-array SSA updates, per-access replayable bounds obligations, contract
  indexing, homogeneous QF_ALIA/QF_ABV Z3 emission, model replay, and a fully
  verified 18-obligation fixture. Pointer decay, aliasing, dynamic allocation,
  multidimensional arrays, partial initialization, and unmodeled libraries
  remain fail-closed.
- A6.12 adds `codeskeptic.fixed-integer-phase-gate/v0`, a deterministic
  60-obligation combined slice, positive/negative evidence for all eight
  operator rows, frozen target/conversion/classifier/backend matrices, exact v1
  archive verification, five-case v1-to-v2 status equivalence, and the integer
  operations runbook. The fixture corpus grows to 18 artifacts.
- A6.11 adds C++17 `~`, `&`, `|`, `^`, `<<`, and `>>` with exact promotions,
  usual conversions, precedence, 32/64-bit QF_BV encoding, shift-count VCs,
  signed-left-shift representability checks, pinned arithmetic signed right
  shift, replay/minimization, and a 19-obligation explicit-Z3 fixture. Compound
  assignments, rotates, and builtin bit operations remain fail-closed.
- A6.10 adds C++17 `unsigned int`/`unsigned long long` as `u32`/`u64`,
  exact usual conversions and modulo arithmetic, homogeneous QF_BV emission,
  exact widened signed-result overflow checks, width-checked BV model
  decoding/replay, unsigned calls/contracts/loops, and a
  20-obligation explicit-Z3 fixture. Affine and default cross-check fail closed
  for BV-required obligations; cache identity now pins both SMT lanes.
- A6.9 adds C++17 `long long` as owned `i64` across lowering, contracts,
  signed promotions, pinned i64-to-i32 narrowing, width-specific safety VCs,
  affine reasoning/search, SMT-LIB, replay, modular calls, and loops. Signed
  `/` and `%` are exact in logical formulas with literal divisors; general
  source divisors still receive exact zero and minimum/-1 safety checks. The
  22-obligation int64 fixture and example are fully verified.
- A5.4 adds the committed assignment-diamond scaling slice and
  `codeskeptic.scaling-phase-gate/v0` executable gate. It freezes cold/fill/warm
  report identity, zero warm backend calls, repeated budget identity, and the
  1/1/1/1 merge target using deterministic counts and SHA-256 evidence rather
  than timing.
- A5.3 adds validated solver-timeout and per-file check-budget value objects plus
  `--max-checks N`. Supported obligations beyond the source-ordered limit are
  explicit `unknown` results without backend work; zero and unlimited are
  defined boundaries, unsupported obligations do not consume units, cache hits
  cannot bypass the limit, and cross-check mode cannot hide Z3 timeout as
  `verified`.
- A5.2 adds the opt-in `--cache PATH` persistent obligation-result cache. Exact
  SHA-256 keys bind report/key schemas, backend identity and configuration,
  solver policy, and canonical logical query content; valid hits reconstruct
  current result IDs and source/trace locations without changing report bytes.
  Missing, stale, malformed, or incompatible data is recomputed, cache I/O
  failures do not change referee results, and `solver_error` is never reused.
- A4.3 adds optional source-ordered `trace` steps to violated results whose VC
  path crosses a branch. Each machine-readable step records the versioned
  condition, taken direction, and source location; text output renders the same
  data as a deterministic `when branch condition ...` explanation.

### Changed

- A6.2 moves the producer to `codeskeptic.semantic-verification/v3` because
  array type identities, expression kinds, bounds obligations, and array-valued
  evidence are new proof-bearing wire semantics. Cache/key schemas advance to
  v1, the fixed-integer phase gate advances to v1, and the fixture corpus grows
  to 20 artifacts.
- A6.8 moves the producer to `codeskeptic.semantic-verification/v2`, maps the
  existing C++17 `int` subset to the explicit `i32` IR identity, and serializes
  every fixed-width integer constant and counterexample binding as canonical
  decimal text. Clang now validates the pinned fixed-width target profile before
  lowering; mismatch is fail-closed. New unsigned and 64-bit source types remain
  unsupported.
- A4.1 moves the producer to `codeskeptic.semantic-verification/v1` and changes
  validity counterexamples from complete public replay models to deterministic
  minimized binding cores. A complete model is still replayed internally, and
  a binding is removed only when exact reasoning proves the remaining core,
  together with the obligation assumptions, forces the violation.
- A4.2 projects replayed models to the conclusion's transitive
  assumption-variable cone before greedy minimization, so disconnected solver
  bindings cannot appear in the public core even when a removal proof is
  inconclusive.
- A5.5 compacts structured branch joins into one exact factored disjunction,
  reducing the 1/2/4/8-diamond probe from 2/4/16/256 post-join obligations to
  1/1/1/1. Guarded trace templates resolve only after full-model replay, and the
  affine backend uses exact case splitting to preserve prior proofs.

### Migration

- v3 consumers must implement exact owned-array values, `select`/`store`,
  `[0, length)` access obligations, QF_ALIA/QF_ABV sorts, and arrays of
  canonical decimal strings in counterexample evidence, or reject those
  objects fail-closed. The complete nine-case v2 corpus is immutable under
  `fixtures/versions/v2/` with 28 SHA-256 entries; v2-to-v3 statuses are
  equivalent for all nine legacy cases. v0, v1, v2, unknown, and mixed-major
  payloads are rejected by the current compatibility gate.
- A6.11 remains schema v2 because it adds only previously unsupported operator
  and predicate-op values on new bitwise/shift objects; conforming consumers
  already reject unknown expression operators fail-closed. Consumers must
  implement exact shift definedness and the pinned signed-right-shift profile
  or reject those objects. Existing fixture bytes remain unchanged.
- A6.10 remains schema v2 because unsigned identities and integral casts were
  reserved by A6.8, and the additive `predicate/signed_no_overflow` form occurs
  only in new unsigned-tainted objects. Consumers must implement that predicate,
  modulo-width values, and the frozen conversion table or reject those objects
  fail-closed. Fixture manifest cases may set `backend: z3`; omission preserves
  the default cross-check lane.
- A6.9 remains in v2 because its fixed-width identities were reserved by A6.8.
  Consumers that do not implement `i64` or the additive `integral` cast
  expression kind must reject those objects fail-closed; existing i32 fixture
  outcomes remain unchanged.
- v2 consumers must replace the implicit `int` identity with `i32`, accept the
  reserved `u32`/`i64`/`u64` identities, and decode fixed-width constants and
  counterexample bindings from canonical decimal strings. Boolean values remain
  JSON booleans. See `docs/schema_versioning.md`.
- The complete v1 corpus is immutable under `fixtures/versions/v1/` with a
  SHA-256 manifest; current fixture paths contain v2 bytes and preserve every
  v1 obligation result status. v0 remains archived unchanged.
- v1 consumers must treat `counterexample` as a possibly empty partial core and
  join it to the referenced obligation assumptions; they must not replay it as
  a complete input assignment.
- Consumers must reject v0/v1/v2 report/Semantic IR mixtures and unknown majors.
  The reference `require_current_schema` gate enforces both rules.
- The complete v0 fixture corpus remains immutable under
  `fixtures/versions/v0/`; current fixture paths now contain v1 bytes.
- No compatible legacy reader or conversion tool exists in this producer-only
  repository. The Unreleased period is the migration window, with no v0
  fixture deletion planned.

## [0.1.0] - 2026-08-06

### Added

- Initial real-Clang C++ to owned Semantic IR pipeline for the documented
  int/bool subset, with deterministic JSON and human-readable output.
- Inline `cs: requires`, `ensures`, and `invariant` parsing with fail-closed
  attachment and expression validation.
- Versioned assignments, branches/merges, direct modular calls with int result
  havoc/ensures, recursion rejection, and invariant-annotated while loops.
- Verification conditions for contracts, assertions, int32 arithmetic safety,
  call pre/postconditions, loop entry/preservation/exit knowledge, and missing
  returns.
- Dependency-free affine backend and external Z3 QF_LIA backend with fixed
  options, timeouts, model parsing, mandatory replay, and default cross-check.
- Five-status result taxonomy, structured frontend failures, sorted
  counterexamples, and explicit loop-termination non-goals.
- Five-case golden corpus, regeneration/check tool, LF byte contract, and CI
  two-run determinism gate.
- Result/schema reference, schema version policy, solver decision record,
  prototype assessment, and fail-closed adoption guide.
- Full guardrail suite with a 139-test ratchet.

### Changed

- A2.1/A3 result-bearing call and loop/non-goal fields are included in the
  initial frozen `codeskeptic.semantic-verification/v0` baseline because they
  predated the fixture-backed compatibility freeze.

### Migration

- This is the first versioned baseline. Consumers must require
  `codeskeptic.semantic-verification/v0`, treat unknown status/mode/kind values
  as fail-closed, and retain top-level non-goals even when Semantic IR is
  omitted.
