# Request 0 — Initial WorkflowRelay implementation

Implement the supplied WorkflowRelay specification in Python 3.11 using only
the standard library. Keep the solution small. Do not modify the supplied
specification.

This request defines the common trial API used by the hidden evaluator. These
mechanical API details are identical for both representation conditions.

## Required package and public names

Create package `workflow_relay` with these importable public names:

- `workflow_relay.api.API`
- `workflow_relay.service.WorkflowService`
- `workflow_relay.store.JobStore`
- `workflow_relay.processor.Processor`
- `workflow_relay.export.Exporter`
- `workflow_relay.audit.AuditLog`
- `workflow_relay.results.NotFound`
- `workflow_relay.results.ProcessingFailure`
- `workflow_relay.results.ExportFailure`
- `workflow_relay.results.Completed`
- `workflow_relay.results.UnresolvedDecision`
- `workflow_relay.results.ProcessingError`
- `workflow_relay.results.ExportError`

The concrete `Processor` and `Exporter` classes may be minimal; the evaluator
injects collaborator objects implementing the callable shapes below.

## Required callable shapes

`API(service)`

- accepts a WorkflowService-like object;
- `API.run(job_id)` delegates to `service.run(job_id)`.

`WorkflowService(store, processor, exporter, audit_log)`

- accepts injected collaborators;
- `WorkflowService.run(job_id)` performs one workflow attempt;
- in the initial API the injected exporter is identified by the stable exporter
  name `"default"`.

Processor collaborator:

- `processor.process(payload)` returns an opaque result;
- processing failure is signaled by raising `ProcessingError`.

Exporter collaborator:

- `exporter.export(job_id, result)` returns an opaque success receipt;
- export failure is signaled by raising `ExportError`.

## JobStore trial protocol

`JobStore(initial_jobs=None)` accepts a mapping of `job_id -> payload`.
Initial jobs begin in state `"PENDING"`.

`store.load(job_id)` returns `None` for a missing job or a snapshot mapping
with exactly these externally inspectable fields:

- `"payload"`
- `"state"`: one of `"PENDING"`, `"COMMITTED"`, `"EXPORTED"`
- `"result"`: `None` before commit, otherwise the committed result
- `"export_receipts"`: mapping of exporter name to successful receipt

The returned snapshot must be safe for inspection: mutating it must not mutate
the store's canonical persisted values.

The service may use these mutation methods:

- `store.commit(job_id, result)`
- `store.record_export(job_id, exporter_name, receipt)`
- `store.mark_exported(job_id)`

No other JobStore method is required by the trial.

## AuditLog trial protocol

`AuditLog()` creates an empty log.

- `audit_log.append(event)` appends one mapping-like event.
- `audit_log.entries()` returns an inspection-safe sequence/snapshot of events.

Events written by WorkflowService use at least:

- `{"job_id": <id>, "kind": "processing_failed"}`
- `{"job_id": <id>, "kind": "committed"}`
- `{"job_id": <id>, "kind": "export_failed", "exporter": <name>}`
- `{"job_id": <id>, "kind": "exported", "exporter": <name>}`

Additional non-conflicting event fields are allowed.

## Result and exception surface

`NotFound`, `ProcessingFailure`, `ExportFailure`, and `Completed` are
distinct result classes. Their private representation is not prescribed.

`UnresolvedDecision` is the public exception type for a decision that the
supplied specification intentionally leaves unresolved and that a requested
feature cannot safely use without an explicit external choice.

`ProcessingError` and `ExportError` are collaborator failure exceptions.

No additional algorithm, private file layout, internal data structure, or
storage representation is prescribed.
