# CodeSkeptic Semantic Verification Prototype

This repository is an isolated prototype for a small
`C++ -> Semantic IR -> verification conditions -> result` pipeline. It was
created after inspecting CodeSkeptic, but it does not modify or vendor the
CodeSkeptic repository.

The prototype deliberately supports only 32-bit `int`, `bool`, local state,
assignment, side-effect-free expressions, `if`/`else`, standalone contracted
calls, `assert`, and `return`. Unsupported C++ is reported explicitly. It uses
a real Clang AST, but has no Python package or solver dependency.

Run the vertical slice:

```powershell
python -m semantic_verifier examples/vertical_slice.cpp --format json
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

The current suite contains 64 deterministic tests. The separately cloned,
unmodified CodeSkeptic reference also passes all 811 tests on this machine.

See [the design document](docs/semantic_verification_prototype.md) for the
implemented boundary, result taxonomy, examples, and limitations.

## Development workflow

Work is planned and tracked in [PLAN.md](PLAN.md) (roadmap; never carries
status), [TODO.md](TODO.md) (active set) and [PROGRESS.md](PROGRESS.md)
(append-only ledger; the single source of truth for "done"). The session
protocol lives in [CLAUDE.md](CLAUDE.md).

After cloning, enable the guardrail hooks once:

```
git config core.hooksPath .githooks
```

The pre-commit hook runs the full test suite, enforces the test-count ratchet
(`guardrails/test_baseline.txt`), and requires PROGRESS.md to be staged
whenever code changes are committed. Commit messages must start with a plan
stage ID (e.g. `A1.2: ...`) or an allowed prefix.
