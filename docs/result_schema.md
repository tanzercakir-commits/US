# Verification Result and Semantic IR Schema Reference

## Scope and stability

The current schema identifier is `codeskeptic.semantic-verification/v2`. It
covers the verification report, obligations, results, non-goals, and the owned
Semantic IR emitted by the Python reference implementation. The deterministic
fixed-width acceptance evidence uses the separate
`codeskeptic.fixed-integer-phase-gate/v0` schema documented in
[the integer operations runbook](integer_operations.md); it is not a report.

F4.1 froze v0 as the first fixture-backed compatibility baseline. A4.1 moved to
v1 for minimized public counterexample cores. A6.8 moves to v2 for explicit
fixed-width type identities and canonical decimal-string integer evidence.
Consumers must check `schema`, ignore unknown object fields only within that
known major, and fail closed on unknown status/mode/kind values. The complete
[version and migration policy](schema_versioning.md) defines compatibility and
preserves the v0 and v1 corpora.

## Report envelope

JSON output has this shape:

```json
{
  "non_goals": [],
  "obligations": [],
  "results": [],
  "schema": "codeskeptic.semantic-verification/v2",
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
| `violated` | The declared obligation is false. | A complete validity countermodel replayed internally before a sufficient public binding core was minimized, or requirements were proved infeasible. |
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

## Persistent obligation-result cache

`--cache PATH` enables an opt-in local JSON cache with schema
`codeskeptic.obligation-result-cache/v0`. Cache files are optimization state,
not part of the report envelope; cold and warm runs emit byte-identical reports.
The cache contains a sorted `entries` object keyed by lowercase SHA-256 digest.

The canonical key payload binds:

- `codeskeptic.obligation-semantic-key/v0` and the current report/IR schema;
- backend identity, implementation policy, nested cross-check identities, and
  result-relevant configuration such as the Z3 executable and timeout;
- obligation mode, conclusion or explicit null, and unsupported reason;
- assumptions serialized with sorted object keys and sorted as a conjunction.

IDs, function/kind labels, descriptions, source locations, and trace locations
are excluded because they do not alter the logical query. A matching entry is
accepted only when its stored key payload exactly equals the current payload.
Trace-template semantics are also matched before cached diagnostic directions
are attached to current source locations. Result obligation ID, function, kind,
primary location, and trace locations are always reconstructed from the current
obligation.

Missing files and keys, unknown cache schemas, changed report schemas, backend
or configuration changes, malformed JSON/entries/statuses/evidence, and trace
metadata mismatches all cause ordinary backend recomputation. Read, directory,
write, or atomic-replace failures do not change the returned referee result.
`solver_error` is deliberately neither stored nor reused, because an
operational failure may disappear without any semantic configuration change.

A syntactically valid matching cache entry is trusted derived state. Keep cache
files inside the same access boundary as verifier outputs and do not restore
one from an untrusted source. Counterexample bindings in the cache have the same
retention sensitivity as report artifacts. Delete the file to force a cold run;
manual editing is unsupported.

## Resource budgets

External Z3 processes use a positive finite `SolverTimeout`; the CLI default is
5 seconds and `--solver-timeout SECONDS` changes it. The same value is passed to
Z3 in milliseconds and to the host process. A timeout before replayable evidence
exists returns explicit `unknown`. In cross-check mode that resource result is
not strengthened to `verified` by the other backend. A timeout during optional
counterexample-core minimization keeps already replayed definitive evidence and
only prevents removal of the affected binding.

`--max-checks N` sets a deterministic `FileCheckBudget`; omission means
unlimited and zero starts no supported checks. One unit is consumed when a
supported top-level obligation is started, in serialized source order. The
counter resets for each pipeline `check_all` file boundary. Unsupported
obligations retain `unsupported` and do not consume a supported-check unit.
Cross-checking both referees is one top-level unit. Internal solver calls and
affine search evaluations are deliberately not additional file units.

Every supported obligation beyond the limit receives `unknown` with a message
that states the configured limit and that the obligation was not started.
Results already produced remain unchanged, status/exit precedence is unchanged,
and repeated budgeted reports are byte-identical. The budget wrapper is outside
the persistent cache, so a warm definitive entry cannot bypass a lower current
file budget.

## Verification result

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `obligation` | string | yes | Stable ID of the checked obligation. |
| `function` | string | yes | Source function name, or a synthetic owner such as `<module>`. |
| `kind` | string | yes | Obligation category copied from the obligation. |
| `status` | status string | yes | One of the five taxonomy values. |
| `location` | location | yes | Primary source location. |
| `message` | string | yes | Deterministic human-readable backend explanation. |
| `counterexample` | object | no | Sorted bindings: fixed-width integers are canonical decimal strings; booleans are JSON booleans. |
| `trace` | trace-step array | no | Source-ordered branch decisions leading to a violated obligation. |

For a violated validity obligation, the backend first replays a complete model
against the original assumptions and conclusion. Relevance projection seeds the
variable cone from the conclusion and transitively includes every variable that
co-occurs in a connected assumption; bindings outside that cone are never
reported. The minimizer then tries remaining bindings in sorted variable order.
A binding is removed only when exact backend reasoning proves that the original
assumptions plus the retained equalities imply the negated conclusion. Solver
uncertainty or an emission failure keeps an in-cone binding. The public object
can therefore be empty, and it is not a standalone replay model. Consumers must
interpret it together with the referenced obligation's `assumptions`.

Every fixed-width integer counterexample value is serialized as a canonical
base-10 string (`0` or an optional leading `-` followed by nonzero digits).
This avoids JSON-number precision loss for u64. Boolean bindings remain JSON
booleans. Cache entries use the same evidence encoding; internal referee values
remain Python integers and booleans.

Counterexample keys use IR variable names. A unique `name#0` is displayed as
`name`; later SSA versions retain `#N`. If shortening would collide, the full
versioned name is retained. Consumers must treat the minimized bindings as
evidence for the specific obligation, not as a complete input or execution
trace.

