# Path Scaling Measurement and Merge-Point Decision

## Decision

Add A5.5 to implement exact structured merge-point compaction before the cache
stage. A join will represent the union of its reachable incoming states as a
factored disjunction of conjunctions. It will not discard a path, guess logical
subsumption, or ask an incomplete backend to justify a merge.

Branch explanations must survive compaction. A5.5 will replace eagerly copied
path traces at joins with compact guarded trace templates. After a complete
countermodel replays, the backend resolves only templates whose guards hold and
uses the model value of each branch condition to produce the existing ordered
`TraceStep` values. Diagnostic provenance remains outside proof status.

## Measurement method

`tools/path_scaling_probe.py` generates functions containing sequential empty
`if/else` diamonds followed by one assertion. It runs the ordinary Clang,
lowering, and VC path but replaces the referee with an `unknown` measurement
backend, so counts do not depend on solver behavior or time. The default cases
are 1, 2, 4, and 8 diamonds; the tool caps input at 12 to prevent accidental
unbounded local work.

Output uses `codeskeptic.path-scaling-probe/v0`, sorted JSON keys, stable display
paths, no timing values, and one trailing newline. Two independent renderings
must be byte-identical.

## Baseline results

Measured on 2026-08-06 with the A5.1 baseline:

| Diamonds | Source bytes | IR nodes | Assertion obligations | Unique semantic keys | Maximum assumptions |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 114 | 3 | 2 | 2 | 3 |
| 2 | 148 | 4 | 4 | 4 | 4 |
| 4 | 216 | 6 | 16 | 16 | 6 |
| 8 | 352 | 10 | 256 | 256 | 10 |

The path count and post-join obligation count are exactly `2^diamonds`. There
are zero exact duplicate obligations in every case. Source and IR grow linearly
while proof work grows exponentially. Exact duplicate removal alone therefore
does not address even the empty-diamond baseline.

## Exact semantic key

The probe key is SHA-256 over canonical UTF-8 JSON containing:

- the current report/IR schema;
- obligation mode;
- assumptions encoded independently with sorted JSON keys, then sorted as a
  conjunction (assumption order is not semantic);
- conclusion or explicit `null`;
- `unsupported_reason` or explicit `null`.

It excludes obligation ID, function, kind, source location, description, and
trace because those are result/report metadata rather than the logical query.
The A5.2 cache must additionally include backend identity/configuration and
solver policy as already required by PLAN.md.

Only identical keys prove exact query equality. Key equality can support safe
deduplication or cache reuse; key inequality says nothing about implication.

## Rejected shortcuts

- Dropping either side of a branch is unsound because the removed path may
  contain the only violation.
- Treating a strict superset of assumptions as redundant without a proved
  implication can erase a reachable program state and its counterexample.
- Comparing source spelling, obligation IDs, or hashes that omit integer/schema
  policy can reuse a result for a different formula.
- Using affine-checker failure or finite-search exhaustion as a subsumption
  proof would promote incompleteness into a proof claim.
- Eagerly retaining every complete trace alternative after merging formulas
  moves the same exponential growth into diagnostic metadata.
- General BDD/SMT simplification at this stage adds a second logic engine and a
  new trust surface before the structured merge case is exhausted.

## Chosen A5.5 architecture

For each structured join:

1. preserve each incoming state formula as the conjunction of its assumptions;
2. factor assumptions structurally common to every incoming state;
3. add the disjunction of the residual conjunctions, simplifying only exact
   boolean identities implemented and tested by the verifier;
4. deduplicate only byte/structure-identical states and facts;
5. retain compact guarded branch-trace templates in deterministic source order;
6. keep trace-condition variables declared without constraining their values;
7. resolve templates only after the complete model replays, before public core
   minimization discards irrelevant values.

The resulting formula is logically equivalent to the union of incoming states.
Factoring and exact identities change representation, not meaning. If a state
cannot be represented or a trace cannot be resolved, the optimization must
fall back to unmerged states or fail closed; it must not report `verified` from
an approximation.

## Acceptance target

A5.5 must reduce the post-join assertion obligations for 1/2/4/8 empty diamonds
from 2/4/16/256 to 1/1/1/1 while preserving verdicts and replayable true/false
branch explanations. Assignment-bearing and nested diamonds need independent
equivalence tests. A5.2 and A5.4 depend on A5.5.

## A5.5 implementation evidence

The structured join now factors assumptions common to every incoming state,
forms one source-ordered disjunction of the residual conjunctions, and removes
only states with identical assumption sets. It deliberately retains exact
boolean tautologies when they carry branch variables required for trace model
resolution.

The same deterministic probe now reports one post-join assertion obligation for
each 1/2/4/8 case: `1/1/1/1` instead of `2/4/16/256`. Source bytes, IR node
counts, expected path counts, and maximum assumption counts remain unchanged.
The optimization moves the path union into one exact formula rather than
silently removing reachable executions.

Nested and assignment-bearing diamonds are checked against a test-only unmerged
VC generator with Z3. A compact query is `verified` exactly when all reference
path queries are verified, and a compact violation is retained when any
reference path violates. The accepted nested violation resolves both guarded
branch templates to the true edge; independent post-join regressions force true
and false directions separately.

The affine backend performs deterministic exact case splitting on disjunctive
assumptions before its ordinary proof rules. This preserves prior affine proofs;
finite search remains a witness mechanism and is never promoted to proof.
Unresolvable trace templates turn a candidate Z3 violation into `solver_error`
before any public counterexample is emitted.
