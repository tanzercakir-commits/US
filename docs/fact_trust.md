# Fact trust overlay

Status: the strict codeskeptic.fact-trust/v1 model is implemented in D5.1.
Referee-backed production of proved claims is implemented separately in D5.2.

## Trust is an overlay

The D1 codeskeptic.fact-index/v1 artifact remains byte-for-byte unchanged.
A trust document names its fact-index identity and exact source hash, then
contains exactly one claim for every D1 purity row.

Each claim repeats only the referenced function ID and purity value needed to
bind the trust label:

- derived means the value came from deterministic fact extraction;
- proved means the pure value passed the D5.2 proof-promotion gate.

impure and unknown values can never be labelled proved. Trust changes no fact
value and hides no D1 limitation.

Claim identities cover the function, value, trust label, and complete evidence.
The overlay identity covers the fact-index ID, source hash, schema, and all
claim identities/content. JSON object keys, arrays, identities, and D1
references are validated strictly and serialize canonically in sorted order.

The normative JSON Schema is
semantic_verifier/fact_trust_schema/v1/index.schema.json.

## Proof evidence shape

A proved claim uses the fixed empty-frame-full-vc/v1 method and records:

- the exact source SHA-256 and semantic-verification artifact SHA-256;
- the semantic-verification schema and recognized referee ID;
- a non-empty sorted set of exact verified obligation IDs;
- the exact source location of the explicit empty modifies frame;
- every exact indexed direct callee, each itself proved.

The loader cross-validates every claim against the supplied D1 fact index.
Proved dependencies must equal the direct-call facts and form an acyclic graph.
A missing, derived, dangling, self-dependent, or cyclic callee prevents a valid
proved overlay.

The accepted referee IDs are codeskeptic.affine/v1, codeskeptic.z3/v1, and
codeskeptic.both/v1. A derived claim carries null evidence.

A structurally valid JSON document is not by itself proof that a referee ran.
D5.2 is the trusted producer: it links one frontend parse, the D1 index, the
complete verification report, and this overlay. Consumers should accept proved
trust only from that controlled execution path and retain the cited report for
audit/replay.

## Fail-closed rules

The strict loader rejects unknown or missing fields, duplicate JSON keys,
non-finite values, duplicate/missing/dangling claims, stale content identities,
invalid hashes or obligation IDs, value drift from D1, proof evidence on a
derived claim, proof trust on a non-pure value, incomplete direct-callee
evidence, and source/frame mismatches.

Serialization contains no absolute physical path, time, randomness, model
output, or mutable state.
