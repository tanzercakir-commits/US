# Request 1 — Batch maintenance

Starting from the current WorkflowRelay implementation, add batch execution
while preserving the supplied original specification and all existing
single-job behavior.

## Public API update

Add:

`WorkflowService.run_many(job_ids)`

Requirements introduced by this request:

- `job_ids` is an iterable of job IDs;
- return one result per input position, in the same order as the input;
- duplicate job IDs are allowed;
- `API.run_many(job_ids)` must delegate through the service;
- existing `API.run(job_id)` and `WorkflowService.run(job_id)` callers remain
  valid.

How the batch is partitioned or processed internally is deliberately not
specified.

This maintenance request does not restate the original architecture,
persistence, aliasing, audit, external-effect, flow, freedom, or unknown-decision
constraints. Preserve the supplied WorkflowRelay specification.
