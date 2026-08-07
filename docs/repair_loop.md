# Referee-guided repair loop

Status: E1.1 replay-attested repair bundles are implemented. The bounded
proposal harness and telemetry stages follow in E1.2 and E1.3.

## Repair bundle v1

codeskeptic.repair-bundle/v1 packages one concrete violated validity obligation.
It is context for an untrusted repair proposer, not a proof or acceptance
decision.

The bundle contains:

- exact display path and UTF-8 source SHA-256;
- semantic-verification schema and full report SHA-256;
- the canonical original obligation and its unique violated result, including
  the replayed counterexample and trace when present;
- a bounded, line-numbered source slice centered on the result location;
- every requires, ensures, and modifies contract attached to the exact target
  IR definition, preserving human or machine-proposed provenance;
- a content identity covering every field.

RepairBundleBuilder reruns the complete report from the supplied source with the
same exact built-in referee. It then checks the original serialized obligation
again and requires an identical violated result with a concrete counterexample.
A report mismatch, changed replay, non-validity obligation, verified/unknown/
unsupported/solver-error result, absent counterexample, ambiguous definition,
custom checker, or mismatched referee label fails closed.

The accepted referees are the exact built-in affine, Z3, and affine-plus-Z3
cross-check implementations. The bundle contains no model prompt, proposed
patch, inferred intent, physical path, clock, duration, randomness, or trust
promotion.

The source slice radius defaults to four lines and is clamped at file bounds.
The supported range is zero through twenty. Slice lines are copied exactly
without reconstructing or normalizing source.

The normative JSON Schema is
semantic_verifier/repair_bundle_schema/v1/index.schema.json. The runtime loader
also cross-validates the source hash, report hash/schema, canonical obligation
and result, source slice, strict keys, and content identity.

## CLI

Generate a bundle from the first replayable violation:

    python tools/generate_repair_bundle.py source.cpp repair.bundle.json \
      --display-path project/source.cpp --backend affine

Select a specific obligation with --obligation. Use --backend z3 or
--backend both with the normal Z3 configuration. Compare exact bytes without
writing:

    python tools/generate_repair_bundle.py source.cpp repair.bundle.json \
      --display-path project/source.cpp --backend affine --check

Exit code 0 means generation succeeded or check bytes matched, 1 means a check
mismatch, and 2 means input/frontend/referee/schema/replay failure.

fixtures/repair_bundle freezes a violated postcondition with one
machine-proposed requires contract, one human ensures contract, exact source
context, and an affine-replayed counterexample.
