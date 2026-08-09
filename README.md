# US Semantic Verifier

[![Determinism](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml/badge.svg)](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml)
![Tests](https://img.shields.io/badge/tests-697%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)

US answers one question:

**Does this C++ code always follow its stated contract?**

A contract defines which inputs are allowed, what the function promises, and
what state it may change. US reads the code and the contract. An independent
checker then decides what is proved.

```text
C++ code + contract -> US -> verified / violated / unknown / unsupported
```

When the result is `verified`, the contract holds for all inputs allowed by its
preconditions, within the C++ features and semantics that US supports. Anything
US cannot justify stays unverified.

An AI proposes the contract and writes the code. A human approves the intended
behavior. The checker judges the result.

This repository contains the Python reference implementation of US.

## Why this matters

AI can produce code faster than people can review every line. Tests show that
code works for selected examples. US reasons about the allowed input range and
reports unsupported code instead of silently skipping it.

It does not replace tests, static analysis, or human review. It adds independent
evidence about the behavior that matters most.

## Choose a contract form

US currently ships two contract adapters. The first accepts a
[supported subset of C++26 contracts](docs/cpp26_contracts_bridge.md):

```cpp
int withdraw(const int balance, const int amount)
    pre(amount >= 0)
    pre(balance >= amount)
    post(result: result >= 0)
{
    return balance - amount;
}
```

The second accepts lightweight [`cs:` contract comments](docs/cs_contracts.md)
for projects and toolchains that do not use C++26 contracts yet:

```cpp
// cs: requires amount >= 0
// cs: requires balance >= amount
// cs: ensures result >= 0
int withdraw(const int balance, const int amount) {
    return balance - amount;
}
```

Both adapters produce the same internal contract and use the same checker. A
project may choose either form. The forms must not be mixed on the same
function.

## How to use it

1. Choose the supported contract form that fits the project.
2. Before implementation, ask the AI to save the proposed contract as a
   separate review artifact.
3. Review, edit, and approve the intended behavior.
4. Freeze the approved artifact and encode the same contract in the source with
   the selected contract form.
5. Let the AI implement the code without changing either contract.
6. Run US and act on the result.

The separate artifact records the approved intent. Today, US verifies the
matching C++26 or `cs:` contract encoded in the source; it does not yet read the
review artifact as direct sidecar input.

The AI proposes. The human owns the intended behavior. The checker remains the
referee.

Approved rules also survive agent, model, and chat changes. A new agent can
read the rules and the last report instead of guessing intent from old messages.

## Prompt for a coding agent

```text
This project uses US semantic verification.

Use the contract form selected by the project. US currently accepts a bounded
C++26 contract subset and cs comments through adapters. Do not mix both forms
on the same function.

Before implementation:
- Restate the requested behavior in plain English.
- Save the smallest useful contract as a separate review artifact.
- Do not modify the source yet.
- Stop and ask for approval.

After approval:
- Freeze the approved contract artifact.
- Encode the same contract in the source with the selected contract form.
- Implement the code without changing the artifact or the source contract.
- Run US and report every result.

Only "verified" counts as proof. Never hide or upgrade "violated",
"unknown", "unsupported", or "solver_error". A successful build or test
run is not proof of a contract.
```

## Try it

You need Python 3.11 or newer and Clang on `PATH`.

```powershell
git clone https://github.com/tanzercakir-commits/US.git
cd US
python -m semantic_verifier fixtures/contract_first/implemented.cpp `
  --backend affine --format text
```

The example returns three `verified` checks and exit code `0`.

For JSON output:

```powershell
python -m semantic_verifier path/to/file.cpp --format json
```

## Result meanings

| Result | Meaning |
| --- | --- |
| `verified` | The exact rule was proved. |
| `violated` | A failing input was found and replayed. |
| `unknown` | The checker could not decide. |
| `unsupported` | The code is outside the current supported subset. |
| `solver_error` | The checking tool failed. |

Only `verified` is success.

## Starting with an existing project

Start with one path where a bug would be expensive. Add a few important rules
and expand only after the results are stable.

For a project with `compile_commands.json`:

```powershell
python tools/project_manifest.py path/to/project
python tools/project_index.py path/to/project
```

These commands account for project files and map direct function calls. Today,
supported source files are verified one at a time. Whole-project proof is not
claimed yet.

## Why this style helps

- Intent is written before implementation.
- Rules survive agent and model changes.
- Review can focus on behavior instead of every generated line.
- Different agents can be judged against the same rules.
- The AI does not grade its own work.
- Failing examples are recorded and replayed.
- Unsupported code is reported instead of silently skipped.
- Adoption can begin with one function.

## Current status

The reference supports a deliberate subset of C++ and has 697 deterministic
tests with byte-checked evidence. Project inventory and direct-call mapping are
available.

Memory and pointer support is being added in stages. The data model exists;
source pointer safety is not claimed as proved today. US is not yet a
full C++ verifier or a certification product. It complements compilation,
tests, sanitizers, static analysis, and human review.

## Learn more

- [`cs:` contract reference](docs/cs_contracts.md)
- [Contract-first workflow](docs/contract_first_workflow.md)
- [Supported boundary](docs/semantic_verification_prototype.md)
- [Adoption guide](docs/adoption_guide.md)
- [Roadmap](PLAN.md) and [completed work](PROGRESS.md)

## License

Licensed under the [Apache License 2.0](LICENSE).
