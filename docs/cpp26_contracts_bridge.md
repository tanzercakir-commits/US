# C++26 contracts adapter

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
violation handling. US does not select or imitate that runtime policy.
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

## Bridge design

US uses a deterministic lexical bridge before the current Clang parse.
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
## Implemented bridge

The bridge now runs automatically before the existing Clang C++17 JSON-AST
parse. It removes accepted `pre`/`post` spans only from private compiler
input, retains their predicates as side metadata, and changes
`contract_assert` to the already-owned `assert(bool)` call shape. The main
source's UTF-8 byte length and newline positions are unchanged, so AST offsets
continue to map to original source locations. Temporary paths and the private
assert declaration never enter reports.

A complete supported example is committed at
`fixtures/cpp26_contracts/verified.cpp`:

```cpp
int absolute_value(const int value)
    pre(value != -2147483648)
    post(result: result >= 0 && (result == value || result == -value))
{
    contract_assert(value != -2147483648);
    if (value < 0) {
        return -value;
    }
    return value;
}
```

Run it through the ordinary referee:

```powershell
python -m semantic_verifier fixtures/cpp26_contracts/verified.cpp
```

The example produces six verified obligations and zero results in every other
status. `violated.cpp` proves the negative path: its false postcondition
produces two verified obligations plus one replayed violation and exit `1`.
Equivalent standard and `cs:` fixtures lower to the same semantic projection.

The extracted function metadata now enters lowering through the same owned
`ContractSurfaceAdapter` seam as legacy `cs:` comments. The adapters share
only a result boundary: they do not merge syntaxes, reinterpret predicates, or
change the bridge acceptance rules. This keeps a future native Clang contract
source replaceable without changing Semantic IR, verification conditions, or
referee outcomes.

The implemented acceptance subset is attribute-free and definition-only. A
contracted function must be its first and only declaration and otherwise fit
the existing non-virtual frontend subset. A postcondition may omit the result
binding; when it has one, the bridge renames only root identifier tokens to
`result`, never same-spelled member names. Any non-reference parameter used by
a postcondition must be const-qualified. Mixed standard/`cs:` contracts,
attributes, malformed or unattached forms, redeclarations, virtual/member
definitions, result-name conflicts, and const-rule violations produce explicit
unsupported results. Text inside comments, ordinary/raw strings, and
preprocessing directives is inert.
