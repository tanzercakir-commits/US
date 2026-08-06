# Verification Result and Semantic IR Schema Reference

## Scope and stability

The current schema identifier is `codeskeptic.semantic-verification/v0`. It
covers the verification report, obligations, results, non-goals, and the owned
Semantic IR emitted by the Python reference implementation.

`v0` is deterministic but provisional. Consumers must check `schema`, ignore
unknown object fields, and treat missing optional fields as absent rather than
`null`. The version-change policy is defined separately in F4.1; until then,
fixtures are the executable compatibility contract.

## Report envelope

JSON output has this shape:

```json
{
  "non_goals": [],
  "obligations": [],
  "results": [],
  "schema": "codeskeptic.semantic-verification/v0",
  "semantic_ir": {},
  "source": "path/to/input.cpp",
  "summary": {
    "solver_error": 0,
    "unknown": 0,
    "unsupported": 0,
    "verified": 0,
    "violated": 0
  }
}
```

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `schema` | string | yes | Exact schema identifier. |
| `source` | string | yes | Caller-visible source path with `/` separators. |
| `summary` | object | yes | Count for every status, including zero counts. |
| `obligations` | array | yes | Source/deterministic generation order. |
| `results` | array | yes | One result per obligation in the same order. |
| `non_goals` | array | yes | Explicit exclusions; never folded into status counts. |
| `semantic_ir` | object | default | Omitted only with JSON `--no-ir`. |

Join a result to its obligation by `result.obligation == obligation.id`.
Consumers should not rely only on array position even though the reference
implementation preserves one-to-one order.

## Result taxonomy

| Status | Meaning | Evidence rule |
| --- | --- | --- |
| `verified` | The declared obligation was discharged. | Validity was proved, satisfiability has a concrete witness, or a well-formedness check accepted the expression. |
| `violated` | The declared obligation is false. | A validity countermodel replayed successfully, or requirements were proved infeasible. |
| `unknown` | The question is supported but undecided. | Affine incompleteness, solver `unknown`, or timeout; never treated as proof. |
| `unsupported` | Source or logic is outside the declared subset. | Carries an explicit reason; no approximation is allowed. |
| `solver_error` | The referee could not be trusted operationally. | Process/configuration failure, malformed output, replay failure, or definitive backend disagreement. |

`unknown` and `unsupported` never promote to `verified`. A candidate solver
model never promotes to `violated` until replay against the original
obligation succeeds.

The CLI exit-code precedence is:

1. `solver_error` present: exit `3`;
2. otherwise `violated` present: exit `1`;
3. otherwise `unknown` or `unsupported` present: exit `2`;
4. otherwise: exit `0`.

Non-goals do not change the exit code.

## Verification result

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `obligation` | string | yes | Stable ID of the checked obligation. |
| `function` | string | yes | Source function name, or a synthetic owner such as `<module>`. |
| `kind` | string | yes | Obligation category copied from the obligation. |
| `status` | status string | yes | One of the five taxonomy values. |
| `location` | location | yes | Primary source location. |
| `message` | string | yes | Deterministic human-readable backend explanation. |
| `counterexample` | object | no | Sorted `int`/`bool` bindings for a replayed violation. |

Counterexample keys use IR variable names. A unique `name#0` is displayed as
`name`; later SSA versions retain `#N`. If shortening would collide, the full
versioned name is retained. Consumers must treat bindings as evidence for the
specific obligation, not as a complete execution trace.

## Obligation

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | string | yes | Deterministic `obNNNNN` identifier. |
| `function` | string | yes | Owning function or synthetic module/frontend owner. |
| `kind` | string | yes | Stable category for filtering and presentation. |
| `mode` | string | yes | `validity`, `satisfiable`, or `well_formed`. |
| `assumptions` | expression array | yes | Conjunctive path/type/contract facts. |
| `conclusion` | expression | mode-dependent | Required by validity/well-formedness; omitted for pure satisfiability. |
| `location` | location | yes | Source location that caused the obligation. |
| `description` | string | yes | Deterministic human explanation. |
| `unsupported_reason` | string | no | Fail-closed reason; checking returns `unsupported`. |

Mode semantics:

- `validity`: prove `assumptions -> conclusion`;
- `satisfiable`: find a witness for the conjunction of `assumptions`;
- `well_formed`: accept only when `conclusion` belongs to the supported logic
  fragment; it does not assert that the expression is true.

Current obligation kinds are:

- `contract_consistency` and `contract_well_formed`;
- `precondition`, `postcondition`, and `assertion`;
- `loop_invariant_entry` and `loop_invariant_preservation`;
- `division_by_zero` and `signed_overflow`;
- `missing_return`;
- `unsupported_construct` and `unsupported_logic`;
- `frontend_initialization` for structured startup failures.

New kinds require a schema/versioning decision if an existing consumer cannot
safely treat the value as an unknown category.

## Non-goal record

