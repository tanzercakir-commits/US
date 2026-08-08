# Contract-first task

## 1. Prose request

State the externally observable behavior, owned types, boundary cases, and
explicit non-goals. Do not write implementation details here.

## 2. Proposed contract set

Record only machine-marked review material:

```cpp
// cs: ai requires <condition>
// cs: ai ensures <condition>
<declaration>;
```

Store it as a separate UTF-8 artifact and pin its SHA-256 in the task manifest.

## 3. Human approval

A human edits the proposed contract lines and removes `ai`. Keep the declaration
unchanged, store the marker-free approval separately, and pin its SHA-256.
Approval is intent, not proof; reviewer identity is attested outside the tool.

## 4. Implementation

Copy the accepted contract set unchanged above the implementation. Implement
only after the accepted artifact exists. Pin the complete source SHA-256.

## 5. Verification

Run the ordinary deterministic referee. Record all five status counts, the
report hash, and every transition hash. `unknown`, `unsupported`, violation, or
solver error fails the workflow; no AI output can override the referee.

```powershell
python tools/contract_first_workflow.py `
  --manifest fixtures/contract_first/task.json `
  --check fixtures/contract_first/expected.run.json
```