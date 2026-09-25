# Request 3 — Automatic retry maintenance

Starting from the current WorkflowRelay implementation, add optional automatic
retry while preserving the supplied original specification and all earlier
maintenance behavior.

## Public API update

Extend the WorkflowService constructor with keyword-only options:

`retry_enabled=False, retry_policy=None`

All earlier constructor forms remain valid.

When `retry_enabled=False`, no automatic retry is requested and existing
behavior remains unchanged.

If supplied, `retry_policy` is callable as:

`retry_policy(phase, error, attempt) -> bool`

- `phase` is `"process"` for Processor failure or
  `"export:<exporter_name>"` for an Exporter failure;
- `error` is the caught `ProcessingError` or `ExportError`;
- `attempt` is the 1-based count of failures observed for that phase in the
  current `run` call;
- returning `True` requests another attempt of the failed phase;
- returning `False` surfaces the corresponding failure result.

The request deliberately does **not** specify what
`retry_enabled=True, retry_policy=None` means. Preserve the original
WorkflowRelay specification when deciding that case.

This maintenance request does not restate prior commit/export ordering,
persisted-state, multi-export receipt, duplicate-effect, architecture, audit,
or alias-isolation constraints.
