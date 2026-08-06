# Semantic Extensions Roadmap

## Purpose

Phase A6 widens values and state without widening the verifier's trust claim by
accident. Parser acceptance is the last step of a semantic feature, not the
first: each family needs owned IR, exact verification conditions, an explicit
solver fragment, replayable evidence, schema review, and negative fail-closed
tests.

## Ordered dependency chain

1. A6.1 chooses fixed-width integer semantics and appends implementation stages
   after A6.7 without renumbering the existing roadmap.
2. Those stages establish any type/solver/schema prerequisites used by arrays.
3. A6.2 adds fixed-size arrays and a common exact lvalue update model.
4. A6.3 builds value-type records on aggregate lvalue paths.
5. A6.4 admits only references with one statically proved target and lifetime.
6. A6.5 adds modular frame conditions over the resulting visible state.
7. A6.6 evaluates CHC/Spacer invariant proposals outside the trusted referee.
8. A6.7 freezes the combined support/capability/schema matrix.

The order is intentional. Frame conditions are not useful until caller-visible
aggregate locations exist, and reference support cannot precede an exact lvalue
and copy model. Inference remains last because a candidate must be checked by
the ordinary loop VCs over the final supported state model.

## Stable trust rules

- Current int32 mathematical-integer formulas plus explicit definedness and
  overflow obligations remain the claim until A6.1 selects and migrates a new
  representation.
- An unsupported source construct or backend formula never becomes verified.
- Default `both` mode does not silently discard an unsupported peer backend.
  A feature that only Z3 can decide must be selected explicitly until a reviewed
  capability policy says otherwise.
- Arrays never decay to pointers in the restricted subset. General aliasing,
  dynamic allocation, and unmodeled library operations remain unsupported.
- Struct support is semantic value copying, not ABI layout verification.
- References are admitted only with a unique proved target; snapshotting an
  alias is not an approximation option.
- `modifies` lists are frame specifications. Unlisted modeled locations must be
  proved unchanged, not merely omitted from a havoc set.
- Inferred invariants are proposals. They gain authority only after ordinary
  entry and preservation obligations verify.

## Schema and fixtures

Every new serialized type, expression, IR node, contract field, result field,
or changed field meaning is reviewed under `docs/schema_versioning.md`. A major
migration preserves the complete prior corpus under `fixtures/versions/`, adds
consumer migration notes, and rejects mixed report/IR majors. Adding a source
construct without serializable owned semantics is prohibited.

## Per-stage acceptance template

Each A6 implementation stage must include:

- positive proof, concrete violation, unknown/incomplete, and unsupported
  boundary tests;
- source-to-IR, IR-to-VC, solver emission, model replay, and deterministic
  serialization coverage for every new semantic path;
- explicit backend capability behavior in affine, Z3, and cross-check modes;
- 32/64-bit range, conversion, bounds, alias, lifetime, and frame obligations
  relevant to the feature;
- fixture/schema/changelog/adoption updates before consumers rely on it;
- full-suite, test-ratchet, fixture, and byte-determinism evidence.

If implementation would cross a stage's declared file set or require an
unplanned trust decision, stop and extend PLAN/TODO before editing code.
