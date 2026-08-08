# Semantic verification fixture archive v2

This immutable archive preserves the complete current fixture corpus immediately
before A6.2 introduced owned fixed-size arrays and advanced the report/Semantic
IR schema to `codeskeptic.semantic-verification/v3`.

`SHA256SUMS` covers `manifest.json`, every source case, and every expected IR and
report artifact. Paths are relative to this directory and use `/` separators.
The archive is migration evidence only; current fixture regeneration must never
write here.
