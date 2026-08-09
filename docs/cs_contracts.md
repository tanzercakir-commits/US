# `cs:` contract comments

The `cs:` syntax is an optional US input adapter for projects that do not use
C++26 contracts. It is made of ordinary C++ line comments. The adapter turns
them into the same internal contracts used by the
[C++26 adapter](cpp26_contracts_bridge.md).

## Contract forms

```cpp
// cs: requires <boolean expression>
// cs: ensures <boolean expression>
// cs: modifies <target, ...>
// cs: invariant <boolean expression>
```

- `requires` states what must be true before a function call.
- `ensures` states what must be true after normal return. `result` and `return`
  both name the returned value.
- `modifies` lists mutable reference parameters, or their fields, that may
  change. An empty `// cs: modifies` states that none may change.
- `invariant` states a property that must hold when a supported `while` loop is
  entered and after each modeled iteration.

Place a contiguous `requires`, `ensures`, and `modifies` comment block directly
before the function. Place a contiguous `invariant` block directly before its
`while` statement. A misplaced or malformed `cs:` comment is reported as
unsupported.

## Expressions

The expression subset includes:

- integer and Boolean literals;
- parameters and other names available at the attachment point;
- `result` or `return` inside `ensures`;
- record fields and supported fixed-size array indexing;
- `+`, `-`, `*`, `/`, `%`, `~`, `&`, `|`, `^`, `<<`, and `>>`;
- `==`, `!=`, `<`, `<=`, `>`, and `>=`;
- `!`, `&&`, `||`, and parentheses.

Parsing an expression does not guarantee that the current verifier backend can
prove it. Unsupported operations and semantics remain explicit non-verified
results.

## AI proposals

For critical functions, save the AI-generated proposal as a separate review
artifact before implementation. After human approval, freeze that artifact and
encode the same contract in the source with either the C++26 or `cs:` adapter.

The current US CLI does not read the review artifact as direct sidecar input.
The source-level contract remains the verifier input, and it must keep the same
meaning as the approved artifact.

An inline `cs:` proposal may retain its origin with an `ai` marker:

```cpp
// cs: ai requires amount >= 0
// cs: ai ensures result >= 0
```

The marker identifies a proposal. In the contract-first workflow, a human must
review the intended behavior and remove `ai` before the contract is accepted.
The AI does not decide whether its proposal is verified.

## Example

```cpp
// cs: requires amount >= 0
// cs: requires balance >= amount
// cs: ensures result >= 0
int withdraw(const int balance, const int amount) {
    return balance - amount;
}
```

The complete supported C++ and semantic boundary is documented in
[Semantic verification prototype](semantic_verification_prototype.md).
