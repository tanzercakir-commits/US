# Fact Query Interface

## Scope

D2.1 exposes deterministic navigation over one strictly validated
codeskeptic.fact-index/v1 artifact. It never extracts additional facts, joins
translation units, resolves a D1 limitation, invokes a model or checker, or
changes purity/proof trust.

The library entry point is FactWorld in semantic_verifier.fact_queries. Every
successful query returns codeskeptic.fact-query-result/v1 as canonical,
sorted-key ASCII JSON ending with one newline. A deterministic text rendering is
also available for terminals.

## Exact selectors

A selector is either a full content-addressed symbol ID or an exact
qualified_name. Bare fuzzy, prefix, suffix, and type-coercing matches do not
exist.

If a qualified name denotes overloads, the query fails and lists sorted
kind/name/type/ID candidates. The caller then repeats the query with the exact
ID. A missing selector and a selector of the wrong symbol kind also fail
explicitly.

## Queries

### who-calls

who-calls accepts only a function. It returns indexed caller symbols, exact call
fact IDs, and source sites grouped by caller. Multiple calls from one function
remain multiple sites. A known function with no indexed callers succeeds with
an empty callers array.

### who-mutates

who-mutates accepts a variable, parameter, or field. It returns indexed mutator
functions and each exact mutation ID, mutation kind, and source site. A known
storage symbol with no indexed mutation succeeds with an empty mutators array.

### neighborhood

neighborhood accepts any symbol and depth 0 through 8. It performs deterministic
undirected breadth-first traversal over only these D1 edges:

| Edge | Direction in output | Source fact |
| --- | --- | --- |
| owns | owner to owned symbol | symbol.owner |
| defines | function context to symbol | definition |
| uses | function context to symbol | use |
| calls | caller to callee | call |
| mutates | function context to storage | mutation |

Traversal treats edges as undirected for reachability but preserves the source
direction in output. The result records each symbol's shortest distance and all
exact edges whose endpoints are inside the selected neighborhood. Depth zero
contains only the target and no edges.

Relevant limitations are preserved in every result. Module-level limitations
are always included; symbol-context limitations are included when that symbol
is the target or part of the returned answer. They remain limitations and never
become graph edges or inferred answers.

## CLI

Run queries against a committed or generated fact index:

    python tools/query_facts.py INDEX who-calls SELECTOR
    python tools/query_facts.py INDEX who-mutates SELECTOR
    python tools/query_facts.py INDEX neighborhood SELECTOR --depth 2

JSON is the default. Put --format text after INDEX and before the command for
the deterministic terminal rendering:

    python tools/query_facts.py INDEX --format text who-calls SELECTOR

Exit codes are:

| Code | Meaning |
| --- | --- |
| 0 | Exact query succeeded, including an empty answer. |
| 2 | Query/selector/kind/depth error. |
| 3 | Fact-index read, UTF-8, schema, or graph-validation error. |

Diagnostics go to stderr and successful output goes to stdout.
## MCP stdio endpoint

D2.2 exposes the same pure FactWorld API through MCP protocol version
2026-07-28. The server is stateless: clients do not send initialize or
notifications/initialized. Every request instead carries these fields in
params._meta:

- io.modelcontextprotocol/protocolVersion: 2026-07-28
- io.modelcontextprotocol/clientCapabilities: an object
- io.modelcontextprotocol/clientInfo: an optional name/version object

Start the newline-delimited UTF-8 JSON-RPC stdio server with:

    python tools/fact_mcp_server.py INDEX

The server implements server/discover, tools/list, and tools/call. Discovery
advertises only the tools capability. List and discovery results include the
required resultType, ttlMs, cacheScope, and server identity fields. Stdout is
reserved for one protocol message per line; startup and transport diagnostics
go to stderr; closing stdin causes a clean exit.

The single tool is codeskeptic.query_facts. Its arguments are kind, selector,
and optional depth for neighborhood only. Successful calls return the
codeskeptic.fact-query-result/v1 object as structuredContent and the same
canonical JSON in a text content block. The tool is read-only, idempotent,
closed-world, and non-destructive.

Missing or unsupported protocol metadata, unknown methods/tools, and malformed
RPC parameters return typed JSON-RPC/MCP errors. Selector ambiguity, missing
symbols, wrong symbol kinds, unsupported query kinds, and invalid neighborhood
depth are tool-visible isError results so an agent can correct the request.
Neither path invents facts, resolves limitations, or promotes trust.

The reviewed primary-source profile is frozen in
research/mcp_fact_query_evidence.json. It records the official 2026-07-28
changelog, schema, stdio, discovery, and tools pages used by the adapter.
## Compact fact context packs

D2.3 produces codeskeptic.fact-context/v1 as compact, sorted-key ASCII JSON.
The requested byte budget is also a conservative token upper bound because the
artifact is ASCII and every token consumes at least one byte. The default and
maximum are both 2000 bytes.

Every pack has a mandatory envelope containing the exact root symbol, fact
index identity/schema, stable source display path, source content hash,
language, requested budget, and omission counts. If this envelope cannot fit,
generation fails and reports the exact minimum budget instead of dropping root
or provenance data.

Candidate items come only from the exact D2 query graph through depth eight.
They are ranked first by shortest graph distance. At a distance, root purity
and explicit limitations lead; relations then prefer calls, mutations,
ownership, uses, and definitions; non-root purity follows relations. Stable
canonical bytes break ties. A relation carries the original edge and exact
qualified-name labels. No source body, inferred edge, semantic guess, proof
status, model output, wall clock, or randomness enters the pack.

Selection keeps the longest ranked prefix that fits. Once the next item would
exceed the budget, the entire lower-ranked suffix is omitted. The limitations,
purity, relations, and total counters therefore describe exactly what was
truncated from the ranked candidate window.

Generate a pack with:

    python tools/generate_fact_context.py INDEX SELECTOR OUTPUT

Use a smaller valid budget with --budget. Check committed bytes without writing
with:

    python tools/generate_fact_context.py INDEX SELECTOR OUTPUT --check

Generation returns 0 on success, 2 for selector/budget errors, and 3 for
index/output errors. Check mode returns 1 for missing or stale output and never
rewrites it. The frozen 2000-byte example is
fixtures/fact_context/pipeline.context.json.
