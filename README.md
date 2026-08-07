# CodeSkeptic Semantic Verification Prototype

This repository is an isolated prototype for a small
`C++ -> Semantic IR -> verification conditions -> result` pipeline. It was
created after inspecting CodeSkeptic, but it does not modify or vendor the
CodeSkeptic repository.

The prototype deliberately supports C++17 `int`/`unsigned int` and `long
long`/`unsigned long long` (owned IR types `i32`/`u32`/`i64`/`u64`), `bool`,
local scalar state, fully initialized one-dimensional fixed-size integer
arrays with exact select/store/bounds, aggregate-by-value structs with exact
field/copy semantics, proved local lvalue references with exact live-target
reads and writes, declaration-only reference parameters with exact `modifies`
frames, fixed-width bitwise/shift expressions,
`if`/`else`,
direct contracted calls with matching fixed-width or value-record results, invariant-annotated
`while`, `assert`, and `return`. Unsupported C++ is reported explicitly. It
uses a real Clang AST and has no Python package dependencies. The affine
checker is dependency-free; the default cross-check backend also invokes a
separately installed Z3 executable through SMT-LIB2. Unsigned, mixed,
bitwise, shift, array, or record obligations require explicit `--backend z3` because
they use
homogeneous QF_BV/QF_ALIA/QF_ABV/QF_RECORD and the affine referee fails closed.

Run the vertical slice (the CLI defaults to affine/Z3 cross-check mode):

```powershell
python -m semantic_verifier examples/vertical_slice.cpp --format json
```

Select Z3-only or dependency-free affine mode explicitly:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp --backend z3
python -m semantic_verifier examples/vertical_slice.cpp --backend affine
```

Reuse exact obligation results from an opt-in local cache:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp `
  --backend both --cache .semantic-verifier-cache.json --format json
```

Bound each external solver process and the supported checks started per file:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp `
  --solver-timeout 5 --max-checks 100 --format json
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

The current suite contains 381 deterministic tests. The separately cloned
CodeSkeptic production track also passes all 914 tests on this machine.
Committed verifier fixtures are checked with:

```powershell
python tools/regenerate_fixtures.py --check
```

Export or check the cross-language native-adapter Semantic IR and obligation
JSON corpus:

```powershell
python tools/export_fixtures.py
python tools/export_fixtures.py --check
```

The [native-adapter manifest](fixtures/native_adapter/manifest.json) pins the
schema identity, source/IR/obligation paths, summaries, and SHA-256 hashes for
all 14 cases.

Run the deterministic scaling/cache/budget, fixed-width integer, and combined
semantic-extension phase gates:

```powershell
python tools/scaling_phase_gate.py --backend both
python tools/integer_phase_gate.py
python tools/semantic_extensions_phase_gate.py
```

Reproduce the isolated, proposal-only invariant-inference research artifact:

```powershell
python tools/invariant_research.py --check
```

Render or reproduce the deterministic offline contract-proposal prompt pack
(no model or network call is made):

```powershell
python tools/contract_proposal.py `
  --request fixtures/contract_proposals/request.json `
  --check fixtures/contract_proposals/expected.prompt.json
```

Pre-screen an untrusted response without mutating source:

```powershell
python tools/contract_proposal.py `
  --request fixtures/contract_proposals/screen.request.json `
  --response fixtures/contract_proposals/eligible.response.json `
  --check fixtures/contract_proposals/expected.pre-screen.json
```
Export a `cs: ai` review overlay, then audit a separately human-edited source:

```powershell
python tools/contract_proposal.py `
  --request fixtures/contract_proposals/screen.request.json `
  --response fixtures/contract_proposals/eligible.response.json `
  --review --overlay-output candidate.cpp --output review.json

python tools/contract_proposal.py `
  --request fixtures/contract_proposals/screen.request.json `
  --response fixtures/contract_proposals/eligible.response.json `
  --accepted-source fixtures/contract_proposals/accepted.cpp `
  --check fixtures/contract_proposals/expected.acceptance.json
```

The [contract-proposal loop](docs/contract_proposal_loop.md) defines the v1
request/response schemas, external-adapter boundary, logical identity, and
mandatory `cs: ai` provenance.
Run the frozen request → proposal → approval → implementation → verification
workflow:

```powershell
python tools/contract_first_workflow.py `
  --manifest fixtures/contract_first/task.json `
  --check fixtures/contract_first/expected.run.json
```

The [contract-first workflow](docs/contract_first_workflow.md) and
[task template](templates/contract_first_task.md) define the content-addressed
transition and human/referee trust boundaries.

The [guarded absolute pilot](pilots/contract_first/guarded_absolute/comparison.md)
applies that workflow to a verifier increment and freezes both the six-obligation
success report and a deterministic seeded-mismatch failure.

