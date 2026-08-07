# C++26 contracts bridge decision

Research snapshot: 2026-08-07. This note records a dated compatibility
decision; compiler support is not consulted on the verifier's logic path.

## Standard surface

P2900R14 is represented in the current working draft by three contract
assertion forms:

- `pre(predicate)` is a function precondition checked at function entry.
- `post(result_name: predicate)`, or `post(predicate)` without a result
  binding, is a function postcondition associated only with normal exit.
- `contract_assert(predicate);` is a statement assertion at its source point.

Attributes may occur between each keyword and its opening parenthesis. A
contract predicate is contextually converted to `bool`. Function-contract
sequences have declaration consistency rules, and a postcondition that odr-uses
a non-reference parameter requires that parameter to be const-qualified.

Runtime evaluation is not simply “on” or “off”: the draft defines ignore,
observe, enforce, and quick-enforce semantics, with compiler-selected policy and
violation handling. CodeSkeptic does not select or imitate that runtime policy.
It statically proves an owned predicate or reports a distinct non-verified
status.

Normative/design sources:

- [P2900R14](https://wg21.link/P2900R14)
- [function contract grammar and rules](https://eel.is/c++draft/dcl.contract.func)
- [assertion-statement grammar](https://eel.is/c++draft/stmt.contract.assert)
- [evaluation semantics](https://eel.is/c++draft/basic.contract.eval)

## Owned mapping

| C++26 form | Existing verifier semantic | Mapping |
|---|---|---|
| `pre(p)` | `cs: requires p` | Preserve the supported predicate exactly. |
| `post(p)` | `cs: ensures p` | Preserve the supported predicate exactly. |
| `post(r: p)` | `cs: ensures p` | Rename only identifier tokens bound to `r` to the reserved IR `result`. |
| `contract_assert(p);` | source `assert(p)` / assertion IR | Prove at that program point, then assume on the continuing path. |

There is deliberately no mapping from `contract_assert` to
`cs: invariant`: a point assertion does not establish loop entry and
preservation. P2900 also supplies no spelling for the verifier's frame contract
(`cs: modifies`). Unsupported predicates and forms remain unsupported; the
bridge never weakens or approximates them.

## Compiler evidence

The SD-6 gate is `__cpp_contracts >= 202502L`. GCC's official C++ status page
reports P2900R14 in GCC 16 under experimental C++26 support. Clang's official
C++ status page currently reports P2900R14 as unsupported:

- [GCC C++ status](https://gcc.gnu.org/projects/cxx-status.html)
- [Clang C++ status](https://clang.llvm.org/cxx_status.html)

The local probe used Clang 20.1.8 with `-std=c++2c`. It found no
`__cpp_contracts` macro and rejected `pre` at the function declarator with
“expected function body after function declarator.” Therefore the existing
Clang JSON-AST seam cannot yet expose native contract nodes.

## C3.1 decision

C3.1 will use a deterministic lexical bridge before the current Clang parse.
It will extract only the declared controlled subset into side metadata and
replace recognized syntax in compiler input without changing UTF-8 byte count
or newline positions. `contract_assert` becomes the already-owned assertion
call shape; a private compiler preamble supplies its declaration without
changing main-file locations. Lowering consumes the side metadata and invokes
the existing contract expression parser and VC generator.

The initial acceptance boundary is intentionally narrower than the complete
standard. It admits attribute-free contracts on a first-and-only, non-virtual,
otherwise-supported function definition. It enforces postcondition const-use
rules and exact result binding. Mixed `cs:` and standard function contracts,
attributes, redeclarations, virtuals, malformed nesting, preprocessing
ambiguity, or uncertain binding fail closed as unsupported.

This bridge is removable. When Clang exposes stable native contract AST nodes,
a later stage can replace extraction while keeping the owned mapping and
verification conditions unchanged.
