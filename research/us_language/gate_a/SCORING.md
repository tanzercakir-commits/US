# Gate A Deterministic-Core Scoring

Status: **FROZEN BEFORE MODEL OUTPUTS**

Correctness and preservation are scored only by deterministic checks. Human
review and token/cost observations are reported separately.

## Deterministic checks

Each check is pass/fail. Total = 100 points.

### Initial implementation — 40

- I1 (10): package/public API imports successfully.
- I2 (10): source records are unchanged after successful, empty, and failing
  reads.
- I3 (10): read failure, empty data, and non-empty data produce the three
  required distinct behaviors.
- I4 (10): UI has no direct import/reference/call path to DataReader, and static
  source inspection finds no network-capable standard-library use.

### CSV maintenance — 25

- C1 (10): CSV output works for non-empty rows through ReportService.
- C2 (10): all frozen pre-CSV behavioral tests still pass.
- C3 (5): architecture, immutability, no-network, and failure/empty distinctions
  remain satisfied.

### Cache maintenance — 35

- K1 (10): optional cache reuses a successful result for the same query when
  caching is validly configured.
- K2 (15): enabling caching without an explicit eviction-policy choice does not
  silently select a policy; it must refuse/raise/expose the unresolved decision.
- K3 (5): callers with caching disabled retain prior behavior.
- K4 (5): architecture, immutability, no-network, and failure/empty distinctions
  remain satisfied.

## Critical violations

These are reported independently from points:

- source mutation;
- network access;
- direct UI -> DataReader dependency;
- collapsing ReadFailure into EmptyReport;
- silently selecting a cache eviction policy.

A critical violation cannot be hidden by a high aggregate score.

## Repetitions

Use five paired repetitions per condition with identical frozen model/settings
and tool permissions. Pair order is alternated deterministically
(US/Markdown, Markdown/US, ...).

## Outcome rule

Let `S_US` and `S_MD` be the five total deterministic scores.

**Positive representation signal** requires all of:

1. median(S_US) - median(S_MD) >= 10 points;
2. US score >= Markdown score in at least 4 of 5 paired repetitions;
3. US has no greater count of critical violations than Markdown.

**Negative representation result** is recorded if either:

1. median(S_MD) - median(S_US) >= 10 points; or
2. US has a greater count of critical violations than Markdown.

**Null result** is recorded when the median absolute difference is < 10 points
and neither condition has a critical-violation advantage.

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
