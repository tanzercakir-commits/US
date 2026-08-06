# Fixed-Width Integer Semantics Decision

## Decision

Use a typed, per-obligation homogeneous dual encoding:

- QF_LIA for signed arithmetic obligations that need no modulo, bitwise, or
  shift semantics;
- QF_BV for every obligation containing unsigned arithmetic, mixed signedness
  that converts to unsigned, bitwise operators, or shifts;
- never mix SMT `Int` and `BitVec` sorts in one emitted query.

The Semantic IR owns signedness and width independently of either encoding.
The classifier is deterministic and part of the backend/cache identity. This
keeps the existing affine and Z3 cross-check path for its exact LIA fragment
while using bitvectors where fixed-width bit patterns are the semantics.

This is a C++17 target-profile decision, not a claim about every conforming C++
implementation. The reference frontend already invokes `-std=c++17`.

## Pinned target profile

The initial profile is
`codeskeptic.cxx17-fixed-integers/i32-u32-i64-u64-twos-complement-arshift/v0`:

| Source spelling | IR type | Width | Range |
| --- | --- | ---: | --- |
| `bool` | `bool` | 1 logical | `false`, `true` |
| `int`, `signed int` | `i32` | 32 | `-2147483648` to `2147483647` |
| `unsigned`, `unsigned int` | `u32` | 32 | `0` to `4294967295` |
| `long long`, `signed long long` | `i64` | 64 | `-9223372036854775808` to `9223372036854775807` |
| `unsigned long long` | `u64` | 64 | `0` to `18446744073709551615` |

`char`, `short`, `long`, extended integers, enums, and library aliases such as
`std::int64_t` remain unsupported. In particular, `long` is rejected because
its width differs between common LP64 and LLP64 targets.

Before accepting these types, A6.8 must make Clang validate the profile: 8-bit
bytes, 32-bit `int`, 64-bit `long long`, arithmetic signed right shift, and the
chosen two's-complement results for out-of-range conversions to signed i32/i64.
Failure is a structured frontend/profile error, never fallback semantics.

