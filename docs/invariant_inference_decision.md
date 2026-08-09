# Invariant-inference research decision

Status: A6.6 research result. This document does not expand the verifier's
trusted semantics or accepted C++ subset.

## Decision

Retain deterministic CHC/Spacer inference only as an optional, proposal-only
pre-pass for simple signed-linear loops. Do not integrate it into the trusted
referee or silently add its output to proof assumptions.

A proposed invariant is useful only after it is attached as
`cs: ai invariant ...` and the ordinary verifier proves loop entry, loop
preservation, and every requested downstream obligation. An inductive but weak
candidate is `insufficient`, not verified. Solver `sat`/`unknown`, timeout,
unsupported input, malformed input/output, and resource exhaustion produce no
accepted candidate.

## Measured boundary

The fixed corpus uses integer Horn clauses with one `Inv_<case>` relation,
explicit initial/transition/bad predicates, and Z3 5.0.0 Spacer. It records:

| Case | Result | Ordinary-referee outcome |
| --- | --- | --- |
| `count_exact` | `useful` | Entry, preservation, overflow, and postcondition verified. |
| `count_insufficient` | `insufficient` | Entry and preservation verified; postcondition violated. |
| `unsafe` | `no_candidate` | Spacer returned `sat`; no fact was promoted. |
| `timeout` | `timeout` | The bounded subprocess produced no candidate. |
| `unsupported` | `unsupported` | The research fragment rejects `u32`; only signed `i32` LIA is admitted. |
| `malformed` | `malformed` | A required Horn predicate is absent. |

This is evidence of value for small counter loops, not evidence that inference
is complete. The insufficient case demonstrates the key distinction: an
inductive invariant can still be too weak to establish the function contract.

## Determinism and resources

- Solver identity is pinned to `Z3 version 5.0.0 - 64 bit`.
- Commands fix SMT, SAT, and Spacer random seeds and disable parallel solving.
- Clause order, case order, JSON keys, candidates, and hashes are canonical.
- Each solver process has a positive timeout. The corpus timeout probe uses a
  deliberately sub-startup budget and is recorded as `timeout`.
- `ResearchBudget.max_solver_cases` is a deterministic count limit. Exhausted
  cases become `no_candidate` without starting a solver.
- Artifacts contain no executable path, wall-clock duration, timestamp, or
  random value.

Run the reproducibility check with:

```powershell
python tools/invariant_research.py --check
```

The committed artifact is
`benchmarks/invariant_inference/expected_candidates.json`. Two complete runs
must be byte-identical.

## Trust boundary

`semantic_verifier.invariant_research` is not imported by the main CLI,
frontend, lowering, VC generator, or checker. It emits a research query and
parses a restricted certificate language. Candidate parsing accepts only
booleans, integer literals, owned variables, comparisons, Boolean connectives,
and linear arithmetic supported by the contract parser. Unknown certificate
forms fail closed.

The candidate generator is untrusted. The validation step replaces exactly one
`// cs: candidate` marker with an explicit `// cs: ai invariant` proposal and
runs the existing pipeline with the ordinary affine/Z3 cross-check referee.
Machine provenance remains visible in Semantic IR. A candidate never changes a
verification status merely because Spacer returned `unsat`.

## Operational recommendation

If US experiments with this pre-pass, keep it opt-in and outside the
referee process. Pin the solver package, preserve the count/time limits, emit
candidate provenance, cache only canonical query/certificate identities, and
require independent replay through normal entry/preservation VCs. Expand past
signed-linear loops only through a new decision stage with typed Horn semantics
and negative-boundary tests.
