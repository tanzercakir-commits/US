# Fact trust overlay

Status: the strict overlay and referee-backed promotion pipeline are implemented.

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
codeskeptic.both/v1. The producer derives that ID from the exact built-in
checker type and rejects custom or mismatched implementations. A derived claim
carries null evidence.

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

## Referee-backed producer

FactTrustPromotionPipeline owns one ClangFactExtractor and parses the exact
source/display path once. The same FrontendUnit is passed to D1 fact extraction
and Semantic IR lowering. The checker processes the complete generated
obligation set, and the resulting full verification report is retained beside
the fact index and trust overlay.

A derived pure claim promotes only when all of these conditions hold:

1. the D1 function has an exact definition and one unambiguous IR body match;
2. no module-level or function-context fact/IR limitation exists;
3. the function has an explicit empty modifies frame that was not marked
   machine-proposed;
4. the function has at least one obligation, exactly one result per obligation,
   and every result is verified;
5. every exact D1 direct callee has already promoted in the same acyclic
   fixed-point run.

No obligation is created merely to make purity promotable. A function with zero
obligations remains derived. Missing or non-empty frames, machine-proposed
frames, external or derived callees, ambiguous overloads, recursion, incomplete
checker output, and violated, unknown, unsupported, or solver-error results all
remain derived. impure and unknown D1 values are never candidates.

Each proved claim cites the SHA-256 of verification.json and its exact
obligation IDs. fact-index.json, verification.json, fact-trust.json, and
promotion-run.json therefore form one deterministic audit bundle.

## Promotion CLI

Generate the four linked artifacts with:

    python tools/promote_fact_trust.py source.cpp \
      --display-path project/source.cpp \
      --output-dir .codeskeptic/fact-trust \
      --backend affine

Use --backend z3 or --backend both with the normal Z3 configuration when those
referees are required. Check frozen artifacts without writing:

    python tools/promote_fact_trust.py source.cpp \
      --display-path project/source.cpp \
      --output-dir .codeskeptic/fact-trust \
      --backend affine --check

Exit code 0 means generation succeeded or every checked byte matched. Exit code
1 means check-mode mismatch or a stale undeclared artifact. Exit code 2 means a
strict input, frontend, filesystem, backend-configuration, or generation error.
A solver status recorded inside a valid verification report does not fabricate
proof; the affected claim stays derived.

The fixture in fixtures/fact_trust freezes a proved leaf and proved direct-call
chain together with no-frame and zero-obligation derived cases.
