# Minimal US Representation v0

This freezes semantics, not a parser grammar.

Every model-facing US specification contains six explicit sections. A section
may be empty only by saying `none`. Every normative fact has one stable fact ID.

## 1. intent

Meaning: durable goal or rationale that implementation and maintenance must
preserve.

- Intent is normative.
- Intent does not prescribe an algorithm unless the statement explicitly does.
- Missing intent is unspecified, not permission to invent a goal.

## 2. architecture

Meaning: named components, responsibilities, and dependency boundaries.

- `A -> B` means A may directly depend on/call B.
- `A !-> B` means A must not directly depend on/call B.
- An omitted edge is unspecified; omission is not an implicit prohibition.
- Architecture statements do not imply runtime success or proof.

## 3. rules

Meaning: mandatory invariants, prohibitions, and distinctions.

- `must` and `must_not` are normative.
- `distinct` means two outcomes must remain observably distinguishable.
- A rule is not delegated merely because implementation details are absent.

## 4. freedom

Meaning: an implementation choice intentionally delegated to the agent.

- `may_choose X` permits choosing X subject to all intent, architecture,
  rules, flow, and unknowns.
- Freedom is explicit; absence of a freedom statement is not a grant.
- Freedom cannot override a rule or resolve an unknown.

## 5. flow

Meaning: required externally observable behavior and branch ordering.

- A flow specifies required cases and outcomes, not internal algorithm steps
  unless explicitly stated.
- Error branches are first-class and must not be collapsed into success cases.

## 6. unknowns

Meaning: a decision intentionally unresolved by the human specification.

- `unresolved X` forbids silently selecting a value for X.
- If implementation can proceed without X, X stays unresolved.
- If a requested feature depends on X, the implementation must require an
  explicit external choice or fail/expose the unresolved decision.
- There is no default selection unless the specification later supplies one.

## Surface shape

The v0 research surface uses simple labeled sections and one fact per line.
Fact IDs are experimental parity anchors, not proposed production syntax.

```text
system <name>

intent:
    [F..] <statement>

architecture:
    [F..] <edge or boundary>

rules:
    [F..] <normative statement>

freedom:
    [F..] may_choose <choice>

flow:
    [F..] <condition> => <outcome>

unknowns:
    [F..] unresolved <decision>
```

No inference beyond the semantics above is part of v0.
