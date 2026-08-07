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
exists in the schema. C1.2 independently pre-screens responses with the
ordinary deterministic referee. C1.3 requires a human-edited source before
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


## Deterministic pre-screen

C1.2 parses the raw response with an exact-field validator, checks its logical
request identity, and builds a separate in-memory `cs: ai` overlay. The input
request and source text are never modified. The ordinary Clang frontend,
contract parser, VC generator, and selected checker then run three gates:

1. every function candidate must survive exact contract parsing and fragment
   well-formedness;
2. existing and proposed requires/ensures/invariants must admit at least one
   jointly typed state;
3. proposed invariants must have verified loop-entry and loop-preservation
   obligations.

An incomplete overlay result (`unknown`, `unsupported`, or `solver_error`) is a
distinct rejection. Infeasible requirements or false invariant checks are a
`violated` rejection. A well-formed, satisfiable postcondition may still expose
a violation in the supplied function body: that is useful intent review
material, not acceptance. Its counts remain visible in `verification_summary`.
No pre-screen outcome is a proof that the specification is the human's intent.

The versioned report schema is
`codeskeptic.contract-proposal-pre-screen/v1`, bundled beside the request and
response schemas. It records canonical request/response/overlay hashes, every
gating check, candidate comments, the body-preview summary, and one of these
states:

| Status | Outcome | Meaning |
| --- | --- | --- |
| `eligible` | `eligible` | All deterministic proposal gates passed. |
| `declined` | `declined` | The generator emitted no proposal. |
| `malformed` | `rejected` | Shape, marker, anchor, or identity was invalid. |
| `violated` | `rejected` | Requirements were infeasible or an invariant failed. |
| `unknown` | `rejected` | The referee could not decide a gating obligation. |
| `unsupported` | `rejected` | The candidate or overlay exceeded owned semantics. |
| `solver_error` | `rejected` | Frontend/checker execution failed. |

Run the frozen affine pre-screen fixture:

```powershell
python tools/contract_proposal.py `
  --request fixtures/contract_proposals/screen.request.json `
  --response fixtures/contract_proposals/eligible.response.json `
  --backend affine `
  --check fixtures/contract_proposals/expected.pre-screen.json
```

Use `--backend both` in an operational adapter when the separately installed Z3
referee is available. Backend disagreement, launch failure, timeout, and
unsupported logic remain fail-closed. The CLI writes only the pre-screen JSON;
it does not export or apply the internal overlay.

## External adapter contract

An adapter may forward `messages` to a model and enforce the embedded
`response_schema` as structured output. It must not add repository facts,
change `request_id`, remove `cs: ai`, or treat the response as a referee result.
The adapter stores the raw response separately and passes it to the C1.2
pre-screening boundary; neither stage patches source.

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