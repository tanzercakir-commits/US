# Assumption declaration protocol

Status: E3.1 immutable declarations and linked resolution overlays are
implemented. The repository-local declaration-before-code pilot follows in
E3.2.

## Referee boundary

An assumption artifact is planning evidence, not verification evidence. The
agent declares what it believes before implementation. A later overlay must
resolve every declaration to a cited contract, a cited test, or an explicit
uncheckable reason. A path, hash, or anchor proves only which artifact was
cited; the normal contract referee or test runner still decides whether that
artifact passes.

Uncheckable is a permanent honest boundary. It carries no evidence, never
appears as verified, and never contributes to the resolved-checkable count.

## Declaration

codeskeptic.assumption-manifest/v1 contains a subject, a sorted exact snapshot
of one or more normalized UTF-8 repository files, and sorted unique assumptions.
Each assumption has an `asm-NNN` identity, statement, scope, low/medium/high
risk, and an intended disposition: contract, test, or uncheckable. The manifest
content identity covers all fields and is independent of every later resolution.

Manifest paths are canonical repository-relative paths. Absolute, dotted,
backslash, missing, non-UTF-8, NUL, stale-hash, and resolved root-escape paths
fail closed. Line endings are normalized to LF before hashing so the declaration
is stable across supported checkouts.

## Resolution overlay

codeskeptic.assumption-resolution/v1 links one exact manifest and contains
exactly one row for every declared ID. Contract and test rows require one or
more sorted unique evidence records with canonical path, normalized UTF-8 hash,
and a non-empty anchor present in the artifact; their reason is null.
Uncheckable rows require no evidence and a concrete non-empty reason.

The validator rechecks the declaration snapshot, one-to-one coverage, intended
dispositions, evidence files, hashes, anchors, and root confinement. Its
codeskeptic.assumption-summary/v1 output reports declaration, contract, test,
resolved-checkable, and uncheckable counts without inventing a verified count.

Validate the frozen example:

    python tools/check_assumption_manifest.py fixtures/assumption_manifest/expected.manifest.json fixtures/assumption_manifest/expected.resolution.json --root fixtures/assumption_manifest

Success exits 0 with deterministic summary JSON. Strict JSON, linkage, path,
snapshot, evidence, disposition, or anchor failure exits 2. The matching Draft
2020-12 structural schemas are under
semantic_verifier/assumption_manifest_schema/v1.
