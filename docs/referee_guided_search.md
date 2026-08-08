# Referee-guided exhaustive search

Status: E4.1 implements the frozen exhaustive Best-of-4 calibration.

## Protocol

The candidate artifact links the exact twenty-case E2 corpus. Every case has
four ordered, distinct patch proposals, and every proposal names the unchanged
original source hash. Rank 1 is the single-shot comparator. The Best-of-4 arm
checks all four ranks independently against that same original source, even
after an earlier rank verifies. A rejected or violated candidate never becomes
input to another candidate.

Only complete target-function `verified` results are eligible. `violated`,
`unknown`, `unsupported`, checker error, malformed, stale, no-op, and contract-
editing candidates cannot be selected. If multiple candidates verify, the
lowest rank wins deterministically; otherwise selection is null. The proposer
never decides success.

The evaluator combines the eighty uniquely renamed standalone candidate
functions into one deterministic frontend batch. It requires the exact
expected function set, maps every result back to one case/rank, and records all
eighty candidate source hashes, proposal identities, result statuses, and
verification evidence identities. Batching changes no candidate ordering,
selection rule, source edit, or referee decision.

## Frozen calibration result

The predeclared absolute success-rate uplift threshold is `2/5`. Exact reduced
rational arithmetic gives:

- rank-1 single-shot: 4/20 = 1/5;
- exhaustive Best-of-4: 18/20 = 9/10;
- absolute uplift: 9/10 - 1/5 = 7/10;
- outcome: passed because 7/10 >= 2/5.

The report retains four evaluations for every case, including ranks after the
selected candidate. Two cases have no verified candidate and remain
unselected; no case is omitted or censored.

Generate or reproduce-check both frozen artifacts:

    python tools/run_referee_search.py benchmarks/experiment_e2/corpus benchmarks/referee_search/candidates.json benchmarks/referee_search/report.json
    python tools/run_referee_search.py benchmarks/experiment_e2/corpus benchmarks/referee_search/candidates.json benchmarks/referee_search/report.json --check

## Evidence boundary

This is an oracle-seeded recorded scripted proxy, not model output. It
calibrates the exhaustive-selection mechanism on a deliberately constructed
candidate set. It does not establish consciousness, causality, general model
behavior, model-proposer performance, or model search uplift. A model study
would require separately frozen model provenance and candidate transcripts and
cannot inherit this outcome.
