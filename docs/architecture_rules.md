# Architectural Dependency Policies

## Scope

D3.1 defines codeskeptic.architecture-policy/v1. It is a deterministic policy
contract only: it does not extract facts, decide compliance, emit findings, or
invoke a model/referee. D3.2 consumes this policy with one validated fact index.

## Layers and selectors

Each layer has a lowercase kebab-case name and at least one literal selector.
Supported selector kinds are:

| Kind | Match |
| --- | --- |
| qualified_name | The complete indexed qualified name is equal. |
| qualified_name_prefix | The indexed qualified name starts with the value. |
| source_prefix | The normalized declaration source path starts with the value. |

Source prefixes use forward slashes, are relative, and reject empty, absolute,
drive-qualified, doubled, dot, or parent segments. Backslashes and one leading
./ are normalized before identity is computed. Qualified-name values remain
literal; no selector kind interprets glob or regular-expression syntax.

A symbol may match zero, one, or several layers. The classify API returns all
matching layer names in sorted policy order. Policy or selector order never
chooses a winner. D3.2 treats zero/multiple endpoint matches as unknown.

Duplicate layer names, duplicate selectors within a layer, and the same
selector repeated across layers are invalid. Different selectors may still
overlap for a real symbol; that is an intentional runtime classification
outcome rather than hidden precedence.

## Complete dependency matrix

The dependencies array contains one decision for every ordered layer pair,
including each self-pair. A decision is exactly allow or forbid. There is no
default.

For N layers a valid policy therefore has N squared dependency entries.
Missing, duplicate, or unknown-layer pairs fail loading. The lookup API accepts
two known layer names and returns their explicit decision.

The frozen fixture contains orchestration, storage, and utility layers. It
allows all self-dependencies, orchestration and storage calls into utility, and
forbids the remaining cross-layer directions including orchestration into
storage.

## Canonical identity and strict loading

Layers are sorted by name, selectors by kind/value, and decisions by from/to.
The policy ID is a lowercase SHA-256 content identity over this canonical
schema payload:

    {
      "schema": "codeskeptic.architecture-policy/v1",
      "layers": [...],
      "dependencies": [...]
    }

The ID is part of the serialized artifact but not its hashed content. Shuffled
input arrays therefore canonicalize to identical bytes and identity. A stale ID
fails loading.

Strict loading rejects malformed UTF-8/JSON, duplicate object keys, non-finite
numbers, missing/unknown fields at every level, unsupported schema/kinds or
decisions, invalid names/paths, and incomplete matrices.

Validate and canonicalize a policy with:

    python tools/validate_architecture_policy.py fixtures/architecture/policy.json

Success writes canonical ASCII JSON to stdout and exits 0. Input/schema/policy
errors write one diagnostic to stderr and exit 2.

## Trust boundary

An allow decision means only that a classified dependency is permitted by the
declared policy. It is not semantic verification or proof. Unsupported or
missing fact edges cannot be reconstructed from policy text. D3.2 must retain
fact-index limitations and incomplete classification as unknown.
## Fact-based enforcement

D3.2 consumes one strictly validated fact-index/v1 artifact and one strict
architecture-policy/v1 artifact. It checks every resolved direct call fact
exactly once:

1. Classify the indexed caller and callee independently.
2. If either endpoint matches zero or multiple layers, record an explicit
   unknown finding and do not invent a decision for that call.
3. If both endpoints match exactly one layer, look up the required matrix entry
   and record its allow or forbid decision with the call ID, caller/callee
   symbols, layers, and exact source site.
4. Convert every fact-index limitation into an unknown finding because the
   indexed architecture graph may be incomplete.

The canonical codeskeptic.architecture-result/v1 object contains all decided
calls, sorted unknown findings, the index/policy content IDs, and summary counts
for calls, decided, allowed, forbidden, undecided calls, and unknown findings.

Aggregate status is deliberately fail-closed:

| Condition | Status | Exit |
| --- | --- | --- |
| Any unknown finding | unknown | 2 |
| Otherwise any forbid decision | violation | 1 |
| Otherwise | clean | 0 |
| Input/schema/I/O failure | no report | 3 |

Unknown therefore takes precedence even when a known forbidden edge is also
present. Clean means only that every indexed direct call is classified and
allowed by this policy; it is not semantic proof.

Run the checker with:

    python tools/check_architecture.py FACT_INDEX POLICY
    python tools/check_architecture.py FACT_INDEX POLICY --format text
    python tools/check_architecture.py FACT_INDEX POLICY --format sarif

JSON is the default. Successful report bytes go only to stdout; input errors go
to stderr.

## SARIF 2.1.0

The SARIF adapter uses two stable rules:

| Rule | Level | Meaning |
| --- | --- | --- |
| CSARCH001 | error | A classified direct call crosses a forbidden pair. |
| CSARCH002 | warning | A limitation or incomplete classification blocks a clean decision. |

Forbidden results use the exact call site and call fact ID. Unknown results use
the limitation site or call site when available plus a content fingerprint of
their evidence. Artifact URIs are normalized stable display paths relative to
%SRCROOT%; regions are one-based. The run records index/policy IDs and aggregate
status but no absolute path, timestamp, duration, random value, or model output.

The frozen world-corpus result has two allowed calls and one forbidden
orchestration-to-storage call. Its canonical result and SARIF artifacts are
fixtures/architecture/expected.result.json and
fixtures/architecture/expected.sarif.json.
