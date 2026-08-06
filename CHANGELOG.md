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

No consumer-visible changes yet.

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