Non-goals are explicit scope statements, not successful or failed proof
obligations.

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `kind` | string | yes | Currently `loop_termination`. |
| `location` | location | yes | The corresponding loop statement. |
| `description` | string | yes | States that only partial correctness was checked. |

Every lowered while loop has `termination: "non_goal"` in Semantic IR and one
corresponding top-level non-goal record, including JSON emitted with `--no-ir`.

## Shared values

### Source location

| Field | Type | Contract |
| --- | --- | --- |
| `file` | string | Caller-visible path with `/` separators. |
| `line` | integer | One-based line. |
| `column` | integer | One-based containing-statement/comment column. |

### Expression

Every expression has `kind` and `type`. `type` is currently `int` or `bool`.

| Kind | Additional fields | Contract |
| --- | --- | --- |
| `constant` | `value` | JSON integer or boolean. |
| `variable` | `value` | Versioned IR symbol name. |
| `unary` | `op`, one-element `args` | `!` or unary `-`. |
| `binary` | `op`, two-element `args` | Arithmetic, comparison, equality, or boolean connective. |

The representable operators are `+`, `-`, `*`, `/`, `==`, `!=`, `<`, `<=`,
`>`, `>=`, `&&`, `||`, and unary `!`/`-`. Representation does not imply solver
support: the QF_LIA emitter rejects division and nonlinear multiplication.

## Semantic IR

### Module

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `schema` | string | yes | Same schema identifier as the report. |
| `source` | string | yes | Caller-visible source path. |
| `functions` | function array | yes | Source traversal order. |
| `unsupported` | node array | yes | Module/frontend issues in deterministic order. |

### Function

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | string | yes | Deterministic source-order function ID. |
| `name` | string | yes | Source spelling. |
| `link_name` | string | no | Present when overload disambiguation differs from `name`. |
| `return_type` | string | yes | Currently `int` or `bool`. |
| `location` | location | yes | Function declaration location. |
| `parameters` | symbol array | yes | Declaration order. |
| `locals` | symbol array | yes | Lowering/source order. |
| `contracts` | contract array | yes | Attached declaration order. |
| `body` | node array | yes | Semantic execution order. |
| `has_body` | boolean | yes | Distinguishes definitions from contracted declarations. |

### Symbol

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | string | yes | Deterministic symbol ID. |
| `name` | string | yes | Source spelling. |
| `ir_name` | string | no | Stable internal base when lexical reuse needs disambiguation. |
| `type` | string | yes | `int` or `bool`. |
| `versioned_name` | string | yes | Initial SSA name, normally `name#0`. |
| `location` | location | yes | Declaration location. |

### Contract

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `kind` | string | yes | `requires`, `ensures`, or `invariant`. |
| `expression` | expression | yes | Typed, lowered logical expression. |
| `location` | location | yes | `cs:` comment location. |
| `text` | string | yes | Normalized clause text. |
| `machine_proposed` | boolean | yes | True only for `cs: ai ...` clauses. |

### IR node

Every node has `id`, `kind`, and `location`. Optional fields are omitted when
they do not apply.

| Node kind | Required kind-specific fields |
| --- | --- |
| `assume`, `assert`, `return` | `expression`; `origin` may identify generated assumptions/returns. |
| `assign` | `target`, `expression`. |
| `call` | `callee`, optional `arguments`; result-bearing calls also have `target` and `result_type`. |
| `branch` | `expression`, optional `then`, `else`, and `merges` arrays. |
| `merge` | `target`, `incoming_true`, `incoming_false`. |
| `loop` | `expression`, `body`, `invariants`, `loop_variables`, `termination`. |
| `unsupported` | `reason`. |

Loop arrays are emitted even when empty so missing invariants remain visible in
IR. Other optional empty arrays are omitted.

### Loop variable

| Field | Type | Contract |
| --- | --- | --- |
| `name` | string | Stable IR base name. |
| `type` | string | `int` or `bool`. |
| `entry` | string | SSA value before the loop. |
| `head` | string | Fresh havoc value for an arbitrary iteration. |
| `back_edge` | string | SSA value after the symbolic body iteration. |
| `exit` | string | Fresh havoc value for the post-loop state. |

No equality between `entry`, `head`, or `exit` is implied by this metadata.

## Deterministic serialization

- JSON uses UTF-8, two-space indentation, sorted object keys, unescaped Unicode,
  and exactly one trailing newline.
- Arrays retain semantic/source order; counterexample object keys are sorted.
- Stable IDs and SSA versions are assigned in deterministic traversal order.
- Clang pointer identities, temporary parse paths, wall clock, and randomness
  never enter serialized logic artifacts.
- Fixture files under `fixtures/expected` are the byte-level examples and are
  forced to LF by `.gitattributes`.

Regenerate or check the reference bytes with:

```powershell
python tools/regenerate_fixtures.py
python tools/regenerate_fixtures.py --check
```
