# Request 2 — In-memory cache maintenance

Starting from the current implementation, add an optional in-memory cache for
successful non-empty report results while preserving the supplied ReportBuilder
specification and all existing behavior when caching is disabled.

## Public API update

`ReportService` must accept these keyword-only options in addition to the
existing positional `reader, renderer` arguments:

`ReportService(reader, renderer, *, cache_enabled=False, eviction_policy=None)`

- Existing `ReportService(reader, renderer)` calls must remain valid.
- With `cache_enabled=False`, behavior must remain the same as before this
  maintenance change.
- With caching enabled and valid cache configuration, a repeated equal query
  may reuse the prior successful non-empty report result instead of reading and
  rendering again.
- If supplied, `eviction_policy` is a callable with shape
  `eviction_policy(cache_snapshot, new_key) -> iterable_of_keys_to_evict`.
  `cache_snapshot` is a shallow read-only-equivalent snapshot/copy suitable for
  policy inspection; `new_key` is the just-stored query key. The implementation
  removes the returned keys if present.

This request deliberately does not specify what `eviction_policy=None` means.
Preserve the supplied ReportBuilder specification when deciding that case.
