# Referee-guided repair loop

Status: E1.1 bundles and the E1.2 bounded repair harness are implemented.
Append-only telemetry follows in E1.3.

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

## Bounded repair harness

RepairHarness accepts a PatchProposer abstract seam and calls it at most N
times, where N is from one through eight. The proposer is untrusted. The
dependency-free CLI uses only a strict codeskeptic.patch-script/v1 document;
there is no network or model package.

A codeskeptic.patch-proposal/v1 value names the exact current UTF-8 source hash
and one inclusive line range plus replacement lines. Proposal and loop content
identities cover every field. Stale hashes, invalid ranges, invalid UTF-8,
newline/NUL-bearing replacement lines, no-op edits, repeated proposal IDs,
non-proposal returns, and proposer exceptions are logged and rejected.

Every valid candidate is verified from memory with the admitted built-in
referee. A candidate succeeds only when:

- the exact target function still exists with every bundled contract unchanged,
  including text and human/machine provenance;
- its complete result set is non-empty and every result is verified;
- no module-level lowering failure exists.

Deleting or changing a contract can never manufacture success. If a candidate
still has a concrete replayable violation, the harness builds the next E1.1
bundle and continues from that candidate. Unknown, unsupported, solver-error,
missing-target, or non-rebundleable candidates are referee-blocked and do not
become the next source. The first verified candidate stops the loop; otherwise
all N attempts are recorded and status is exhausted.

codeskeptic.repair-loop/v1 records every proposal ID, candidate source hash,
verification artifact hash, exact obligation statuses, diagnostic, and the
accepted source/proposal only on verified success. It carries no time or random
value. The original source file is never written.

Run the offline harness:

    python tools/run_repair_loop.py source.cpp repair.bundle.json \
      proposals.json repair-loop.json \
      --display-path project/source.cpp --max-iterations 3 \
      --backend affine

Add --check to compare exact log bytes without writing. Exit code 0 means the
deterministic loop ran or matched, 1 means check mismatch, and 2 means strict
input/frontend/referee error. Loop exhaustion is an honest output, not a tool
error.

fixtures/repair_loop freezes a first-shot verified repair and a two-attempt
exhausted run.
