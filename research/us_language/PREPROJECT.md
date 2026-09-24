# US Language — Pre-project Research Brief

Status: **pre-project / PRACTICAL research lane**

This brief authorizes research only. It does not change the current US product
queue, verifier semantics, supported C++ boundary, or the meaning of
`verified`.

## 1. Research question

Can a compact, structured language make AI-generated software preserve human
intent, architecture, constraints, and explicitly delegated choices better
than a strong prose/Markdown specification containing the same information?

The key comparison is not "structured input versus vague prompt." Both sides
must receive the same facts. The experiment is about representation.

## 2. Working thesis

Source code increasingly becomes an implementation artifact that an AI can
regenerate. The durable artifact may instead be the information that explains
what the system is meant to be and which choices are fixed versus delegated.

The candidate US Language surface starts with six concepts:

- `intent` — goals and rationale that must survive implementation changes;
- `architecture` — components, dependency directions, and structural
  boundaries;
- `rules` — invariants, contracts, permissions, and prohibited outcomes;
- `freedom` — choices intentionally delegated to the implementation agent;
- `flow` — expected behavior, state transitions, and error paths;
- `unknowns` — unresolved decisions the agent must expose rather than silently
  invent.

These names are hypotheses, not frozen syntax.

## 3. Illustrative shape

```text
system ReportBuilder

intent:
    Produce reports without modifying source data.

architecture:
    UI -> ReportService
    ReportService -> DataReader
    UI !-> DataReader

rules:
    source_data is immutable
    network_access is forbidden
    read_failure != empty_result

freedom:
    internal data structures may change
    cache implementation may change

unknowns:
    cache eviction policy is not decided

flow build_report(query):
    rows = DataReader.read(query)

    if read fails:
        return ReadFailure

    if rows is empty:
        return EmptyReport

    return Renderer.render(rows)
```

This is illustrative pseudocode, not a parser contract.

## 4. Why this belongs in US

US already owns several independent pieces needed to test the idea without
making the AI its own judge:

- contract-first intent artifacts and human approval boundaries;
- contract adapters that lower supported predicates to one internal contract;
- a deterministic semantic referee with explicit
  `verified/violated/unknown/unsupported/solver_error` outcomes;
- a fact index/world model;
- deterministic architectural dependency policies and checks.

US Language can therefore begin as an input/representation experiment above
those components. Machine-checkable fragments may later lower to existing US
artifacts, while non-machine-checkable intent remains explicitly labeled as
human-reviewed rather than "proved."

## 5. Current boundaries

During the PRACTICAL research lane:

- work stays under `research/us_language/` unless an explicit PLAN stage says
  otherwise;
- no production verifier/frontend/parser semantics are changed;
- no shared wire schema is changed;
- no public claim says US is already a programming language;
- D2 and D13 remain in force;
- the AI may propose designs and implementations, but it is not the referee.

A research-only parser, renderer, fixture set, or benchmark harness may be built
inside this directory after the experiment contract is frozen. Moving any such
component into production code requires a new PLAN stage and at least REVIEWED
governance.

## 6. First controlled experiment

### Conditions

A. **Structured US condition** — the candidate structured representation.

B. **Markdown condition** — a carefully written Markdown specification carrying
the same requirements, architecture, freedoms, unresolved questions, and flow
information.

No fact may appear in only one condition.

### Pilot task

Start with a small report builder because it can express all six candidate
concepts without requiring a UI, network service, or database.

Frozen requirements should include at least:

- source records are immutable;
- network access is forbidden;
- read failure and empty data are distinct outcomes;
- UI may not call DataReader directly;
- implementation may choose internal data structures;
- cache mechanics are delegated but an unresolved eviction policy must not be
  silently invented.

After initial implementation, apply at least two maintenance changes such as
CSV output and an in-memory cache. The important question is whether earlier
intent and architecture survive later edits.

### Evidence

Prefer deterministic evidence:

- functional hidden tests;
- architecture-policy checks;
- contract/verifier checks for expressible rules;
- explicit counts of preserved/violated requirements;
- token/cost measurements kept separate from correctness.

Any human judgment must be labeled separately and must not be silently converted
into proof.

## 7. Experiment-design safeguards

Before running model trials:

1. freeze the information-equivalent US and Markdown inputs;
2. freeze tasks, maintenance changes, hidden checks, model/settings, repetition
   count, and scoring rules;
3. prevent the implementation agent from seeing hidden expected results;
4. keep machine-verifiable and human-reviewed outcomes separate;
5. record failures and unsupported cases rather than repairing the benchmark
   after seeing results.

The first experiment is allowed to falsify the idea.

## 8. Promotion gates

### Gate A — from concept to research prototype

Required:

- candidate representation is written down;
- Markdown baseline has information parity;
- first task and maintenance changes are frozen;
- scoring has a deterministic core.

### Gate B — from research prototype to broader benchmark

Required:

- the pilot runs end to end;
- any apparent advantage can be explained without giving US extra information
  or extra verifier access;
- failures are retained, not edited away.

### Gate C — from research to US product integration

Required:

- repeated evidence shows a useful representation effect rather than a
  one-example prompt effect;
- integration boundaries are specified;
- shared schema/IR/parser changes receive a new explicit PLAN stage;
- governance escalates to REVIEWED for material shared-interface changes.

A negative result stops or redesigns the language track without affecting the
existing verifier roadmap.

## 9. Candidate research sequence

This is a pre-project sequence, not yet part of the generated production TODO.

1. Freeze the minimal representation and its semantics.
2. Create the information-equivalent Markdown baseline.
3. Freeze one end-to-end pilot and deterministic checks.
4. Run repeated initial-generation and maintenance trials.
5. Analyze error classes, not just pass/fail totals.
6. Decide: stop, revise the representation, or expand the benchmark.
7. Only after a positive gate, prototype a parser/IR mapping under
   `research/us_language/`.
8. Only after a later integration gate, propose production PLAN stages.

## 10. Governance classification

- Pre-project documents, research fixtures, and reversible isolated prototypes:
  **PRACTICAL**.
- Shared grammar/schema contracts, production parser/IR integration, or
  material cross-module compatibility changes: **REVIEWED**.
- Security/authentication, release integrity, protected-state, destructive
  migration, or other high-assurance boundaries: **STRICT**.

The cheapest evidence that can falsify the relevant failure mode should be used.
Do not build release-grade governance machinery for a research fixture.

## 11. Start condition for the next session

The next session may begin research implementation only after reading:

1. `AGENTS.md`;
2. `TODO.md` and the current production status;
3. PLAN decisions D17-D19;
4. this brief.

The research lane must remain isolated. The production TODO continues to name
A7.4 as the verifier-roadmap front unless the owner later records a different
production priority.
