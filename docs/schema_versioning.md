# Schema Version Policy

## Decision

The wire identifier has one explicit major component:

```text
codeskeptic.semantic-verification/vMAJOR
```

The current value is `codeskeptic.semantic-verification/v4`. F4.1 froze the
report and Semantic IR contract as v0; A4.1 advanced to v1 for minimized public
counterexample evidence; A6.8 advances to v2 for explicit fixed-width types and
canonical integer evidence, A6.2 advances to v3 for owned arrays, and A6.3
advances to v4 for value records. A producer emits exactly one major version; there
is no implicit negotiation or fallback.

The fixture-corpus manifest has its own namespace
(`codeskeptic.fixture-corpus/v0`) and versions independently from the report/IR
schema. A6.12 added `codeskeptic.fixed-integer-phase-gate/v0`; A6.2 advanced
that evidence schema to v1. A6.3 advances it to v2 so it also pins the v3
archive plus v1-to-v4, v2-to-v4, and v3-to-v4 migration checks. Changing its frozen profile, conversion
table, operator rows, backend matrix, or migration checks requires an
intentional gate version review, not a report-schema reinterpretation.

## Why v0 is not bumped retroactively

A2.1 introduced result-bearing call fields (`target` and `result_type`), and A3
introduced loop nodes plus top-level termination non-goals. Either change would
be a major-version candidate after a compatibility baseline exists: an old
consumer could otherwise treat a result-bearing call as a side-effect-only call
or ignore the fact that loop termination was not checked.

Those changes predated the field reference, golden corpus, determinism CI, and
this freeze decision. They are therefore batched into the initial v0 baseline
rather than causing a retrospective v1 with no preserved pre-change fixture
contract. From this commit forward, the same changes require the review and
migration process below.

## v1 decision: minimized public counterexample evidence

A4.1 changes the public `counterexample` from a complete replayable assignment
to a deterministic minimized binding core. The referee still obtains and
replays the complete concrete model internally. It then removes a binding only
when exact reasoning proves that the original obligation assumptions plus the
remaining equalities imply the negated conclusion.

Keeping this meaning under v0 was rejected. An old v0 consumer can reasonably
replay the public object as a complete assignment; a v1 core may be partial or
empty and must instead be interpreted with the referenced obligation
assumptions. Adding an optional diagnostic field or retaining both public forms
would not make changing the existing `counterexample` meaning safe and would
unnecessarily expose the noisy complete model.

The five-case v0 corpus is preserved byte-for-byte under
`fixtures/versions/v0/`. Current fixtures are regenerated as v1. The public
`require_current_schema` gate is the reference compatibility check; it rejects
unknown report majors and mixed report/Semantic IR schemas.

A4.3 adds the optional diagnostic `trace` result field within v1. It is safe for
a v1 consumer to ignore: branch explanations do not change the obligation,
status, replay requirement, or counterexample-core meaning. Results without a
violated source-branch path omit the field, so the then-current five-case v1
fixture corpus remained byte-identical. An equivalent change that altered proof
meaning or existing fixture bytes would require a new major review.

## v2 decision: fixed-width type identities and integer evidence

A6.8 replaces the implicit v1 `int` identity with schema-owned `i32`, and
reserves `u32`, `i64`, and `u64` alongside distinct `bool`. Every serialized
fixed-width integer constant and counterexample binding becomes canonical
base-10 text. Internal values remain integers. This avoids implicit width and
signedness and prevents u64 precision loss in JSON-number consumers.

Keeping this change under v1 was rejected: a v1 consumer expects `int` and JSON
numbers and could misinterpret or reject the new evidence. The complete v1
corpus is preserved byte-for-byte under `fixtures/versions/v1/` with checked
SHA-256 hashes. Current fixtures are regenerated as v2, and status-equivalence
tests show that legacy int32 proof outcomes do not change.

