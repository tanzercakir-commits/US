# US roadmap

US is moving from file-level semantic verification toward an honest
whole-project C++ result. Each stage keeps unsupported behavior explicit and
must pass the deterministic test and fixture gates.

## Completed foundation

- C++ parsing through Clang and deterministic Semantic IR.
- Preconditions, postconditions, frame conditions, and loop invariants.
- Independent affine and Z3 checker paths with replayed counterexamples.
- Fixed-width integers, arrays, value records, reviewed local references, and
  direct modular calls within the documented subset.
- C++26 and `cs:` contract adapters with one internal contract boundary.
- Contract-first approval artifacts that are checked against the implemented
  source contract.
- Deterministic project manifests and direct cross-file call indexing.
- Proof-neutral Memory IR for regions, objects, typed pointers, memory states,
  and memory operations.
- 697 deterministic tests and byte-identity fixture checks.

## Current stage

Admit a bounded stack/global pointer subset and generate explicit null, bounds,
provenance, type, and lifetime obligations. Pointer operations outside the
admitted subset remain unsupported.

## Next stages

1. Carry alias and memory-effect summaries across direct project calls.
2. Verify a controlled allocation and deallocation lifecycle.
3. Produce a project coverage report that accounts for every selected file,
   function, call edge, obligation, and unsupported construct.
4. Freeze a non-toy whole-project pointer and heap corpus with replayed negative
   evidence and deterministic outputs.
5. Measure scale and determinism on a large C++ project.
6. Run one high-error-cost pilot and make an evidence-based ship decision.

## Current boundary

US is not yet a full C++ verifier or a certification product. Source pointer
safety, alias summaries, heap lifecycle, and whole-project proof are not claimed
until their roadmap gates pass. See the
[supported boundary](semantic_verification_prototype.md) for the exact current
subset.
