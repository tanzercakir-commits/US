# Fixed-Width Integer Operations and Phase Gate

## Frozen scope

A6.12 freezes the reference implementation's C++17 fixed-width integer phase.
The accepted target profile is
`codeskeptic.cxx17-fixed-integers/i32-u32-i64-u64-twos-complement-arshift/v0`:
8-bit bytes, 32-bit `int`/`unsigned int`, 64-bit `long long`/`unsigned long
long`, two's-complement signed conversions, and arithmetic negative signed
right shift. Clang validates the profile before lowering.

The owned IR types are `i32`, `u32`, `i64`, and `u64`. `bool` promotes to
`i32`. The usual arithmetic conversion table is:

| Left/right | `i32` | `u32` | `i64` | `u64` |
| --- | --- | --- | --- | --- |
| `i32` | `i32` | `u32` | `i64` | `u64` |
| `u32` | `u32` | `u32` | `i64` | `u64` |
| `i64` | `i64` | `i64` | `i64` | `u64` |
| `u64` | `u64` | `u64` | `u64` | `u64` |

## Operation and definedness matrix

| Family | Exact semantics | Generated safety condition | Solver lane |
| --- | --- | --- | --- |
| signed `+`, `-`, `*` | Mathematical result at the owned width | Signed range; widened `signed_no_overflow` when BV-tainted | QF_LIA unless BV-tainted |
| unsigned `+`, `-`, `*`, unary `-` | Modulo `2^width` | None | QF_BV |
| signed unary `-` | Mathematical negation | Operand is not the type minimum | QF_LIA unless BV-tainted |
| `/`, `%` | C++17 truncation toward zero; unsigned quotient/remainder | Divisor nonzero; signed minimum with `-1` excluded | QF_LIA for eligible literal-divisor formulas, otherwise QF_BV when unsigned-tainted |
| equality/order | Usual conversions, then signed or unsigned comparison | None beyond conversion | QF_LIA unless unsigned/bitwise/shift-tainted |
| `~`, `&`, `|`, `^` | Fixed-width bit pattern after promotions/conversions | None | QF_BV |
| `E1 << E2` | Promoted-left width; unsigned modulo; pinned C++17 signed rule | `0 <= E2 < width`; signed-left value is nonnegative and representable in the corresponding unsigned type | QF_BV |
| `E1 >> E2` | Logical for unsigned; pinned arithmetic shift for negative signed | `0 <= E2 < width` | QF_BV |

Every candidate violation is replayed against its original obligation before
its public binding core is minimized. A failed `shift_count` or
`signed_left_shift` obligation is undefined behavior; a wrapped SMT value after
that failure is not a C++ result.

## Backend capability matrix

| Query | `affine` | `z3` | `both` |
| --- | --- | --- | --- |
| supported signed QF_LIA | supported | supported | independently cross-checked |
| QF_BV required | `unsupported` | supported with mandatory replay | `unsupported` (capable peer never hides unsupported) |

The classifier emits one homogeneous query. QF_LIA uses only SMT `Int`; QF_BV
uses only fixed-size bitvectors for integer terms. No query mixes the sorts.
Use explicit `--backend z3` for unsigned, mixed-to-unsigned, bitwise, or shift
formulas.

## Deterministic phase gate

Run the complete frozen gate and fixture check:

```powershell
python tools/integer_phase_gate.py
python tools/regenerate_fixtures.py --check
python -m unittest discover -s tests
```

The gate emits sorted JSON with schema
`codeskeptic.fixed-integer-phase-gate/v2`. It records:

- the profile ranges, complete 4-by-4 conversion table, and conversion samples;
- QF_LIA/QF_BV classifier query hashes and the backend capability matrix;
- positive and negative evidence for all eight operator truth-table rows;
- the combined slice's source/report hashes, summary, and replay count;
- all 16 immutable v1, 28 immutable v2, and 31 immutable v3 archive
  hashes, plus five v1-to-v4, nine v2-to-v4, and ten v3-to-v4
  status-equivalent cases.

Two renders with the same Clang/Z3 configuration must be byte-identical. The
fixture generator is independently run twice by the test suite and must produce
the same 22 artifact byte set. Any count, hash, status, lane, or capability
change is a phase-gate failure requiring an intentional new plan stage.

## Unsupported boundary

`long`, `short`, `char`, enums, extended integers, compound assignments,
increment/decrement, rotates, `<bit>` helpers, and implicit target choices remain
unsupported. They must not be approximated with the frozen operations above.
