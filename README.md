# US Semantic Verifier

[![Determinism](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml/badge.svg)](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml)
![Tests](https://img.shields.io/badge/tests-697%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)

US checks whether C++ code follows the rules we wrote down.

An AI can write code and propose rules. A human approves the intent. An
independent checker decides what is proved. Anything it cannot justify stays
unverified.

```text
C++ + checked rules -> independent checker -> clear result
```

This repository is US, the working Python reference. CodeSkeptic is the
separate production implementation and is written in C++.

## Why this matters

AI can produce code faster than people can review every line. Tests cover
selected examples. Ordinary comments can become outdated.

US turns small comments into rules that can be checked. The goal is to
review intent and evidence instead of blindly trusting the author, the AI, or
the tool.

## A small example

```cpp
// cs: requires amount >= 0
// cs: requires balance >= amount
// cs: ensures result >= 0
int withdraw(int balance, int amount) {
    return balance - amount;
}
```

`requires` says what must be true before the call. `ensures` says what must be
true after it. `modifies` can state what the function may change.

These are normal C++ comments. They use a small grammar, not a replacement for
C++.

## How to use it

1. Describe the behavior in plain language.
2. Let the AI propose rules with the `cs: ai` marker.
3. Review, edit, and approve those rules.
4. Let the AI implement them without changing them.
5. Run US and act on the result.

The AI proposes. The human owns the intended behavior. The checker remains the
referee.

Approved rules also survive agent, model, and chat changes. A new agent can
read the rules and the last report instead of guessing intent from old messages.

## Prompt for a coding agent

```text
This C++ project uses US contracts.

Before implementation:
- Restate the requested behavior in plain English.
- Propose the smallest useful rules with:
  // cs: ai requires ...
  // cs: ai ensures ...
  // cs: ai modifies ...   only when state may change
- Stop and ask for approval.

After approval:
- Remove the "ai" marker from the approved rules.
- Keep the approved rules unchanged while writing the code.
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

- [Contract-first workflow](docs/contract_first_workflow.md)
- [Supported boundary](docs/semantic_verification_prototype.md)
- [Adoption guide](docs/adoption_guide.md)
- [Roadmap](PLAN.md) and [completed work](PROGRESS.md)

## License

Licensed under the [Apache License 2.0](LICENSE).
