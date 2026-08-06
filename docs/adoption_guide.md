# Adoption Guide

## Purpose

This guide introduces the semantic verifier into another codebase without
expanding its soundness claim. The verifier is a deterministic referee for a
restricted C++ subset. It is not a replacement for compilation, tests,
sanitizers, static analysis, review, or production certification.

The central adoption rule is fail-closed:

- `verified` is success only for the exact emitted obligation;
- `violated` is actionable only after its counterexample has replayed;
- `unknown`, `unsupported`, and `solver_error` are never success;
- loop termination remains a separate explicit non-goal.

## Prerequisites

Before adoption, pin or document:

- Python 3.11 or newer;
- a Clang executable that supports JSON AST output;
- Z3 for the default `both` backend, or an explicit decision to use the weaker
  dependency-free `affine` backend;
- the verifier commit and `schema` identifier;
- the source paths/functions allowed into the initial subset;
- the CI owner responsible for `unknown`, `unsupported`, and `solver_error`.

Run the reference baseline first:

```powershell
git config core.hooksPath .githooks
python -m unittest discover -s tests
python tools/regenerate_fixtures.py --check
```

Do not begin an adoption while the baseline is red.

## Recommended rollout

### 1. Observe without gating

Run the verifier in CI on a small, explicit file list and retain JSON output as
an artifact. Do not block merges yet. Measure:

- how many obligations are produced;
- status counts by file/function/kind;
- unsupported source constructs;
- runtime and solver timeouts;
- counterexample usefulness.

Use the default cross-check backend:

```powershell
python -m semantic_verifier path/to/pilot.cpp `
  --backend both --format json > semantic-report.json
```

Shell redirection is illustrative; CI should also preserve stderr and the
process exit code.

### 2. Freeze the pilot subset

Create an allow-list of functions/files that already stay inside the supported
boundary. Unsupported code must remain visible rather than being silently
dropped. Keep pointers, references, arrays, records, globals, macros, indirect
calls, unsupported loops, and other excluded constructs outside the pilot.

Pin representative inputs and outputs as fixtures. Regenerate twice and compare
bytes before accepting a schema or lowering change.

### 3. Add contracts incrementally

Start with boundary contracts that are easy to review:

```cpp
// cs: requires amount >= 0
// cs: requires balance >= amount
// cs: ensures result >= 0
int withdraw(int balance, int amount);
```

For modular result reasoning, an assigned int result is havoced and then
constrained by the callee's `ensures`. A visible body without `ensures` does not
grant a return-value fact to its caller.

For while loops, attach a contiguous invariant block immediately before the
loop:

```cpp
// cs: invariant i >= 0 && i <= n
while (i < n) {
    i = i + 1;
}
```

Review invariants as specifications. The verifier proves entry and inductive
preservation and uses `I && !condition` after the loop; it does not infer an
invariant or prove termination.

### 4. Gate only stable categories

After an observation period, a conservative merge gate is:

- fail on process exit `1` (`violated`);
- fail on process exit `3` (`solver_error`);
- fail or require an explicit waiver on exit `2` (`unknown`/`unsupported`);
- accept exit `0` only while also reviewing top-level `non_goals`.

Never rewrite exit `2` to success globally. If a temporary waiver is necessary,
scope it to an exact obligation kind/location and give it an owner and expiry.

### 5. Expand one semantic feature at a time

For each new source construct:

1. state its exact semantics and unsupported boundary;
2. extend owned IR before checker logic;
3. add positive, violation, and fail-closed tests;
4. add 32-bit/undefined-behavior safety obligations where required;
5. advance the test-count ratchet deliberately;
6. regenerate fixtures twice and review the byte diff;
7. update schema/version documentation before consumers depend on fields.

Do not widen parser acceptance without adding the corresponding semantic and
VC rules.

## CI integration

A minimal observation job can follow this shape:

```yaml
- name: Verify pilot
  shell: pwsh
  run: |
    python -m semantic_verifier src/pilot.cpp --backend both --format json |
      Set-Content -Encoding utf8 semantic-report.json

- name: Upload verifier report
  uses: actions/upload-artifact@v7
  if: always()
  with:
    name: semantic-verification
    path: semantic-report.json
```

Preserve the verifier exit code if the job is intended to gate. Some pipelines
lose the first command's status when output is piped; capture and restore it
explicitly for that shell.

For the reference repository, `.github/workflows/determinism.yml` is the model
for full-suite plus two-run fixture comparison.

## Result triage

### `verified`

Confirm the obligation kind and non-goals before interpreting the result. A
verified postcondition does not imply loop termination, memory safety outside
the modeled subset, or correctness of an unsupported caller.

### `violated`

The reported model has replayed against the original obligation. Reproduce with
the same verifier/solver versions, inspect versioned variables in the obligation,
and decide whether to fix source code or correct an inaccurate contract. Do not
weaken a soundness test merely to remove the violation.

### `unknown`

Separate affine incompleteness from Z3 `unknown`/timeout. Re-run with
`--backend z3` when the affine-only backend is the cause. If Z3 times out, reduce the pilot
or investigate the formula; increasing timeouts is an explicit operational
decision, not proof.

### `unsupported`

Read `unsupported_reason` and either narrow the pilot, refactor to the supported
subset, or implement the construct through the full IR/VC/test process. Never
approximate the construct in an adapter.

### `solver_error`

Treat as an infrastructure or soundness incident. Check Z3 discovery/version,
stderr, timeout configuration, model parsing/replay, and cross-backend alarms.
Do not retry until green and then discard the failed report without review.

## Counterexamples and data handling

Counterexamples contain source/SSA variable names and concrete int/bool values.
They are deterministic proof evidence, but may still expose sensitive business
inputs in logs or CI artifacts. Apply the target repository's retention and
access policy. Relevance projection and minimization are later roadmap items;
current models may contain more bindings than a human needs.

## Schema and fixture discipline

- Check `schema` before consuming fields.
- Join results to obligations by ID.
- Treat unknown status/kind values conservatively.
- Ignore unknown object fields during v0 evolution, but never ignore an unknown
  status as success.
- Keep golden fixture bytes under review and forced to LF.
- Use `python tools/regenerate_fixtures.py --check` in CI.

See [the field reference](result_schema.md) for every report and Semantic IR
field. Schema-breaking decisions and migration windows belong to the version
policy, not an ad hoc consumer workaround.

## Native CodeSkeptic path

For a production C++ integration, keep the stable seam:

```text
ASTContext -> SemanticLowerer -> owned Semantic IR -> VC generator
           -> checker backend -> VerificationResult -> reporter adapter
```

Begin with a test-only ASTContext-to-IR adapter. Compare its output byte-for-byte
against the Python fixture subset before adding a native solver or production
reporter. Reuse CodeSkeptic's compile database, source mapping, contract
attachment, diagnostics, and test harness; do not turn its specialized
DataflowEngine into the persistent Semantic IR.

## Adoption completion checklist

- [ ] Tool, Clang, Z3, and schema versions are pinned/documented.
- [ ] Baseline suite and fixture check are green.
- [ ] Pilot source list is explicit and reviewed.
- [ ] Unsupported constructs are visible and owned.
- [ ] Contracts/invariants have source-code reviewers.
- [ ] Status and exit-code policy is documented in CI.
- [ ] Non-goals are retained in reports and release evidence.
- [ ] Counterexample artifacts follow data-retention policy.
- [ ] Fixture/schema changes require compatibility review.
- [ ] AI may propose contracts or patches but never decides proof status.
