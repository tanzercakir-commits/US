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
