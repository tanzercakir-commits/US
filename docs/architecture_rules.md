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
