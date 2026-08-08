# Whole-project and owned-memory readiness decision

Decision date: 2026-08-08.

This decision turns product readiness into three evidence-backed properties:

1. the selected C++ project is ingested and accounted for as a whole;
2. the admitted memory/pointer semantics are modeled and checked without
   unsound approximations; and
3. everything not evaluated remains visible to the operator.

It does not claim full C++, production certification, or current readiness.
Python and JavaScript frontends are explicitly deferred until the C++ ship gate
F6.3.

## Readiness is three different measurements

Project ingestion, semantic coverage, and proof outcomes are separate:

- **ingestion completeness** accounts for every selected compilation-database
  entry and translation unit;
- **semantic coverage** accounts for every discovered function, direct call
  edge, and construct as supported, unsupported, unresolved, or failed; and
- **proof outcomes** account for every emitted obligation using the existing
  five statuses.

A project can be completely ingested without every construct being supported.
It cannot be called completely evaluated when unsupported work is hidden. A
silent file, function, edge, construct, or obligation omission is therefore a
release blocker.

No percentage may combine `unknown`, `unsupported`, or `solver_error` with
`verified`. Reports must expose absolute counts and leaf records as well as
any derived ratio.

## Whole-project identity and accounting

The project input will be rooted in a caller-owned repository and an explicit
`compile_commands.json`. A7.1 owns deterministic selection and rejects
missing sources, duplicate entries, commands outside the declared root, stale
commands, and argument shapes it cannot interpret. It never discovers or
guesses build commands from the network.

Logical project identity excludes absolute checkout location but includes:

- normalized project-relative source paths;
- canonical compiler arguments that affect parsing or target semantics;
- source content identities;
- the pinned target profile and frontend policy; and
- the ordered set of selected translation units after canonical sorting.

A7.2 adds stable declaration/function identity and direct-call edges. An
ambiguous, conflicting, or unresolved edge cannot import a callee contract into
the caller. Internal linkage, overloads, redeclarations, and ODR conflicts need
explicit dispositions.

The project report must reconcile these inventories:

```text
compilation entries = selected + rejected
selected translation units = parsed + frontend_error
discovered functions = supported + unsupported + unresolved + failed
direct call edges = linked + external_contracted + unresolved + unsupported
obligations = verified + violated + unknown + unsupported + solver_error
```

## Owned memory model

Pointers are not integers. The versioned memory IR introduced by A7.3 will own
these concepts:

- **region**: stack, global, or heap storage with stable identity, extent,
  alignment/layout evidence, and lifetime state;
- **object**: a typed value occupying a region or a typed subobject/path;
- **pointer**: null or a typed reference carrying provenance, target
  region/object, and an in-region offset;
- **location**: a typed lvalue selected from a live object by field or proved
  in-bounds index steps;
- **memory state**: explicit SSA-style load/store state rather than hidden
  mutation; and
- **lifetime**: declared, alive, or freed/ended according to the admitted
  storage class.

Serialization alone proves nothing. A7.4 and later stages must generate and
discharge the relevant obligations before a memory operation can verify:

- pointer is non-null;
- provenance names an admitted live region;
- offset/path is within the complete object and correctly typed;
- stack lifetime has not ended or escaped illegally;
- a write is permitted by the effective `modifies` frame;
- alias uncertainty has been preserved rather than replaced by no-alias;
- allocation is alive before access;
- deallocation targets a compatible live allocation exactly once; and
- ownership/lifetime summaries remain compatible across direct calls.

## Admission order

| Stage | Newly admitted behavior | Still deferred |
| --- | --- | --- |
| A7.3 | Memory IR representation and value-only v6 migration | All pointer operations remain unverified |
| A7.4 | Stack/global address-of, dereference, member/index access, null/bounds/lifetime checks | Heap, indirect calls, arbitrary pointer arithmetic |
| A7.5 | Direct-call may/must-alias and memory-effect summaries, pointer-aware frames | Function pointers, dynamic dispatch, concurrency |
| A7.6 | Controlled ordinary scalar/array `new`/`delete`, ownership transfer, UAF/double/invalid-free checks | Placement/nothrow/overloaded new, custom allocators, shared ownership |

The following remain fail-closed until separate decisions provide exact
semantics: pointer-integer conversion, `reinterpret_cast`, union type-punning,
unsupported object layout, placement new, custom allocators, exception-driven
cleanup, atomics, and concurrency. Uncertain aliasing broadens effects or
becomes unsupported; it is never treated as independence.

## Cross-repository delivery

The Python repository remains the executable reference oracle:

- A7.1–A7.2 establish project ingestion and cross-TU identity;
- A7.3–A7.6 establish memory semantics and proof/replay behavior;
- A7.7 establishes honest project coverage; and
- A7.8 freezes the reference corpus and phase-gate evidence.

CodeSkeptic remains the native C++17 product:

- B5.1 matches project and cross-TU reference identities;
- B5.2 ports memory IR, VC, referee, and replay without semantic widening;
- B5.3 records contract-first dogfood evidence;
- B5.4 packages project reporting and CI; and
- B5.5 proves native end-to-end parity on the non-toy corpus.

Python never becomes a CodeSkeptic runtime or release dependency.

## CodeSkeptic contract-first dogfood

The recommendation is to start shadow-mode dogfood now for changed C++ functions
whose current semantics are already supported.

1. The AI creates only `// cs: ai ...` proposals from an exact owned request.
2. The existing deterministic C1.2 pre-screen evaluates the proposal.
3. Rejected, malformed, stale, unsupported, unknown, or solver-error proposals
   do not enter the human acceptance queue.
4. A human edits the candidate if needed and removes `ai`.
5. The acceptance audit and a fresh verification run are stored separately.
6. Shadow-mode results do not block ordinary development.

Pointer-bearing contracts that exceed current semantics must not be accepted as
proof-bearing intent merely to dogfood the syntax. Record those assumptions as
explicit design work until B5.2 can check them. B5.3 makes the workflow eligible
for a blocking policy only after one supported scalar change and one admitted
pointer-bearing change complete the full proposal-to-reverification chain.

This policy lets CodeSkeptic use its own contract workflow without making the AI
the referee or pretending that unsupported memory semantics already exist.

## Product gates

The product does not ship merely because a demo verifies.

- **A7 gate:** a deterministic multi-TU reference corpus has zero silent skips
  and positive/replayed-negative evidence for every admitted pointer, alias,
  lifetime, frame, and heap class.
- **B5 gate:** the packaged native binary matches reference identities,
  obligations, statuses, replay, and project accounting.
- **F6.1 gate:** a pinned non-toy project repeats logical outputs across
  supported machines and declares its operational envelope.
- **F6.2 gate:** one high-error-cost pilot publishes predeclared scope,
  coverage, useful findings, unsupported debt, review effort, proposal
  acceptance, CI cost, and limitations.
- **F6.3 gate:** every mandatory gate passes. Otherwise the recorded decision
  is no-ship.

The ship claim is limited to the declared C++ segment and pilot profile. It is
never a claim to verify all C++ or certify a system.
