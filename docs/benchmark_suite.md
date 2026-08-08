# Curated benchmark suite

Status: F1.1 corpus and deterministic checker are implemented. Append-only run
evidence (F1.2) and the three-point trend gate (F1.3) follow separately.

## Corpus contract

`benchmarks/corpus/manifest.json` is a content-addressed
`codeskeptic.benchmark-corpus/v1` manifest for one LF-only C++ translation unit.
It declares exactly forty sorted standalone functions in four ten-case tiers:

- `affine-basic`: ten verified affine functions;
- `affine-counterexample`: ten violated affine functions with exact replayed
  counterexamples;
- `path-sensitive`: ten verified branch-sensitive functions; and
- `deterministic-search-frontier`: ten supported affine functions whose
  high-arity satisfiable precondition lies beyond the fixed deterministic
  search budget, so contract consistency remains unknown.

The exact aggregate is 20 verified, 10 violated, 10 unknown, and 0 unsupported.
The frontier tier deliberately contains no nonlinear expression. Nonlinear
multiplication would be `unsupported` under the affine referee and must never be
relabeled as `unknown`.

The manifest snapshots exact source bytes, tiers, function names, and expected
statuses. The loader rejects missing/extra files, duplicate or reordered cases,
unknown fields, unsafe/stale identities, malformed UTF-8 or JSON, inconsistent
tier counts, and changed expectations.

## Check boundary

The checker runs the complete translation unit through one ordinary affine-
referee batch. It requires the exact declared function set and at least one raw
result per function. Solver/checker errors fail the run. Aggregate status uses
the fail-closed order unsupported, violated, unknown, then all-verified.

Every violated result must contain concrete counterexample evidence and replay
byte-for-byte through the checker against its original obligation. Unknown
results must be genuine checker unknowns with zero unsupported lowering nodes.
Only an exact match to all forty frozen expectations produces a successful
corpus check.

Run the check:

    python tools/check_benchmark_corpus.py benchmarks/corpus

Success prints deterministic `codeskeptic.benchmark-corpus-check/v1` JSON and
exits 0. Structural, source, frontend, status, evidence, replay, or expectation
failure exits 2. The check uses no timing, randomness, network/model call,
retry, or package dependency.
