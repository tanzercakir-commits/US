# CodeSkeptic Semantic Verification Prototype

This repository is an isolated prototype for a small
`C++ -> Semantic IR -> verification conditions -> result` pipeline. It was
created after inspecting CodeSkeptic, but it does not modify or vendor the
CodeSkeptic repository.

The prototype deliberately supports C++17 `int`/`unsigned int` and `long
long`/`unsigned long long` (owned IR types `i32`/`u32`/`i64`/`u64`), `bool`,
local state, assignment, fixed-width bitwise/shift expressions, `if`/`else`,
direct contracted calls with matching fixed-width results, invariant-annotated
`while`, `assert`, and `return`. Unsupported C++ is reported explicitly. It
uses a real Clang AST and has no Python package dependencies. The affine
checker is dependency-free; the default cross-check backend also invokes a
separately installed Z3 executable through SMT-LIB2. Unsigned, mixed,
bitwise, or shift obligations require explicit `--backend z3` because they use
homogeneous QF_BV and the affine referee fails closed.

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

The current suite contains 226 deterministic tests. The separately cloned,
unmodified CodeSkeptic reference also passes all 811 tests on this machine.
Committed fixtures are checked with:

```powershell
python tools/regenerate_fixtures.py --check
```

Run the deterministic scaling/cache/budget phase gate:

```powershell
python tools/scaling_phase_gate.py --backend both
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
validates that profile before any source is lowered; a mismatch fails closed.
The [signed int64 example](examples/int64_slice.cpp) covers widening, pinned
narrowing, arithmetic, modular calls, and loop invariants. The
[unsigned example](examples/unsigned_slice.cpp) covers modulo arithmetic,
usual conversions, unsigned comparison/division, calls, and loops. The
[bitwise example](examples/bitwise_slice.cpp) covers masks, mixed conversions,
32/64-bit shifts, arithmetic/logical right shift, and signed-left-shift safety;
run both with `--backend z3`.

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
