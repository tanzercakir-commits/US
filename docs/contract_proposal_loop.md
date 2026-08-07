# Offline contract-proposal loop

C1.1 defines a deterministic handoff from an owned C++17 function body to an
external model adapter. This repository renders the prompt but never opens a
network connection or invokes a model. The generated response is untrusted
review material: it cannot represent accepted intent, and every contract keeps
the `cs: ai` marker.

## Trust boundary

The AI proposes. It does not prove a contract, decide whether the contract is
correct, or modify source. The response schema permits only `candidate` and
`declined`. Candidate comments must begin with `// cs: ai`; no marker-free form
exists in the schema. C1.2 will independently pre-screen responses with the
ordinary deterministic referee. C1.3 will require a human-edited source before
intent can be accepted.

The prompt includes no wall clock, random value, executable path, or model
identity. It contains only caller-owned request data, bundled instructions, a
logical SHA-256 request identity, and the complete response schema.

## Request format

The versioned request schema is
`codeskeptic.contract-proposal-request/v1`, bundled at
`semantic_verifier/prompt_packs/contract_proposal/v1/request.schema.json`.
Its four required fields are:

- `target`: exact C++17 function name, signature, and body;
- `context`: typed owned symbols plus existing and direct-callee contracts;
- `source`: navigation-only file and declaration line;
- `schema`: the exact v1 identity.

All objects reject undeclared fields. Context arrays reject duplicates and are
canonicalized before rendering. `source.file` and `source.line` do not enter the
logical request hash, so checkout relocation and line shifts retain identity.
Signature, body, symbol/type context, and visible contracts do enter the hash.

The frozen example is
`fixtures/contract_proposals/request.json`. The target body is supplied exactly;
the renderer never extracts or guesses missing code. A loop anchor's
`body_line` is one-based within the supplied `target.body` text.

## Render and check

```powershell
python tools/contract_proposal.py `
  --request fixtures/contract_proposals/request.json `
  --output prompt.json

python tools/contract_proposal.py `
  --request fixtures/contract_proposals/request.json `
  --check fixtures/contract_proposals/expected.prompt.json
```

With neither `--output` nor `--check`, the canonical prompt JSON is written to
standard output. Exit codes are `0` for success/match, `1` for a golden mismatch,
and `2` for malformed input or I/O/resource failure.

## External adapter contract

An adapter may forward `messages` to a model and enforce the embedded
`response_schema` as structured output. It must not add repository facts,
change `request_id`, remove `cs: ai`, or treat the response as a referee result.
The adapter stores the raw response separately and passes it to the C1.2
pre-screening boundary; it does not patch source during C1.1.

The response schema requires:

- exact schema and request identities;
- `candidate` with one or more proposals, or `declined` with none;
- a function anchor for requires/ensures/modifies and a loop anchor for an
  invariant;
- a machine-proposed comment, rationale, and concrete evidence for every
  proposal;
- no undeclared fields and no accepted-intent state.

The prompt pack is vendor-neutral JSON. No OpenAI-, Anthropic-, IDE-, or hosted
service field is part of the stable contract.