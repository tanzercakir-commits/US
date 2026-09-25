# Gate A2 Deterministic-Core Scoring

Status: **FROZEN BEFORE MODEL OUTPUTS**

Correctness and preservation are scored only by deterministic checks. Human
review and cost observations remain separate.

Maximum score per repetition: **150**.

## Initial implementation — 50

- I1 (5, architecture): public API imports and API delegates only through
  WorkflowService.
- I2 (10, architecture): forbidden dependency checks and no-network static scan
  pass.
- I3 (10, state_flow): missing, processing-failure, export-failure, and success
  flows produce distinct required outcomes.
- I4 (10, aliasing): hostile nested mutation by Processor/Exporter cannot mutate
  canonical JobStore payload or committed result.
- I5 (10, state_flow): commit precedes export; export failure remains COMMITTED;
  successful export reaches EXPORTED; repeated EXPORTED execution does not
  repeat the external effect.
- I6 (5, audit): required transition events are appended and earlier AuditLog
  entries cannot be changed through later append or returned aliases.

## Batch maintenance — 25

- B1 (5, state_flow): run_many/API batch delegation returns one result per input
  in input order.
- B2 (10, external_effects): duplicate job IDs do not duplicate a successful
  external effect.
- B3 (5, aliasing): payload/result isolation remains correct across batch use.
- B4 (5, preservation): initial architecture, flow distinctions, no-network,
  persistence, and audit behavior remain satisfied.

## Multiple exporters maintenance — 35

- M1 (10, unresolved): multiple exporters with no fanout policy expose
  UnresolvedDecision rather than silently selecting a policy.
- M2 (5, state_flow): an explicit fanout policy selects the required configured
  exporters correctly.
- M3 (5, preservation): success receipts survive a later exporter failure.
- M4 (5, external_effects): a replacement WorkflowService over the same
  JobStore/AuditLog invokes only still-required exporters lacking success
  receipts.
- M5 (5, state_flow): partial export failure preserves COMMITTED state and the
  committed result.
- M6 (5, preservation): all earlier constraints remain satisfied.

## Automatic retry maintenance — 40

- R1 (10, unresolved): retry_enabled=True with no retry policy exposes
  UnresolvedDecision rather than silently inventing classification/attempts.
- R2 (10, state_flow): an explicit retry policy can repeat a failed processing
  phase and then complete correctly.
- R3 (5, state_flow): export retry after commit does not recompute/recommit the
  processor result.
- R4 (5, external_effects): already successful exporter effects are not repeated
  during retry/recovery.
- R5 (5, preservation): durable state, alias isolation, and audit history remain
  valid through retry.
- R6 (5, preservation): all earlier maintenance behavior and original
  constraints remain satisfied.

## Score families

Family totals are retained separately so one quirky check family cannot by
itself establish a positive representation signal.

- architecture: 15
- state_flow: 50
- aliasing: 15
- audit: 5
- external_effects: 20
- unresolved: 20
- preservation: 25

Total: 150.

## Critical violations

Critical events are counted independently from points when actually observed:

- forbidden API/JobStore/Processor/Exporter/AuditLog dependency;
- network-access surface;
- canonical payload mutation;
- committed-result mutation;
- audit history deletion/reordering/mutation;
- PENDING -> EXPORTED without commit;
- rollback/loss of committed state after export failure;
- duplicate successful external effect for one (job, exporter_name);
- collapse of required distinct result categories;
- silent multi-export policy selection;
- silent automatic retry policy/classification/attempt selection.

Import/syntax failure loses relevant points but is not invented into an
unobserved critical event.

## Repetitions

Use five paired repetitions with the frozen ordering in EXPERIMENT_CONTRACT.md.

Each repetition total is initial + batch + multi_export + retry = 150.

## Sensitivity gate

Before interpreting representation outcome:

- **insensitive_ceiling** if both condition medians are at least 143/150 and
  both have zero critical events;
- **insensitive_floor** if both condition medians are at most 60/150.

A sensitivity result takes precedence over positive/negative/null
interpretation. It means the benchmark did not provide a useful discrimination
surface at the relevant end of the scale.

## Representation outcome rule

If the sensitivity gate does not fire, let `S_US` and `S_MD` be the five
total scores.

A **positive** representation signal requires all of:

1. median(S_US) - median(S_MD) >= 12;
2. US score >= Markdown score in at least 4 of 5 paired repetitions;
3. US has no greater critical-event count than Markdown;
4. at least two score families have a US median advantage of >= 5 points.

A **negative** representation result is recorded if either:

1. Markdown satisfies the symmetric four requirements above against US; or
2. US has a greater critical-event count than Markdown.

A **null** result is recorded when:

- absolute median difference is < 12; and
- critical-event counts are equal.

Any remaining pattern is **inconclusive**.

No result is promoted by human review, token cost, wall-clock speed, or model
self-assessment.
