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

- v1 consumers must treat `counterexample` as a possibly empty partial core and
  join it to the referenced obligation assumptions; they must not replay it as
  a complete input assignment.
- Consumers must reject v0/v1 report/Semantic IR mixtures and unknown majors.
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
