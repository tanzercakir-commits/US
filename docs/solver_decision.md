# Z3 Backend Decision Record

Status: accepted for the Python reference implementation (A1, 2026-08-06).

## Decision

Use Z3 as an optional external executable through deterministic SMT-LIB2
stdin/stdout. Keep the dependency-free affine checker available and run it
alongside Z3 by default in the CLI. Do not link a solver library and do not add
a Python package dependency.

The accepted backend modes are:

- `affine`: dependency-free, exact where it decides, deliberately incomplete;
- `z3`: complete for emitted homogeneous QF_LIA, QF_BV, QF_ALIA, QF_ABV, and QF_RECORD
  fragments;
- `both` (CLI default): run both and report a `solver_error` soundness
  alarm if their definitive (`verified`/`violated`) answers disagree.

Z3 is developed by Microsoft Research and distributed under the
[MIT license](https://github.com/Z3Prover/z3/blob/master/LICENSE.txt). The
[official project](https://github.com/Z3Prover/z3) publishes pre-built stable
and nightly binaries and documents source builds. This repository invokes only
the executable; it does not redistribute Z3 or its language bindings.

## Why a subprocess

The subprocess boundary preserves the repository's zero-package-dependency
policy and keeps the eventual C++ production adapter independent of Python
binding APIs. SMT-LIB2 is deterministic, inspectable, fixture-friendly, and
portable across the Python lab and the C++17 production track.

Rejected alternatives:

- affine checker only: sound but cannot prove ordinary transitive facts;
- `z3-solver` Python package: adds a package and native-wheel dependency;
- linked C/C++ API: adds build-system, ABI, and per-platform linker coupling;
- a general first-order-logic encoding: unnecessary and less predictable for
  the current quantifier-free LIA/BV fragments.

## Supported logic and query semantics

The query classifier selects one homogeneous lane per obligation. Signed-only
formulas emit QF_LIA with `i32`/`i64` as `Int`; widening, pinned narrowing,
literal multiplication, and literal-divisor C++ quotient/remainder are exact.
Variable multiplication or division/remainder in a signed-only logical formula
fails closed. Any `u32`/`u64` taint or bitwise/shift operator selects QF_BV and
emits every fixed-width term as `(_ BitVec 32|64)`. That lane supports modulo
arithmetic, variable multiplication, signed/unsigned division/remainder and
comparisons, complement/and/or/xor, logical/arithmetic shifts, sign/zero
extension, same-width reinterpretation, and truncation. It never declares an
`Int`. Signed-result `+`, `-`, and `*` safety in this lane uses a widened
`sign_extend` equality, not a tautological comparison of an already wrapped
term. Shift counts receive exact range VCs; signed left shift uses a
zero-extended double-width representability equality, and signed right shift
selects `bvashr` under the pinned profile. Source division/remainder receives
exact nonzero VCs in both lanes and signed minimum/-1 VCs where applicable.
Owned-array obligations are classified as QF_ARRAY. Signed-only array formulas
emit QF_ALIA with `(Array Int Int)`; unsigned or bitwise taint emits QF_ABV with
64-bit bitvector indices and element-width bitvectors. Array literals are
deterministic const/store terms, every access has a separate bounds VC, and
models are materialized to the declared owned length before replay. Malformed
types and unknown expression kinds fail closed before Z3 starts.

Value-record obligations are classified as QF_RECORD and use deterministic SMT
datatypes under `(set-logic ALL)`. Nested record declarations are emitted
inner-first. Their scalar and array leaves stay homogeneous: signed-only records
use `Int`/Int-array terms; unsigned or bitwise taint uses width-matched
bitvectors. `project` uses selectors and `update` reconstructs the datatype,
which preserves whole-value copy isolation. Model constructors decode to exact
typed records and replay recursively before violation evidence is accepted.

The affine backend rejects every BV-, array-, or record-required obligation. Default `both` also
returns explicit `unsupported` under the cross-check policy; users must select
`--backend z3` for unsigned, mixed, bitwise, shift, array, or record formulas. The Z3/cache identity pins the
homogeneous lane policy so earlier referee results cannot alias it.

For a validity obligation, assumptions are asserted together with the negated
conclusion. `unsat` means `verified`; `sat` is only a candidate violation until
its model replays. For a satisfiability obligation, assumptions are asserted
directly: `sat` means the requirements are feasible and `unsat` means they are
infeasible.

## Discovery and packaging

Discovery order is fixed:

1. explicit `--z3 PATH`;
2. `SEMANTIC_VERIFIER_Z3`;
3. `z3` on `PATH`;
4. platform-known locations.

The program checks that the candidate is a file. Launch failure is still
captured as `solver_error`; discovery never terminates the verification
pipeline with an uncaught configuration exception.

The reference machine pins Z3 5.0.0. The
[official release page](https://github.com/Z3Prover/z3/releases) provides
Windows, Linux glibc, and macOS archives with published SHA-256 digests. Pin a
version and verify its digest in CI or packaged deployments; do not depend on a
moving nightly asset.

Platform layout:

- Windows: extract the official `x64-win`/`arm64-win` archive. The reference
  user install is
  `%LOCALAPPDATA%\Programs\z3-5.0.0-x64-win\bin\z3.exe`, selected through
  `SEMANTIC_VERIFIER_Z3`. Known fallbacks are
  `%LOCALAPPDATA%\Programs\z3-*\bin\z3.exe`,
  `%ProgramFiles%\Z3\bin\z3.exe`, and `C:\z3\bin\z3.exe`.
- Linux: use the matching official glibc archive or a pinned distribution
  package. Put `z3` on `PATH` or set `SEMANTIC_VERIFIER_Z3` to its absolute
  path. Known fallbacks are `/usr/local/bin/z3` and `/usr/bin/z3`.
- macOS: use the matching official arm64/x64 archive or a pinned package.
  Put `z3` on `PATH` or set the environment variable. Known fallbacks are
  `/opt/homebrew/bin/z3`, `/usr/local/bin/z3`, and `/usr/bin/z3`.

The upstream build documentation installs executables under `PREFIX/bin`,
normally `/usr` on Linux and `/usr/local` on macOS. Release archives are the
preferred cross-platform pin because their version and checksum are explicit.

## Timeout and failure taxonomy

Default CLI timeout: 5 seconds per solver process, configurable with
`--solver-timeout SECONDS`. A validated `SolverTimeout` requires a positive
finite value. The runner passes `timeout=<milliseconds>` to Z3 and applies the
same bound to the host subprocess. Z3's
[parameter reference](https://microsoft.github.io/z3guide/programming/Parameters/)
defines `timeout` in milliseconds.

Result mapping is exact:

| Solver/process result | Validity | Satisfiability |
| --- | --- | --- |
| `unsat` | `verified` | `violated` (infeasible requirements) |
| `sat` | replayed `violated` candidate | `verified` |
| `unknown` | `unknown` | `unknown` |
| host timeout | `unknown` | `unknown` |
| non-zero exit or malformed output | `solver_error` | `solver_error` |
| missing/unlaunchable executable | `solver_error` | `solver_error` |

No `unknown`, timeout, unsupported formula, parse failure, configuration
failure, or crash can become `verified`. A timeout while requesting the full
countermodel is `unknown`, because no replayable violation evidence exists yet.
A timeout in later greedy minimization keeps the already replayed definitive
violation and the binding whose removal could not be proved. Cross-check mode
propagates a timeout as resource-exhaustion `unknown` instead of selecting a
peer `verified` result.

The independent `--max-checks N` file budget counts supported top-level
obligations in source order. It is not a wall-clock solver setting: zero starts
none, omission is unlimited, and exhausted obligations are explicit `unknown`.
Unsupported obligations do not consume a supported-check unit. The wrapper is
outside the persistent cache and cross-check backend, so cache hits cannot evade
the limit and checking both referees remains one top-level unit.

## Determinism policy

Every invocation uses a shell-free argument vector with:

```text
-in
-smt2
timeout=<ceil(seconds * 1000)>
smt.random_seed=0
sat.random_seed=0
parallel.enable=false
```

The parameter guide documents the SMT and SAT random seeds and the parallel
solver switch. The emitter sorts declarations, uses a fixed operator spelling,
and terminates every query with one newline. Re-emitting an obligation is
byte-identical.

Z3 may choose a different but valid model across solver versions. Therefore
model byte text and exact values are golden only for a pinned solver version.
The portable serialization contract is sorted source-level binding keys, and
every binding set must pass replay.

## Model parsing, replay, and public minimization

Models are requested in a second deterministic run only after the first run
returns `sat`. This avoids asking Z3 for a model after `unsat`, which Z3 reports
as an error.

The parser accepts only zero-arity `define-fun` entries with `Int`, `Bool`, or
width-matching `BitVec` values. Bitvectors decode to source signedness before
replay. It rejects quoted/unknown symbols, functions with arguments, unknown
sorts, width/range mismatches, non-literal values, duplicates, missing or
unexpected bindings, and malformed S-expressions.

SMT symbols use an injective reversible codec. SSA names remain readable
(`y#0` becomes `y_v0`); underscores, scopes, Unicode, numeric-leading names,
and reserved symbols are escaped without collisions. Parsed bindings are
decoded to their exact Semantic IR identities.

Before a validity result becomes `violated`, every parsed binding is replayed
through the existing evaluator against the original obligation:

1. every assumption must evaluate to true;
2. the conclusion must evaluate to false;
3. evaluation must complete without missing names or partial-operation errors.

Any mismatch becomes `solver_error`. Only then does deterministic relevance
projection seed a variable cone from the conclusion and close it transitively
through co-occurrence in assumptions. Bindings outside the cone are discarded;
greedy minimization tries the rest in sorted Semantic IR name order. A binding
is removed only if a second exact validity query proves that the original
assumptions plus the retained equalities imply the negated conclusion.
Unknown/error results keep the in-cone binding. The retained core is projected
to human-facing names and serialized
in sorted-key order by `VerificationResult.to_dict()`; it may be empty and is
not independently replayable without the obligation assumptions. Raw solver
stdout and the complete replay model remain internal and are not trusted as the
public counterexample.

## Operational verification

Run the Z3 backend and cross-check mode with:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp --backend z3
python -m semantic_verifier examples/vertical_slice.cpp --backend both
python -m semantic_verifier examples/unsigned_slice.cpp --backend z3
python -m semantic_verifier examples/bitwise_slice.cpp --backend z3
python tools/integer_phase_gate.py
python -m unittest tests.test_z3_backend tests.test_backend tests.test_smtlib_bv
```

On the accepted Z3 5.0.0 reference setup, the vertical slice produces
10 verified and 2 replayed violations with zero unknown, unsupported, solver
error, or backend disagreement results. The fixed-width phase gate additionally
freezes QF_LIA as verified by affine/Z3/both and QF_BV as verified only by
explicit Z3, with affine/both remaining `unsupported`.