The C++17 draft makes unsigned arithmetic modulo the width and permits multiple
signed representations ([N4659 `basic.fundamental`](https://timsong-cpp.github.io/cppwp/n4659/basic.fundamental)).
It also makes an out-of-range conversion to a signed destination
implementation-defined ([N4659 `conv.integral`](https://timsong-cpp.github.io/cppwp/n4659/conv.integral)).
The pinned profile resolves those implementation choices explicitly.

## Serialized type and value policy

A6.8 introduces report/IR schema v2. Expression and symbol types use the stable
identifiers `bool`, `i32`, `u32`, `i64`, and `u64`; the v1 string `int` is not
overloaded with implicit width. Every serialized fixed-width integer constant
and counterexample binding uses a canonical base-10 string, including i32.
Booleans remain JSON booleans, while counts/locations remain JSON numbers.
Decimal strings avoid loss in consumers whose JSON number type cannot represent
all u64 values. Internal Python values remain integers.

The complete v1 fixture corpus is archived unchanged before current fixtures
move to v2. Mixed report/IR majors are rejected. There is no in-place cache
migration: report schema and typed expressions change semantic keys, so old
entries miss and recompute.

## Promotions and usual arithmetic conversions

Clang's resolved operand types are authoritative only after they pass the
pinned profile. `bool` promotes to `i32`. The common type table is symmetric:

| Left/right | `i32` | `u32` | `i64` | `u64` |
| --- | --- | --- | --- | --- |
| `i32` | `i32` | `u32` | `i64` | `u64` |
| `u32` | `u32` | `u32` | `i64` | `u64` |
| `i64` | `i64` | `i64` | `i64` | `u64` |
| `u64` | `u64` | `u64` | `u64` | `u64` |

Operands are sign-extended, zero-extended, or truncated to the selected type
before the operator. Equality and relational operators use the same conversion;
the final comparison is signed for `i32`/`i64` and unsigned for `u32`/`u64`.

Assignment/return/argument conversion follows this table:

| Destination | Source value rule |
| --- | --- |
| `bool` | zero is false; every nonzero supported integer is true |
| `u32`, `u64` | unique value congruent modulo `2^width` |
| `i32`, `i64`, in range | value unchanged |
| `i32`, `i64`, out of range | modulo `2^width`, interpreted as the pinned two's-complement signed value |

The last row is target-profile behavior for C++17's implementation-defined
case. It is not a signed-arithmetic overflow rule.

Integer literal spelling is parsed by Clang; only literals whose resolved type
maps to the table are accepted. Decimal, hexadecimal, octal, and binary forms
and `u`, `ll`, and `ull` suffixes are allowed when the resolved value/type is
supported. Floating, character, user-defined, 128-bit, and unsupported-rank
literals fail closed. The i64 minimum should be written using a representable
expression such as `-9223372036854775807LL - 1`, not by retagging an oversized
positive literal.

## Operator truth table

| Operator family | Exact C++17/profile rule | Required VC |
| --- | --- | --- |
| signed `+`, `-`, `*` | mathematical result in signed range | lower/upper representability |
| unsigned `+`, `-`, `*` | result modulo `2^width` | none beyond operand well-formedness |
| unary `-` | signed mathematical negation; unsigned modulo | signed operand is not minimum |
| `/`, `%` | signed or unsigned quotient/remainder after conversions | divisor nonzero; signed minimum divided/remaindered by `-1` rejected |
| `==`, `!=`, `<`, `<=`, `>`, `>=` | usual conversions, then signed/unsigned comparison | none beyond conversion well-formedness |
| `~`, `&`, `|`, `^` | bitwise result after promotions/usual conversions | none beyond operand well-formedness |
| `E1 << E2` | promoted-left result type; unsigned modulo; signed C++17/profile rule | `0 <= E2 < width`; signed `E1 >= 0` and shifted value representable in corresponding unsigned type |
| `E1 >> E2` | logical for unsigned/nonnegative; pinned arithmetic shift for negative signed | `0 <= E2 < width` |

The C++17 shift rules, including undefined counts, conditional signed left
shift, and implementation-defined negative signed right shift, are stated in
[N4659 `expr.shift`](https://timsong-cpp.github.io/cppwp/n4659/expr.shift).
Bitwise operations use the converted operands' binary representation, as in
[N4659 `expr.bit.and`](https://timsong-cpp.github.io/cppwp/n4659/expr.bit.and).

Compound assignments, increment/decrement, rotates, `<bit>` library functions,
and implicit narrowing beyond the explicit conversion paths above remain
unsupported until separately planned.

## SMT lanes and replay

### QF_LIA lane

All integer symbols emit as SMT `Int`, with type ranges and the existing
definedness obligations. A6.9 parameterizes those rules for i32/i64. The affine
backend remains eligible, and default `both` continues independent cross-check.

### QF_BV lane

All fixed-width integer symbols in the obligation emit as `(_ BitVec width)`.
Constants, extensions, truncation, arithmetic, signed/unsigned comparisons,
and bitwise/shift operations use the SMT-LIB fixed-size bitvector theory. The
theory defines modulo arithmetic, signed/unsigned interpretations, conversions,
and overflow predicates ([SMT-LIB `FixedSizeBitVectors`](https://smt-lib.org/theories-FixedSizeBitVectors.shtml)).
Z3 supplies distinct signed and unsigned comparisons and warns that mixed
integer/bitvector reasoning has overhead ([Z3 bitvector guide](https://microsoft.github.io/z3guide/docs/theories/Bitvectors/)); the homogeneous policy avoids that combination.

The Z3 model parser accepts only width-matching canonical bitvector values and
converts them to source-level signed/unsigned Python integers before replay.
Replay evaluates the original typed obligation, including modulo and conversion
rules, before public minimization. A width, sort, range, or replay mismatch is
`solver_error`.

The affine backend returns explicit `unsupported` for BV-required obligations.
Under the unchanged fail-closed cross-check policy, default `both` therefore
also returns `unsupported`; users must select `--backend z3` explicitly for BV
features. No capable backend is silently substituted for an unsupported peer.

## Rejected alternatives

- Pure mathematical integers for bitwise/unsigned operations would require a
  second hand-built bit semantics and modulo engine in the trusted path.
- Pure QF_BV for every legacy obligation would discard affine cross-checking and
  force an unnecessary schema/solver behavior change on existing arithmetic.
- Mixed `Int`/`BitVec` queries add conversion complexity and solver overhead at
  every boundary; per-obligation homogeneous lowering is simpler to audit.
- Treating signed overflow as wrap is unsound for C++17 arithmetic.
- Leaving signed narrowing/right shift "implementation-defined" at runtime
  makes reports target-ambiguous; the validated profile fixes or rejects them.
- Letting default cross-check select Z3 when affine is unsupported violates the
  repository rule that unsupported never promotes to verified.

## Implementation stages selected

- A6.8: fixed-width type profile and schema v2;
- A6.9: signed int64 QF_LIA lane;
- A6.10: unsigned integers and homogeneous QF_BV lane;
- A6.11: C++17 bitwise and shift operators;
- A6.12: fixed-width integer phase gate.

Arrays begin only after A6.12, so their index/value types consume the frozen
typed IR and backend classifier instead of creating a second type decision.
