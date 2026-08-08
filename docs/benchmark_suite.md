# Curated benchmark suite

Status: the F1 corpus, append-only run evidence, and three-point logical trend
gate are implemented and frozen.

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

The summary separates logical points from informational timing.

## Three-point logical trend gate

`benchmarks/results/trend.json` is the deterministic derived
`codeskeptic.benchmark-trend/v1` artifact for every ledger row in append order.
Its first three points are explicitly named `f1-calibration-001` through
`f1-calibration-003`. They are repeated observations of one current logical
version, not reconstructed results for historical A gates. The first observation
was captured at the F1.1 revision; the next two were independently captured at
the F1.2 revision after evidence recording existed. All three have the identical
corpus, configuration, forty statuses, counts, rates, and logical identity.

The trend is green only while every complete point preserves the baseline
function set, every baseline-verified function remains verified, every baseline-
violated function remains violated, and unknown/unsupported/solver-error
coverage does not increase. A baseline unknown or unsupported result cannot be
promoted inside the existing trend. Such a change requires a future explicit
plan stage that reviews and replaces the baseline; the gate cannot approve its
own baseline change. A solver/checker error cannot become a run row and exits as
a strict error.

The artifact contains full run identities, source revisions, counts, and measured
durations for audit. Its separate `logic_sha256` excludes operational duration
and event identity, so timing changes remain visible but cannot alter red/green
status. No point selection, omission, reordering, rewrite, timing filter, or
historical relabeling is accepted.

Generate or byte-check the complete trend:

    python tools/check_benchmark_trend.py benchmarks/results/runs.jsonl benchmarks/results/trend.json
    python tools/check_benchmark_trend.py benchmarks/results/runs.jsonl benchmarks/results/trend.json --check

A green trend exits 0, a supported logical regression exits 1, and malformed,
incomplete, stale, mislabeled, or solver/checker-error evidence exits 2.

For every future A-phase gate, record one real `A<stage>-<description>`
observation before marking that gate complete, then regenerate and check this
artifact. Historical A-gate points must never be invented. A reviewed baseline
change must be declared by its own future PLAN stage before any ledger or trend
update.