# Schema Version Policy

## Decision

The wire identifier has one explicit major component:

```text
codeskeptic.semantic-verification/vMAJOR
```

The current value is `codeskeptic.semantic-verification/v1`. F4.1 froze the
report and Semantic IR contract as the v0 compatibility baseline; A4.1 advances
the producer to v1 for the counterexample-evidence change below. A producer
emits exactly one major version; there is no implicit negotiation or fallback.

The fixture-corpus manifest has its own namespace
(`codeskeptic.fixture-corpus/v0`) and versions independently from the report/IR
schema.

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
violated source-branch path omit the field, so the existing five-case current
fixture corpus remains byte-identical. An equivalent change that altered proof
meaning or existing fixture bytes would require a new major review.

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

The next such change moves the identifier from v0 to v1. Triggers include:

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
   archive such as `fixtures/versions/v0/`;
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

As of A4.3:

- current producer: `codeskeptic.semantic-verification/v1`;
- frozen previous baseline: the complete five-case v0 corpus under
  `fixtures/versions/v0/`;
- compatible readers: v1 readers that require the exact schema and apply the
  minimized-core interpretation; `semantic_verifier.schema` supplies the
  reference fail-closed gate;
- v0 readers are intentionally incompatible with v1 evidence semantics;
- no legacy report reader or conversion tool exists in this producer-only
  reference repository, so none is deleted by this migration;
- the Unreleased changelog period is the migration window; v0 fixture bytes
  remain available throughout and are not scheduled for deletion.

This policy does not promise that every future source feature stays in v0. It
promises that a semantic break will be explicit, reviewable, fixture-backed,
and impossible to confuse silently with the previous proof contract.
