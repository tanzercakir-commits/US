# Referee-as-reward research memo

Status: design only. No collector, executable schema, training loop, model call,
optimizer, reward service, or training result exists in this repository.

## Purpose

This memo describes a possible future offline research protocol for recording
ordinary US referee outcomes as a bounded categorical reward signal.
The AI remains an untrusted candidate proposer. The deterministic verifier and
its replay rules remain the only acceptance authority.

The design has three goals:

1. preserve enough immutable evidence to reproduce every reward decision;
2. prevent incomplete or operational failures from becoming positive reward;
3. retain every sampled candidate so selection and early-stop bias are visible.

This is not a recommendation to train or deploy a model. It does not specify a
vendor, model, optimizer, loss function, serving architecture, or production
data pipeline. It does not claim model improvement, generalization,
consciousness, or causality.

## Trust boundary

The proposer may supply arbitrary text, malformed edits, stale identities,
contract changes, or attempts to trigger unsupported and checker-error paths.
Nothing asserted by the proposer contributes to reward eligibility.

The trusted decision path is:

    frozen sample + frozen candidate
        -> strict structural and lineage validation
        -> ordinary verifier under an exact configuration
        -> required counterexample replay
        -> categorical terminal class
        -> eligibility gate
        -> fixed reward mapping
        -> append-only raw event

Hashes and links prove which artifacts were used, not that the linked referee
was correct. Correctness still depends on the versioned frontend, lowering,
verification-condition generator, checker, and replay implementation. Their
identities therefore belong in every event.

## Normative terminal state machine

The draft uses only two eligible rewards: exact rational `1/1` for complete
verification and `0/1` for a replay-attested violation. Every other class has a
null reward. This avoids silently interpreting an infrastructure or coverage
failure as a useful negative example.

| Terminal class | Required evidence | Eligibility | Draft reward |
| --- | --- | --- | --- |
| `verified` | Every target obligation is `verified`; no module unsupported node; source lineage and contracts preserved | `eligible` | `1/1` |
| `violated_replayed` | At least one concrete violation; all required counterexamples replay exactly; no disqualifying status | `eligible` | `0/1` |
| `unknown` | Any required obligation is `unknown` | `ineligible` | `null` |
| `unsupported` | Any required construct or module node is unsupported | `ineligible` | `null` |
| `solver_error` | Solver process, protocol, parse, or checker failure | `ineligible` | `null` |
| `frontend_error` | Frontend initialization or parse failure | `ineligible` | `null` |
| `malformed` | Candidate/event syntax or strict-schema failure | `ineligible` | `null` |
| `stale` | Dataset, source, proposal, config, or evidence identity mismatch | `ineligible` | `null` |
| `contract_changed` | Candidate changes, removes, or adds protected intent | `ineligible` | `null` |
| `partial` | Missing obligation, result, candidate, replay, or accounting row | `ineligible` | `null` |
| `replay_failed` | A claimed violation cannot replay against its original obligation | `ineligible` | `null` |
| `leakage_detected` | Split, oracle, hidden-test, or protected-answer contamination | `ineligible` | `null` |

Precedence is fail-closed. If evidence satisfies more than one row, any
ineligible row wins. `verified` is impossible when an unknown, unsupported, or
error status is present. A timeout is an operational error, never a weak
violation. Human preference and proposer confidence cannot override the table.

## Draft event data contract

The name `codeskeptic.rlvf-reward-event/draft-v0` is descriptive and is not an
executable schema. A future implementation must review and version it rather
than treating this memo as wire compatibility.

| Field | Draft type | Meaning and constraint |
| --- | --- | --- |
| `schema` | string | Exact draft schema name |
| `id` | SHA-256 identity | Content identity over every field except `id` |
| `dataset_snapshot` | SHA-256 identity | Immutable complete dataset manifest |
| `split_snapshot` | SHA-256 identity | Immutable grouping and train/validation/test assignment |
| `sample` | SHA-256 identity | Exact task, source, target, contracts, and permitted context |
| `candidate` | SHA-256 identity | Exact candidate record, including generation rank |
| `proposal` | SHA-256 identity | Exact untrusted patch proposal |
| `base_source_sha256` | SHA-256 identity | Source to which the proposal claims to apply |
| `candidate_source_sha256` | SHA-256 identity or null | Applied source; null when structural application fails |
| `target` | object | Canonical source path, function key, and obligation scope |
| `referee` | object | Frontend/lowering/VC/checker/replay names, versions, and configuration hash |
| `results` | sorted array | Every required obligation ID, kind, and raw status; never success-only |
| `counterexamples` | sorted array | Exact counterexample and obligation identities, when produced |
| `replay` | object | Whether replay was required, its terminal status, and evidence identity |
| `terminal` | enum | Exactly one terminal class from the normative table |
| `eligibility` | enum | `eligible` or `ineligible`, derived from `terminal` and completeness |
| `reward` | rational or null | Canonical reduced rational for eligible rows; null otherwise |
| `rejection_reason` | string or null | Deterministic reason for every ineligible row |
| `provenance` | object | Candidate generator class/version/config, run manifest, and parent identities |

