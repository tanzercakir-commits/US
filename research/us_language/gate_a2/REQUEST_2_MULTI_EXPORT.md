# Request 2 — Multiple exporters maintenance

Starting from the current WorkflowRelay implementation, add support for
multiple named exporters while preserving the supplied original specification,
batch behavior, and existing single-export behavior.

## Public API update

Extend the existing WorkflowService constructor with keyword-only options:

`WorkflowService(store, processor, exporter, audit_log, *, exporters=None, fanout_policy=None)`

Existing four-positional-argument construction must remain valid.

When `exporters` is not supplied, the existing single exporter continues to be
identified by the name `"default"`.

When `exporters` is supplied:

- it is a mapping of `exporter_name -> exporter object`;
- the positional `exporter` argument may be `None`;
- each exporter object keeps the existing
  `exporter.export(job_id, result) -> receipt` shape.

If supplied, `fanout_policy` is callable as:

`fanout_policy(exporter_names) -> iterable_of_required_exporter_names`

where `exporter_names` is a tuple containing the configured exporter names in
lexicographic order. Returned names must refer to configured exporters.

The request deliberately does **not** specify what `fanout_policy=None` means
when multiple exporters are configured. Preserve the original WorkflowRelay
specification when deciding that case.

This request also deliberately does not restate prior rules about persisted
receipts, resuming committed jobs, external-effect duplication, rollback,
aliasing, or architecture.
