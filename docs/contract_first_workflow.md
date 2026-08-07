# Contract-first workflow

C2.1 makes intent an input artifact rather than a comment written after the
implementation. The sequence is fixed:

1. prose request;
2. `cs: ai` proposed contract declaration;
3. separately stored marker-free human approval;
4. implementation carrying the accepted contracts unchanged;
5. ordinary deterministic verification.

The workflow checker creates no model request, contract, approval, or code. It
reads already separated artifacts, verifies their transitions and hashes, and
then asks the existing referee to decide. Human identity remains an external
attestation and is recorded as required in every successful report.

## Task template

Use [the task template](../templates/contract_first_task.md) before writing
code. The machine manifest is a strict
`codeskeptic.contract-first-task/v1` JSON object with:

- a stable task ID and non-empty prose request;
- relative proposed, accepted, and implemented UTF-8 artifact paths;
- exact SHA-256 for every artifact;
- the target function name;
- an exact five-status expected summary.

Paths are resolved under the manifest directory. Absolute paths, `..`, missing
files, non-UTF-8 content, unknown fields, and hash drift fail closed. Run output
contains no checkout root, timestamp, duration, random value, or executable
path, so relocating the complete task directory does not change its bytes.

## Transition rules

### Request to proposal

The proposed artifact is a declaration preceded by one or more contracts. Every
contract must retain `cs: ai`. The ordinary parser and referee must accept the
contract fragment and find the requirements satisfiable.

### Proposal to approval

The accepted artifact is separate, marker-free, and keeps the declaration and
contract-kind sequence. A human may edit the expressions while reviewing them.
The checker verifies the resulting declaration again; it does not infer who
performed the edit.

### Approval to implementation

The implementation must copy the accepted contract lines exactly and replace
the declaration with a matching definition. Any implementation-side contract
change fails before verification.

### Implementation to verification

The normal frontend, VC generator, and selected checker run on the implementation.
At least one obligation must exist. Every obligation must be `verified`, and the
complete five-status summary must equal the manifest. A violation, `unknown`,
`unsupported`, solver error, or summary drift prevents `complete`.

## Frozen end-to-end task

The committed task asks for a signed `increment_checked` function that returns
`value + 1` only below `INT_MAX`. Its accepted intent is:

```cpp
// cs: requires value < 2147483647
// cs: ensures result == value + 1
int increment_checked(int value);
```

The later implementation produces three verified obligations: contract
consistency, signed-addition safety, and the postcondition. Every other status
is zero.

```powershell
python tools/contract_first_workflow.py `
  --manifest fixtures/contract_first/task.json `
  --check fixtures/contract_first/expected.run.json
```

Use `--backend both` when the separately installed Z3 referee is required. The
dependency-free affine fixture is deliberately within the exact affine fragment.
`--output <file>` writes a canonical report; without output/check it is printed.
Exit `0` means success or golden match, `1` means golden mismatch, and `2` means
a malformed artifact, failed transition, or non-verified referee result.

## Evidence and limitations

The `codeskeptic.contract-first-run/v1` report content-addresses the prose,
three artifacts, accepted contract set, four transitions, and final verifier
report. It establishes artifact order and consistency, not real-world reviewer
identity or the correctness of the prose itself. Those remain human inputs. The
AI never becomes the referee.
## C2.2 verifier pilot

The committed `guarded_absolute_value` pilot applies the workflow to an
already-supported A-style signed-i32 increment. During approval, the proposed
`value > INT_MIN` precondition was deliberately rewritten as the clearer
`value != INT_MIN` boundary before implementation. The correct implementation
produces six verified obligations and zero results in every other status.

```powershell
python tools/contract_first_workflow.py `
  --manifest pilots/contract_first/guarded_absolute/task.json `
  --check pilots/contract_first/guarded_absolute/expected.run.json
```

`mismatch.task.json` keeps the accepted contracts but points at a seeded
implementation that returns negative values unchanged. It deterministically
fails with a replayed postcondition violation and exit `2`. The accompanying
comparison records the added evidence and artifact cost without claiming that
earlier implementation-first stages used this workflow.