All object keys are exact. Unknown fields, duplicate JSON keys, non-finite
numbers, booleans in integer fields, unsafe paths, invalid UTF-8, NUL, stale
hashes, unsorted repeated fields, and non-reduced rationals fail closed.

Illustrative canonical content, before computing `id`:

```json
{
  "base_source_sha256": "sha256:<64 lowercase hex>",
  "candidate": "sha256:<64 lowercase hex>",
  "candidate_source_sha256": "sha256:<64 lowercase hex>",
  "counterexamples": [],
  "dataset_snapshot": "sha256:<64 lowercase hex>",
  "eligibility": "eligible",
  "proposal": "sha256:<64 lowercase hex>",
  "provenance": {
    "generator": "recorded-external-model/draft",
    "generator_config": "sha256:<64 lowercase hex>",
    "run": "sha256:<64 lowercase hex>"
  },
  "referee": {
    "checker": "codeskeptic.affine/v1",
    "configuration": "sha256:<64 lowercase hex>",
    "frontend": "clang-json/<pinned-version>",
    "lowering": "codeskeptic.semantic-ir/<pinned-version>",
    "replay": "codeskeptic.counterexample-replay/<pinned-version>",
    "vc_generator": "codeskeptic.vc/<pinned-version>"
  },
  "rejection_reason": null,
  "replay": {
    "evidence": null,
    "required": false,
    "status": "not_required"
  },
  "results": [
    {
      "kind": "postcondition",
      "obligation": "sha256:<64 lowercase hex>",
      "status": "verified"
    }
  ],
  "reward": {
    "denominator": 1,
    "numerator": 1
  },
  "sample": "sha256:<64 lowercase hex>",
  "schema": "codeskeptic.rlvf-reward-event/draft-v0",
  "split_snapshot": "sha256:<64 lowercase hex>",
  "target": {
    "function": "example(int)",
    "scope": "all-target-obligations",
    "source": "dataset/example.cpp"
  },
  "terminal": "verified"
}
```

The placeholder values make this example non-executable by design. A real
event identity must cover a canonical envelope naming the identity algorithm
and draft schema. Line endings and paths need one documented normalization
policy before collection begins.

## Dataset, split, and sampling protocol

The dataset snapshot freezes sources, contracts, permitted proposer context,
hidden referee inputs, ownership/licensing metadata, and task identities before
candidate generation. The split snapshot is a separate immutable artifact.

Related functions must be grouped before assignment. At minimum the grouping
key includes source ancestry, repository origin, normalized function family,
contract ancestry, generated variants, bug seed, and repair oracle ancestry.
No group may cross train, validation, and final-test splits. Near-duplicate and
templated sources require content and semantic similarity review before the
split is frozen.

Candidate count and sampling policy are fixed before observing referee results.
For independent Best-of-N data, every candidate applies to the same original
source and all N rows are retained. Evaluation continues after success. A
sequential repair trajectory is a different protocol and must link every state
transition explicitly; it cannot be mixed into independent-candidate events.

Raw collection retains malformed, stale, unknown, unsupported, and failed
rows. Derived training views may filter only through a versioned, content-
addressed query whose inputs include the raw manifest. Success-only exports,
unrecorded retries, best-run selection, and deletion of inconvenient outcomes
are forbidden.

The E2 and E4 recorded scripted proxies are protocol fixtures. In particular,
the E4 candidates are oracle-seeded. They must not be represented as external
model samples or used to claim a model-training effect.

## Append-only storage and determinism

Raw reward events are immutable and append-only. Corrections append a new event
that names the superseded event and the reason; they never rewrite or delete
the original. Dataset, split, generator, referee, and query manifests are also
content-addressed.

The logic path uses no wall clock, random value, host-dependent path, mutable
environment default, or network result. If sampling needs randomness, a future
protocol must freeze the algorithm and seed in the run manifest before any
outcome is observed; the resulting candidate identities, not the random API,
are the referee inputs. Wall-clock timing may be stored in a separate
operational log and cannot influence reward, order, identity, or eligibility.

All summaries are derived. Recomputing the same raw manifest with the same
versioned query must produce identical bytes. An aggregate is never evidence
for an individual reward event.

