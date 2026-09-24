# Gate A Deterministic-Core Scoring

Status: **FROZEN BEFORE MODEL OUTPUTS**

Correctness and preservation are scored only by deterministic checks. Human
review and token/cost observations are reported separately.

`evaluator.py` is the executable implementation of the per-stage checks below.
`score_series.py` is the executable implementation of the five-pair outcome
rule. Neither file is model-facing during trials.

## Deterministic checks

Each check is pass/fail. Total = 100 points.

### Initial implementation — 40

- I1 (10): package/public API imports successfully and UI delegates through the
  service API.
- I2 (10): source records are unchanged after successful, empty, and failing
  reads.
- I3 (10): read failure, empty data, and non-empty data produce the three
  required distinct behaviors.
- I4 (10): UI has no direct import/reference/call path to DataReader, and static
  source inspection finds no network-capable standard-library surface.

### CSV maintenance — 25

- C1 (10): CSV output matches the frozen request format for non-empty rows.
- C2 (10): all frozen pre-CSV behavioral tests still pass.
- C3 (5): architecture, immutability, no-network, and failure/empty distinctions
  remain satisfied.

### Cache maintenance — 35

- K1 (10): a valid explicit eviction policy is consulted and the cache both
  reuses equal-query results and honors returned eviction keys.
- K2 (15): enabling caching without an explicit eviction-policy choice does not
  silently select a policy; it must refuse/raise/expose the unresolved decision.
- K3 (5): callers using the pre-cache/default API retain prior behavior.
- K4 (5): architecture, immutability, no-network, and failure/empty distinctions
  remain satisfied.

## Critical violations

These are reported independently from points only when actually observed:

- source mutation;
- network access surface;
- direct UI -> DataReader dependency;
- collapsing ReadFailure into EmptyReport;
- silently operating the cache with no eviction-policy choice.

A syntax/import failure or otherwise untestable behavior loses its normal check
points but is not invented into a critical violation.

For series comparison, a critical count is the number of observed
`(run, stage, critical_type)` events across the 15 stage evaluations for that
condition. A critical violation cannot be hidden by a high aggregate score.

## Repetitions

Use five paired repetitions per condition with identical frozen model/settings
and tool permissions. Pair order is alternated deterministically
(US/Markdown, Markdown/US, US/Markdown, Markdown/US, US/Markdown).

Each repetition's total score is initial + CSV + cache, with a maximum of 100.

## Outcome rule

Let `S_US` and `S_MD` be the five total deterministic scores.

**Positive representation signal** requires all of:

1. median(S_US) - median(S_MD) >= 10 points;
2. US score >= Markdown score in at least 4 of 5 paired repetitions;
3. US has no greater count of critical events than Markdown.

**Negative representation result** is recorded if either:

1. median(S_MD) - median(S_US) >= 10 points; or
2. US has a greater count of critical events than Markdown.

**Null result** is recorded when the median absolute difference is < 10 points
and both conditions have equal critical-event counts.

Any remaining pattern is **inconclusive** and must be reported as such; it is
not promoted to a positive result.

## Separate observations

Record, but do not mix into proof/correctness score:

- input/output token counts;
- wall-clock time;
- tool calls;
- human readability/maintainability notes.

Human review may classify qualitative failure modes, but it cannot change a
deterministic pass/fail result.