Before lowering any source, the frontend validates the pinned C++17 target
profile for 8-bit bytes, 32/64-bit widths, arithmetic signed right shift, and
the selected two's-complement signed narrowing behavior. A mismatch fails
closed. A6.8 does not accept new C++ source integer types: `int` maps to `i32`;
unsigned and 64-bit source types remain unsupported until their dedicated
stages.

The `require_current_schema` gate rejects v0, v1, unknown, and mixed-major
payloads. No legacy reader or conversion tool exists in this producer-only
repository.

## v3 decision: owned fixed-size arrays

A6.2 introduces proof-bearing `array<E,N>` types plus `array`, `select`, and
`store` expression kinds. Each access creates an explicit `[0,N)`
`array_bounds` obligation. Signed-only formulas use QF_ALIA; unsigned or
bitwise-tainted formulas use QF_ABV. Array countermodel values are materialized
at their owned length for replay and, when retained publicly, serialize as JSON
arrays of canonical decimal strings.

Keeping these semantics under v2 was rejected. A v2 consumer does not know that
`store` returns an isolated value, cannot enforce the new access-definedness
claim, and may misinterpret an array-valued counterexample binding. The complete
nine-case v2 corpus is preserved byte-for-byte under `fixtures/versions/v2/`
with 28 checked SHA-256 entries. Current fixtures are regenerated as v3;
status-equivalence is checked for all nine legacy v2 reports and the five v1
reports. `require_current_schema` rejects v0, v1, v2, unknown, and mixed-major
payloads.

The reviewed source subset is local, one-dimensional, positive fixed size,
fully initialized, and limited to 64 fixed-width integer elements. Raw-array
parameters/returns, pointer decay outside direct subscripting, aliases, dynamic
allocation, multidimensional arrays, partial initialization, and unmodeled
libraries remain unsupported.

## v4 decision: aggregate-by-value records

A6.3 introduces canonical `record<Name>{field:type,...}` identities, module
record declarations, and `record`, `project`, and `update` expressions. Record
parameters, returns, locals, branch merges, and direct contracted calls are
whole values with field-sensitive functional SSA. Signed integer leaves,
including elements of array fields, retain their source-type bounds.

Record formulas are classified as `QF_RECORD` and emitted as deterministic SMT
datatypes under `(set-logic ALL)`. Nested declarations are dependency-first;
signed-only leaves use `Int`, while unsigned or bitwise taint selects the
homogeneous bitvector lane. Candidate datatype models decode to canonical typed
records and replay before a violation can be returned. Public record evidence is
a recursive field-name object; cache v2 uses an explicit `$record` tag.

Keeping this under v3 was rejected. A v3 consumer cannot safely interpret the
new type identity, functional field update, module `records` table, or
record-valued counterexample. The complete ten-case v3 corpus is immutable under
`fixtures/versions/v3/` with 31 checked SHA-256 entries. Current fixtures are v4
and add the record slice; status equivalence is checked for all ten legacy v3,
nine v2, and five v1 reports. `require_current_schema` rejects v0 through v3,
unknown, and mixed-major payloads.

The reviewed source subset is named public `struct` values with 1 to 16 fields
and maximum nesting depth 8. Fields may be bool, fixed-width integer, owned
array, or an earlier value-record type. Aggregate initialization must be full.
Methods, constructors beyond implicit copy, inheritance, unions, bitfields,
layout/padding claims, class/private state, pointers, references, default member
initializers, partial/uninitialized values, and escaping addresses remain
unsupported.

## Consumer rules

Consumers must:

- compare the full `schema` string before interpreting the payload;
- reject or quarantine an unknown major version rather than guessing;
- ignore unknown object fields only within a known major;
- treat unknown status, mode, node-kind, and non-goal values as fail-closed;
- join results to obligations by ID;
- preserve non-goals separately from status counts;
- never reinterpret `unknown` or `unsupported` as `verified`.

The report and nested `semantic_ir` objects must carry the same schema value.
A mismatch is a malformed payload.

## Compatible changes within a major

A change may remain in the current major only when all of these are true:

1. it is additive;
2. the new field is optional for existing objects;
3. absence preserves the old meaning;
4. a conforming old consumer can ignore it without changing a proof claim;
5. deterministic ordering and existing fixture bytes remain unchanged for old
   inputs;
6. no existing status, mode, kind, field, or non-goal changes meaning.

Examples that can be compatible after review:

- an optional diagnostic-only string that does not affect evidence;
- a new top-level metadata object explicitly documented as ignorable;
- a new fixture case whose old cases remain byte-identical.

“Additive JSON” alone is not sufficient. A field is breaking when ignoring it
can change the semantic interpretation.

## Mandatory major-version triggers

The next such change advances the major identifier. Triggers include:

- removing, renaming, or changing the type/requiredness of an existing field;
- changing status meaning, proof evidence, cross-check behavior, or CLI status
  precedence;
- changing obligation mode semantics or the assumptions/conclusion contract;
- changing an existing expression/operator or IR node's semantics;
- adding a field that an old consumer cannot safely ignore, including result
  flow, memory effects, termination claims, or unsupported-boundary changes;
- adding a status or non-goal category that old consumers might treat as
  success;
- changing integer semantics, undefined-behavior obligations, model replay, or
  the rule that candidate counterexamples must replay;
- changing stable ordering, ID allocation, path normalization, encoding, or
  newline rules in a way that changes old fixture bytes;
- changing whether `semantic_ir` can be omitted or whether non-goals survive
  `--no-ir`;
- making an existing unsupported source form produce ordinary verified
  obligations without a reviewed semantic extension.

A new obligation or node kind is a mandatory version review. It may remain in
the current major only if old consumers are already required to fail closed on
the unknown value and ignoring the entire new object cannot strengthen a proof
claim.

## Major-version migration procedure

Every major bump must be one intentional stage/commit and include:

1. a decision note describing the semantic incompatibility and rejected
   compatibility alternatives;
2. an entry in [CHANGELOG.md](../CHANGELOG.md) with producer and consumer
   migration steps;
3. an update to the single `SCHEMA` constant and every report/IR schema test;
4. updated result/schema and adoption documentation;
5. preservation of the complete previous fixture corpus under a versioned
   archive such as `fixtures/versions/v1/`;
6. a new current corpus generated twice and byte-compared;
7. tests that reject mixed report/IR majors and unknown majors;
8. a consumer compatibility test or explicit statement that no compatible
   reader exists;
9. a release/migration window before deleting any old reader or conversion
   tool.

Old fixture bytes are never rewritten to look like the new schema. Corrections
to a historical corpus are added as documented errata or a new version.

## Producer and fixture discipline

- `semantic_verifier.model.SCHEMA` is the sole producer constant.
- Report and ModuleIR serialization use that constant directly.
- Golden JSON fixtures pin exact schema bytes.
- Human-readable IR may evolve only under the same deterministic/compatibility
  review because it is also a cross-language fixture surface.
- The regeneration tool must fail on unexpected summary drift.
- Two independent generations must remain byte-identical before a version
  change is accepted.

## Current compatibility statement

As of A6.3:

- current producer: `codeskeptic.semantic-verification/v4`;
- frozen previous baselines: complete v0, v1, v2, and v3 corpora under their
  matching `fixtures/versions/vN/` directories;
- compatible readers: v4 readers that require the exact schema and implement
  fixed-width scalars, owned arrays, value records, exact projection/update and
  bounds semantics, canonical recursive evidence, and minimized cores;
  `semantic_verifier.schema` supplies the reference fail-closed gate;
- v0 through v3 readers are intentionally incompatible with current
  type/evidence semantics;
- no legacy report reader or conversion tool exists in this producer-only
  reference repository, so none is deleted by this migration;
- the Unreleased changelog period is the migration window; archived fixture
  bytes remain available and are not scheduled for deletion.
This policy does not promise that every future source feature stays in v4. It
promises that a semantic break will be explicit, reviewable, fixture-backed,
and impossible to confuse silently with the previous proof contract.