## Reward-hacking threat model

| Threat | Required mitigation |
| --- | --- |
| Delete or weaken contracts | Exact protected-contract comparison; classify `contract_changed`; null reward |
| Trigger unsupported lowering | Preserve raw unsupported status; classify `unsupported`; null reward |
| Force timeout or checker crash | Classify operational error; null reward; never retry invisibly |
| Exploit stale source or config | Exact source/proposal/referee hashes checked before evaluation |
| Cherry-pick retries or stop after success | Predeclare N; retain every rank and every retry identity; evaluate all N |
| Duplicate an easy candidate | Candidate identities unique within a sample; duplicate rows remain auditable and cannot inflate counts |
| Leak hidden tests, oracle, or final split | Freeze permitted context; ancestry-grouped splits; contamination scan; invalidate affected events |
| Exploit a verifier bug | Pin versions; adversarial regression corpus; independent replay; append correction events after disclosure |
| Forge result or replay evidence | Recompute from exact source/config; content-address full results and replay artifact |
| Optimize proxy fixture labels | Keep scripted/oracle-seeded fixtures out of model-evidence datasets |
| Hide negative or ineligible rows | Append-only raw manifests and completeness/accounting queries |
| Encode sensitive or unlicensed source | Admission review, least-retention policy, access control, deletion policy defined before collection |

No mitigation makes the verifier omniscient. Differential checking, adversarial
holdouts, human review of high-impact samples, and verifier-version comparison
may be useful research controls, but none may silently replace the ordinary
referee decision recorded by an event.

## Audit and replay requirements

A release candidate for a future dataset must answer these queries exactly:

- Are there positive rewards with any non-`verified` result, unsupported node,
  changed contract, stale link, or missing obligation? Expected count: zero.
- Are there ineligible events with non-null rewards? Expected count: zero.
- Does every replay-required event cite one exact successful replay artifact?
- Does every predeclared sample contain its full candidate/rank accounting,
  including candidates after the first success?
- Do any ancestry groups or candidate identities cross frozen splits?
- Do all event referee configurations belong to the declared run manifest?
- Can every event and aggregate be regenerated byte-for-byte after relocation?
- Do raw terminal-class counts equal the derived-view inclusion plus exclusion
  counts, with no dropped row?

Replay failure invalidates eligibility; it does not relabel a violation as
verified. Missing binaries, unavailable exact versions, corrupted artifacts,
or nondeterministic reproduction block dataset release until resolved. An
operator may append a superseding event only after the original failure remains
visible.

## Retention and privacy

Before collection, the owner must decide which source, prompts, model outputs,
counterexamples, and diagnostics may be retained and redistributed. Content
hashes can still identify known sensitive text and are not automatically
anonymous. Access policy, encryption, jurisdiction, licensing, retention
period, subject/request handling, and deletion obligations require review
outside this technical memo.

If law or policy requires deletion, the append-only logical record should retain
the smallest non-sensitive tombstone permitted, naming the affected identity
and reason without preserving prohibited content. That exception must be part
of the dataset policy before data collection; this repository implements none
of it.

## Failure handling

Collection fails closed on schema, identity, lineage, split, completeness,
replay, or referee errors. Partial output is quarantined and cannot enter a
training view. Operational retry, if later allowed, creates a new attempt
identity linked to the prior attempt; it never overwrites or hides it. A changed
referee version starts a new run manifest and cannot silently extend an old
dataset snapshot.

Suspected leakage or verifier unsoundness freezes affected dataset releases.
The response records scope, affected identities, investigation evidence, and
superseding manifests. Existing claimed results must be retracted or bounded;
they are not grandfathered through a new verifier.

## Unresolved decisions

No implementation should begin before resolving at least these questions:

- Is `0/1` sufficient for replayed violations, or is a signed reward needed?
- How should multiple obligations be scoped without rewarding partial proof?
- Which verifier/version diversity is required for adversarial validation?
- How are infrastructure flakiness and reproducibility windows measured without
  letting timing affect reward?
- Which semantic ancestry and near-duplicate detector is adequate for splits?
- What external-model provenance is both reproducible and legally retainable?
- How are sequential repair trajectories represented separately from
  independent Best-of-N candidates?
- What minimum corpus size and held-out evidence would justify any training
  effectiveness claim?
- Which privacy, licensing, access, deletion, and incident-response policies
  apply to real source and model output?
- Is a human override ever allowed, and if so how is it recorded without making
  the human or AI result masquerade as referee verification?

Until those decisions are reviewed and a new implementation stage is approved,
this memo remains a non-executable research design. There is no RLVF dataset,
training run, model comparison, or measured reward-learning result here.
