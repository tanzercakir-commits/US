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

## Append-only run evidence

`benchmarks/results/runs.jsonl` contains canonical one-line
`codeskeptic.benchmark-run/v1` events. The first explicit observation is
`f1-calibration-001`, recorded against the F1.1 source revision. It links the
exact corpus and fixed frontend/checker/execution configuration, retains all
forty sorted statuses, and stores exact counts and reduced rational rates.

Each event has two identities. `id` covers the complete event, including the
observed monotonic batch duration. `logic_sha256` covers only corpus,
configuration, cases, counts, and rates. Changing timing therefore changes the
raw event identity but cannot change or disguise the logical outcome used by a
future trend gate.

Dates, labels, and source revisions are explicit caller inputs. The runner does
not read a wall clock. A monotonic nanosecond clock measures only the batch
boundary and never affects verification, status, ordering, rate arithmetic, or
acceptance. The first recorded result remains 20 verified, 10 violated, 10
unknown, and 0 unsupported; its duration is operational evidence for that run,
not a performance threshold.

Recording validates every existing ledger byte and row before appending one new
canonical line. Duplicate event identities or observation labels, mixed corpus
identities, truncated/noncanonical rows, stale counts/rates/links, and invalid
timing fail closed. Existing lines are never regenerated or rewritten.

Record an explicitly labeled future observation or summarize the ledger:

    python tools/record_benchmark_run.py record benchmarks/corpus benchmarks/results/runs.jsonl --observation A4.1-phase-gate --recorded-on 2026-08-07 --source-revision <40-hex-commit>
    python tools/record_benchmark_run.py summarize benchmarks/results/runs.jsonl

The summary separates logical points from informational timing. F1.3 will define
the red/green trend rule; F1.2 makes no regression or timing claim.