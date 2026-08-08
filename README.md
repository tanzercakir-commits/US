# CodeSkeptic Semantic Verifier

[![Determinism](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml/badge.svg?branch=feature%2Fsemantic-verification-prototype)](https://github.com/tanzercakir-commits/US/actions/workflows/determinism.yml)
![Tests](https://img.shields.io/badge/tests-652%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)

A small reference project for checking contract-style rules in supported C++
code. It reads real C++ with Clang, builds a simpler semantic model, and asks a
deterministic referee whether each rule is proved, broken, or outside the
current boundary.

The guiding principle is simple: tools may propose, but only the referee decides.
Anything it cannot justify stays unverified.

## Why this exists

Code review and tests are valuable, but they do not always explain whether a
specific rule holds for every allowed input. This project explores a practical,
auditable verification path:

```text
C++ source -> Semantic IR -> proof obligations -> deterministic result
```

It is a completed Python reference implementation and research lab. It does not
modify or include the separate production CodeSkeptic repository.

## Quick start

You need Python 3.11 or newer and Clang on `PATH`.

```powershell
git clone https://github.com/tanzercakir-commits/US.git
cd US
python -m semantic_verifier examples/vertical_slice.cpp --backend affine --format text
```

The example deliberately contains both valid and broken rules, so exit code `1`
is expected. The affine backend needs no Python packages or Z3. For the default
cross-check mode, install the Z3 executable and run:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp --backend both --format text
```

Contracts live beside the C++ they describe:

```cpp
// cs: requires x < 2147483647
// cs: ensures result > x
int increment(int x) {
    return x + 1;
}
```

## Result meanings

| Result | Meaning |
| --- | --- |
| `verified` | The exact generated obligation was proved. |
| `violated` | A counterexample was found and replayed. |
| `unknown` | The code is supported, but the referee could not decide. |
| `unsupported` | The code is outside the implemented subset. |
| `solver_error` | The checking tool failed; this is never treated as success. |

`unknown`, `unsupported`, and `solver_error` never become `verified` by
assumption.

## What is covered

The supported subset is intentionally limited. It includes common integer and
boolean logic, branches, contracted function calls, annotated loops, and
selected arrays, value structs, references, and frame conditions. Unsupported
C++ is reported explicitly instead of being silently approximated.

This is not a full C++ verifier, a production certification tool, or a
replacement for compilation, tests, sanitizers, review, and static analysis.

## Confidence checks

The repository currently carries:

- 652 deterministic tests;
- reproducible, byte-checked fixtures;
- a forty-function benchmark corpus;
- replay evidence for every reported counterexample; and
- a complete three-point benchmark trend with a green logical gate.

Run the main checks with:

```powershell
python -m unittest discover -s tests
python tools/regenerate_fixtures.py --check
python tools/check_benchmark_corpus.py benchmarks/corpus
python tools/check_benchmark_trend.py benchmarks/results/runs.jsonl benchmarks/results/trend.json --check
```

GitHub Actions runs the full suite and regenerates fixtures twice to catch
non-deterministic output.

## Repository guide

| Path | Contents |
| --- | --- |
| [`semantic_verifier/`](semantic_verifier/) | The reference verifier. |
| [`examples/`](examples/) | Small C++ examples. |
| [`tests/`](tests/) | Soundness, boundary, and determinism tests. |
| [`fixtures/`](fixtures/) | Frozen reproducible evidence. |
| [`benchmarks/`](benchmarks/) | Experiment and trend data. |
| [`docs/`](docs/) | Detailed design and operating notes. |

Useful starting points:

- [Design and supported boundary](docs/semantic_verification_prototype.md)
- [Adoption guide](docs/adoption_guide.md)
- [Result and schema reference](docs/result_schema.md)
- [Benchmark suite](docs/benchmark_suite.md)
- [Roadmap](PLAN.md), [completed-work ledger](PROGRESS.md), and
  [changelog](CHANGELOG.md)

## Development guardrails

Enable the repository hooks once after cloning:

```powershell
git config core.hooksPath .githooks
```

The pre-commit hook runs the full test suite, protects the test-count ratchet,
and requires progress records for implementation changes. See
[`CLAUDE.md`](CLAUDE.md) for the full contribution protocol.
