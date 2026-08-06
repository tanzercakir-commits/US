# Semantic-extension operations and phase gate

## Frozen scope

A6.7 freezes the combined A6 reference boundary at report/Semantic IR schema
`codeskeptic.semantic-verification/v6`. It covers fixed-width signed and
unsigned integers, bitwise/shift operations, owned fixed arrays, value structs,
proved local references, modular `modifies` frames, and proposal-only invariant
research. This gate does not add source semantics.

The combined slice is `examples/semantic_extensions_gate.cpp`. It exercises an
owned array, value record, mutable field reference, declaration-only framed
call, signed 64-bit arithmetic, unsigned bitwise arithmetic, and an annotated
loop in one translation unit. Explicit Z3 verifies all eight obligations. The
default affine/Z3 cross-check returns all eight as `unsupported`, proving that
a capable peer does not hide the affine backend's boundary.

## Backend capability matrix

| Feature | Homogeneous logic | `affine` | `z3` | default `both` |
| --- | --- | --- | --- | --- |
| signed `i32`/`i64` | QF_LIA | supported | supported and replayed | independently cross-checked |
| unsigned/bitwise/shift | QF_BV | unsupported | supported and replayed | unsupported |
| signed/unsigned owned arrays | QF_ALIA/QF_ABV | unsupported | supported and replayed | unsupported |
| value records | QF_RECORD/ALL | unsupported | supported and replayed | unsupported |
| proved local references | logic of the referent | only affine formulas | supported and replayed | unsupported when aggregate/BV-tainted |
| modular frames | logic of the framed values | only affine formulas | supported and replayed | unsupported when aggregate/BV-tainted |
| inferred invariants | research CHC/HORN | not a referee input | proposal generator only | ordinary VCs decide |

Every public violation still requires replay against its original obligation.
The gate embeds the fixed-integer phase result with 13 replayed violations and
pins every capable-backend feature report hash. `unknown`, `unsupported`, or a
solver error never promotes to `verified`.

## Fixture and migration evidence

The gate regenerates the current corpus twice in memory, compares the two byte
maps, then compares them with `fixtures/expected`. The frozen corpus contains
28 artifacts, including the combined semantic-extension IR/report pair.

The immutable v1 archive retains 16 checked hashes. The gate also reuses the
integer phase migration evidence: five v1, nine v2, ten v3, eleven v4, and
twelve v5 report cases remain status-equivalent to schema v6. Archived bytes
are read-only evidence; a hash mismatch fails the gate.

## Invariant proposal boundary

The A6.6 corpus remains isolated. The gate reproduces the committed research
artifact and requires both candidate paths to pass the ordinary referee:

- the useful candidate is machine-proposed, inductive, and accepted only after
  every ordinary obligation verifies;
- the insufficient candidate is machine-proposed and inductive, but its failed
  postcondition keeps it rejected;
- unsafe, timeout, unsupported, and malformed cases yield no accepted fact.

This remains a proposal-only research path. It is not imported by the normal
CLI, frontend, lowering, VC generator, or checker.

## Negative boundary

Five source probes freeze representative exclusions: pointers, variable-length
arrays, array-element references, mutable reference calls without an explicit
frame, and `short`. Each must produce only explicit `unsupported` results under
the default backend. Any verified, violated, unknown, or solver-error result is
a gate failure: unsupported constructs fail closed.

## Commands

Run the phase gates and reproducibility checks:

```powershell
python tools/semantic_extensions_phase_gate.py
python tools/invariant_research.py --check
python tools/integer_phase_gate.py
python tools/regenerate_fixtures.py --check
python -m unittest discover -s tests
```

The semantic-extension gate emits sorted JSON with schema
`codeskeptic.semantic-extensions-phase-gate/v0`. It contains no timestamps,
wall-clock durations, executable paths, or random data. Stable inputs and the
pinned Clang/Z3 configuration must produce identical bytes.

## Failure handling

A changed support summary, report/source hash, archive hash, migration status,
fixture byte, inference outcome, negative-boundary status, or replay count is
not refreshed casually. Diagnose the semantic difference first. If the change
is intentional, open a new PLAN stage, update consumer documentation and
fixtures together, preserve every archive, bump the test ratchet, and record
the evidence in `PROGRESS.md`.