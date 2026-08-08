# Project index fixture

The two-unit project exercises header redeclaration merging, overloaded external
functions, one translation-unit-owned `static` function, and four direct call
edges. `expected.index.json` is the canonical A7.2 artifact.

`missing_definition/` and `odr_conflict/` are committed fail-closed cases.
Their direct edges must remain unresolved and conflicting respectively, and
both project indexes must remain invalid.