### Branch trace step

`trace` is emitted only for a `violated` result when its VC path crossed at
least one source branch. It is explanatory metadata; the serialized obligation
assumptions remain the canonical logical path, and a trace never changes a
status or replaces replay evidence. Steps retain outer-to-inner path order.

| Field | Type | Contract |
| --- | --- | --- |
| `kind` | string | Currently `branch`. |
| `condition` | expression | Versioned boolean condition evaluated at the branch. |
| `taken` | boolean | `true` for the then edge, `false` for the else/fallthrough edge. |
| `location` | location | Source location of the branch statement. |

At a compact structured join, branch provenance is stored internally as guarded
trace templates instead of enumerated path alternatives. Only after the complete
countermodel replays are active guards and condition directions evaluated into
the public steps above. Resolution failure is fail-closed as `solver_error`.

Human-readable result output renders the same fields as, for example,
`when branch condition (x#0 > 0) is true at trace.cpp:3:5`. A result with no
source branch omits `trace`; an empty array is not emitted.

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

A single obligation may represent the exact disjunction of several incoming
structured paths after a branch join. Consumers must not infer one obligation
or result per enumerated source path; the serialized assumptions remain the
complete formula.

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

New kinds require review under the
[schema version policy](schema_versioning.md). Existing consumers must treat an
unknown category as fail-closed.

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

### Integer target profile

Before lowering, Clang must accept the pinned
`codeskeptic.cxx17-fixed-integers/i32-u32-i64-u64-twos-complement-arshift/v0`
probe: 8-bit bytes, 32-bit `int`/`unsigned int`, 64-bit `long long`/`unsigned
long long`, arithmetic signed right shift, and the selected two's-complement
signed narrowing behavior. Failure is a deterministic `solver_error`; source
is never lowered under a different target.

### Source location

| Field | Type | Contract |
| --- | --- | --- |
| `file` | string | Caller-visible path with `/` separators. |
| `line` | integer | One-based line. |
| `column` | integer | One-based containing-statement/comment column. |

### Expression

Every expression has `kind` and `type`. v2 type identities are `bool`, `i32`,
`u32`, `i64`, and `u64`; the current source subset emits all five identities.

| Kind | Additional fields | Contract |
| --- | --- | --- |
| `constant` | `value` | Canonical decimal string for fixed-width integers; JSON boolean for `bool`. |
| `variable` | `value` | Versioned IR symbol name. |
| `unary` | `op`, one-element `args` | `!` or unary `-`. |
| `cast` | `op`, one-element `args` | `integral`; bool-to-fixed-width or any owned fixed-width conversion under the pinned profile. |
| `binary` | `op`, two-element `args` | Arithmetic, comparison, equality, or boolean connective. |
| `predicate` | `op`, one-element `args` | `signed_no_overflow` for mixed arithmetic or `signed_left_shift_defined` for C++17 left-shift safety. |

The representable operators are `+`, `-`, `*`, `/`, `%`, `~`, `&`, `|`, `^`,
`<<`, `>>`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, and unary `!`/`-`.
Any expression containing `u32`/`u64` or a bitwise/shift operator selects
homogeneous QF_BV: every fixed-width term in that obligation is
a width-matching bitvector, with signed/zero extension, truncation, modulo
arithmetic, and signed/unsigned comparisons. Signed-only obligations remain
QF_LIA, where exact division/remainder requires a literal divisor and
variable-by-variable multiplication is rejected. Clang-resolved operands and
contracts follow the frozen usual-arithmetic-conversion table. Signed
arithmetic retains width-specific overflow VCs; unsigned arithmetic wraps
modulo `2^width`. In QF_BV, `signed_no_overflow` compares the signed operation
at double width with the sign-extension of its wrapped result, so mixed
signed-result arithmetic cannot turn undefined overflow into a proof. Shift
counts require `0 <= count < promoted-left width`; signed left shift uses a
zero-extended double-width equality plus a nonnegative left operand, while
signed right shift is arithmetic under the pinned profile. Both lanes require
nonzero divisors, and signed division/remainder also excludes the type minimum
with `-1`.

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
| `return_type` | string | yes | v2 type identity; currently emitted as `i32`, `u32`, `i64`, `u64`, or `bool`. |
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
| `type` | string | yes | v2 type identity; currently emitted as `i32`, `u32`, `i64`, `u64`, or `bool`. |
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
| `type` | string | v2 type identity; currently emitted as `i32`, `u32`, `i64`, `u64`, or `bool`. |
| `entry` | string | SSA value before the loop. |
| `head` | string | Fresh havoc value for an arbitrary iteration. |
| `back_edge` | string | SSA value after the symbolic body iteration. |
| `exit` | string | Fresh havoc value for the post-loop state. |

No equality between `entry`, `head`, or `exit` is implied by this metadata.

## Deterministic serialization

- JSON uses UTF-8, two-space indentation, sorted object keys, unescaped Unicode,
  and exactly one trailing newline.
- Arrays retain semantic/source order, including outer-to-inner trace steps;
  minimized counterexample-core keys are sorted.
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
