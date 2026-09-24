# Request 1 — CSV maintenance

Starting from the current implementation, add CSV report output as an optional
output format while preserving the supplied ReportBuilder specification and all
existing default behavior.

## Public API update

Change `ReportService.build_report` to:

`build_report(query, *, output_format="default")`

- `output_format="default"` must preserve the previous renderer-based behavior.
- `output_format="csv"` must return a CSV `str` for non-empty source rows.
- Source rows are mapping-like records.
- CSV columns are the union of row keys sorted lexicographically.
- Use `\n` line endings and include a final newline.
- Use Python standard-library CSV behavior for quoting/escaping.

Existing callers that do not request CSV must keep their prior behavior.