The [C++26 contracts bridge decision](docs/cpp26_contracts_bridge.md) freezes
the `pre`/`post`/`contract_assert` mapping, current compiler evidence, and
the fail-closed C3.1 source-bridge boundary. The implemented bridge accepts the
controlled standard spelling automatically. Its positive fixture is reproducible
with:

```powershell
python -m semantic_verifier fixtures/cpp26_contracts/verified.cpp
```

The [enforcement-ladder policy](docs/enforcement_ladder.md) fixes how all five
referee statuses route to proof completion, defect/infrastructure handling,
property-test generation, runtime guarding, or an explicit manual boundary.
Reproduce the committed property fallback with:

```powershell
python tools/generate_property_skeleton.py `
  fixtures/enforcement_ladder/property/square_bounded.cpp `
  --backend affine `
  --skeleton fixtures/enforcement_ladder/property/expected.property.cpp `
  --manifest fixtures/enforcement_ladder/property/expected.manifest.json `
  --check
```

See [the design document](docs/semantic_verification_prototype.md) for the
implemented boundary, examples, and limitations. The
[result/schema reference](docs/result_schema.md) defines machine-readable
fields and status semantics, the
[schema version policy](docs/schema_versioning.md) defines compatibility and
migration, the [changelog](CHANGELOG.md) records consumer-visible releases, and
the [adoption guide](docs/adoption_guide.md) gives a staged path into another
codebase. The
[Z3 backend decision record](docs/solver_decision.md) documents licensing,
packaging, timeouts, determinism, failure handling, model replay, and minimized
evidence cores. The [path-scaling decision](docs/path_scaling_decision.md)
records the measured exponential baseline and chosen exact merge architecture.
The [scaling operations runbook](docs/scaling_operations.md) defines the frozen
A5 phase gate and failure handling. The
[semantic extensions roadmap](docs/semantic_extensions_roadmap.md) fixes A6
ordering, trust boundaries, and per-stage acceptance requirements. The
[fixed-width integer decision](docs/integer_semantics_decision.md) selects the
homogeneous QF_LIA/QF_BV strategy and pinned C++17 target profile. Clang
validates that profile before any source is lowered; a mismatch fails closed. The
[invariant-inference research decision](docs/invariant_inference_decision.md)
records the isolated CHC/Spacer corpus, deterministic resource policy, measured
useful/insufficient outcomes, and untrusted-proposal boundary. The
[semantic-extension operations runbook](docs/semantic_extensions_operations.md)
freezes the combined A6 feature/capability matrix, fixture and migration
evidence, negative boundary, and phase-gate response.
The [signed int64 example](examples/int64_slice.cpp) covers widening, pinned
narrowing, arithmetic, modular calls, and loop invariants. The
[unsigned example](examples/unsigned_slice.cpp) covers modulo arithmetic,
usual conversions, unsigned comparison/division, calls, and loops. The
[bitwise example](examples/bitwise_slice.cpp) covers masks, mixed conversions,
32/64-bit shifts, arithmetic/logical right shift, and signed-left-shift safety.
The [array example](examples/array_slice.cpp) covers constant/symbolic reads,
whole-array SSA stores, isolation, signed bounds, and unsigned QF_ABV.
The [value-struct example](examples/struct_slice.cpp) covers construction, nested
field/array updates, copy isolation, by-value calls, and record contracts.
The [reference example](examples/reference_slice.cpp) covers scalar and whole-
record aliases, disjoint field references, writes, and branch-disjoint
lifetimes. The [frame-condition example](examples/frame_conditions.cpp) covers empty,
scalar, multiple, and nested record-field `modifies` summaries with exact
post-state constraints and preservation of unlisted fields.
The [combined integer gate](examples/fixed_integer_gate.cpp) carries positive
and negative evidence for the complete operator table; run all BV examples with
`--backend z3`. The [integer operations runbook](docs/integer_operations.md)
freezes the capability matrix and A6.12 gate commands.

## Development workflow

Work is planned and tracked in [PLAN.md](PLAN.md) (roadmap; never carries
status), [TODO.md](TODO.md) (active set) and [PROGRESS.md](PROGRESS.md)
(append-only ledger; the single source of truth for "done"). The session
protocol lives in [CLAUDE.md](CLAUDE.md).

After cloning, enable the guardrail hooks once:

```
git config core.hooksPath .githooks
```

The pre-commit hook runs the full test suite, enforces the test-count ratchet
(`guardrails/test_baseline.txt`), and requires PROGRESS.md to be staged
whenever code changes are committed. Commit messages must start with a plan
stage ID (e.g. `A1.2: ...`) or an allowed prefix.
