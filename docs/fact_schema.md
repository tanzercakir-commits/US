# Fact Index Schema v1

## Scope

The independent wire identifier is codeskeptic.fact-index/v1. It does not share
a version number with the verification report or Semantic IR. The index is a
deterministic world-model artifact for navigation and later architectural
queries; it is not verification evidence.

D1.1 defines and validates the contract only. Clang extraction starts in D1.2,
and fixture-backed extractor goldens start in D1.3.

## Envelope

Every document contains these required fields:

| Field | Meaning |
| --- | --- |
| schema | Exact codeskeptic.fact-index/v1 identity. |
| id | SHA-256 identity over all canonical index content. |
| source | Normalized display path, C++17 language, and source-byte hash. |
| symbols | Owned declarations for functions, records, fields, parameters, and variables. |
| definitions | Declaration, definition, parameter, initialization, or assignment facts. |
| uses | Read, write, read-write, or address uses inside a function. |
| calls | Direct caller-to-callee edges. |
| mutations | Explicit storage mutation facts. |
| purity | Exactly one derived tri-state row per indexed function. |
| limitations | Explicit unsupported or unresolved extraction boundaries. |

Unknown fields and unknown enum values are rejected. Arrays are sorted
canonically by their content identities or declared stable keys before
serialization. JSON object keys are sorted, non-ASCII text is escaped, and the
document ends with one newline.

## Source and locations

source.file is caller-visible and uses forward slashes. Every v1 location is
one-based and must name that exact source file. source.content_sha256 hashes the
UTF-8 source bytes and excludes checkout roots, compiler paths, clocks,
durations, and frontend process details.

The schema intentionally contains no Clang JSON node ID. Frontend identities
are inputs to extraction only and cannot become persistent world-model keys.

## Content identities

All symbol, definition, use, call, mutation, and complete-index identities use
lowercase SHA-256 with the sha256: prefix. The hashed envelope includes the
codeskeptic.fact-identity/v1 identity schema, the fact kind, and all canonical
owned fields.

A loader recomputes every identity. Editing a field without updating its
content identity fails closed. The complete index identity covers source
identity, every relation, purity, and limitations. Input array ordering is not
part of meaning.

## Symbols and ownership

Symbol kinds are closed to:

- function
- record
- field
- parameter
- variable

Linkage is external, internal, or none. Parameters are owned by functions,
fields by records, and local variables by functions. These owned symbols must
use none linkage. Functions and records have no owner in v1; member functions
are therefore outside this schema profile. Global variables have no owner.

qualified_name and type are canonical extractor-owned text. Declaration and
optional definition locations participate in the symbol identity, which also
prevents same-spelled local declarations from collapsing.

## Relations

Definitions refer to one symbol and an optional enclosing function context.
Definitions of local symbols must use their owning function as context.

Uses always carry an indexed function context. Calls have indexed function
caller and callee endpoints and are direct in v1. Mutations carry an indexed
function context and target only a parameter, field, or variable. Every
reference must resolve inside the same index; dangling graph edges are invalid.

Definitions, uses, calls, and mutations have their own content identities.
Duplicate symbols, relation identities, purity rows, or limitations are
invalid rather than silently deduplicated.

## Derived purity

Purity is navigation metadata with exactly three states:

| State | Meaning |
| --- | --- |
| pure | The admitted extraction surface found no caller-visible effect. |
| impure | The admitted surface found a caller-visible effect. |
| unknown | Extraction was incomplete, unresolved, or unsupported. |

Pure rows have no reasons. Impure and unknown rows require one or more closed
reason codes. Reasons cover global/parameter mutation, direct impure callees,
indirect or unresolved calls, virtual dispatch, and unsupported constructs.

No purity row says verified or proved. D1 derives facts from admitted syntax;
a later D5 stage may add separately versioned proof trust.

## Explicit limitations

The limitation codes are indirect_call, virtual_dispatch, unresolved_symbol,
macro_location, and unsupported_ast. Each limitation has a deterministic
message plus optional indexed context and source location.

A limitation never authorizes an approximation. D1.2 must use limitations when
the v0 extractor cannot claim complete coverage, and affected purity remains
unknown.

## Validation API

semantic_verifier.facts exposes immutable value objects, FactIndex.create,
load_fact_index, and load_fact_index_json. Constructors enforce local field
rules; FactIndex enforces graph closure, ownership, one source unit, complete
purity coverage, duplicate rejection, and the top-level identity.

The machine-readable schema is:

    semantic_verifier/fact_schema/v1/index.schema.json

It has additionalProperties set to false at every object boundary and freezes
the same enum sets as the Python loader.
