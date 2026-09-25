# WorkflowRelay specification

Every bracketed fact ID corresponds to the same canonical fact used by
the sibling structured condition. The prose below is normative.

## Intent

- **[F01]** Execute workflows without losing committed work or duplicating successful external effects.
- **[F02]** Maintenance and WorkflowService replacement must preserve behavior through persisted workflow state rather than service-instance memory.

## Architecture

- **[F03]** API may directly depend on and call WorkflowService.
- **[F04]** API must not directly depend on or call JobStore.
- **[F05]** API must not directly depend on or call Processor.
- **[F06]** API must not directly depend on or call Exporter.
- **[F07]** API must not directly depend on or call AuditLog.
- **[F08]** WorkflowService may directly depend on and call JobStore.
- **[F09]** WorkflowService may directly depend on and call Processor.
- **[F10]** WorkflowService may directly depend on and call Exporter.
- **[F11]** WorkflowService may directly depend on and call AuditLog.
- **[F12]** JobStore must not directly depend on or call Exporter.
- **[F13]** Exporter must not directly depend on or call JobStore.

## Required rules

- **[F14]** JobStore is the sole persistence owner of workflow payload, workflow state, committed result, and per-exporter success receipts.
- **[F15]** AuditLog is append-only: later events must not delete, reorder, or mutate earlier audit entries.
- **[F16]** WorkflowService records processing_failed, committed, export_failed, and exported audit events at the corresponding transitions.
- **[F17]** Canonical job payload stored by JobStore must not be mutated through aliases passed to Processor or any later collaborator.
- **[F18]** A committed result stored by JobStore must not be mutated through aliases passed to Exporter or any later collaborator.
- **[F19]** The implementation performs network access.
- **[F20]** A result is committed before any external export effect for that result is attempted.
- **[F21]** Exporter failure after commit does not roll back the committed result or COMMITTED workflow state.
- **[F22]** For a given job and exporter name, a successfully recorded external export effect occurs at most once, including after later calls, maintenance, retries, or WorkflowService replacement.
- **[F23]** Workflow state skips directly from PENDING to EXPORTED without a committed result.
- **[F24]** NotFound, ProcessingFailure, ExportFailure, and Completed are pairwise distinct observable outcomes.
- **[F25]** A successful exporter receipt remains persisted even if another exporter later fails or a new WorkflowService instance resumes the job.

## Deliberately delegated choices

- **[F26]** Internal data structures, subject to all other facts.
- **[F27]** Internal batch partitioning strategy, subject to observable batch semantics and all other facts.
- **[F28]** Private helper classes, functions, and internal file layout beyond the required public trial API.
- **[F29]** AuditLog internal storage and indexing representation, subject to append-only semantics.
- **[F30]** Invocation order among exporters that are still required and have no recorded success, when no other rule or explicit policy constrains that order.

## Required flow

- **[F31]** If a job does not exist, return NotFound without calling Processor or Exporter.
- **[F32]** If Processor fails while the job is PENDING, append processing_failed, return ProcessingFailure, keep the job PENDING, and do not commit or export.
- **[F33]** If Processor succeeds while the job is PENDING, commit the result, enter COMMITTED, append committed, and only then attempt export.
- **[F34]** If an attempted required export fails after commit, append export_failed, return ExportFailure, and keep the job COMMITTED.
- **[F35]** When every exporter required by the active explicit policy has a persisted success receipt, mark the job EXPORTED, append exported, and return Completed.
- **[F36]** If a job is already EXPORTED, return Completed from persisted state without invoking an exporter again.
- **[F37]** When a COMMITTED multi-export job is resumed, exporters with persisted success receipts are not invoked again; only still-required exporters without success receipts remain eligible.

## Open decisions

- **[F38]** The policy that decides which exporters are required when multiple exporters are configured is unresolved. No default all, any, first-success, or best-effort policy may be silently selected.
- **[F39]** Automatic retry policy is unresolved, including which processing/export failures are retryable and how many attempts are allowed. No retry classification or attempt limit may be silently selected.
