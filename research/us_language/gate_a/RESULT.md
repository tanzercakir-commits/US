# US Language Gate A — Result

Status: **COMPLETE — NULL RESULT**

This report records the predeclared Gate A ReportBuilder experiment without
changing the frozen representation, task, maintenance requests, evaluator, or
scoring rules.

## Deterministic result

Five paired repetitions completed for both conditions. Each repetition included:

1. initial implementation — 40 points;
2. CSV maintenance — 25 points;
3. cache maintenance — 35 points.

| Repetition | US | Markdown |
|---|---:|---:|
| 1 | 100/100 | 100/100 |
| 2 | 100/100 | 100/100 |
| 3 | 100/100 | 100/100 |
| 4 | 100/100 | 100/100 |
| 5 | 100/100 | 100/100 |

- US median: 100
- Markdown median: 100
- Median difference: 0
- Paired repetitions with US >= Markdown: 5/5
- US critical events: 0
- Markdown critical events: 0

Under the frozen `SCORING.md` outcome rule, this is a **null result**.

The pilot does not provide evidence that the minimal US representation produces
better implementation/preservation outcomes than the information-equivalent
strong Markdown control.

It also does not establish that the representations are generally equivalent.
This bounded pilot saturated: both conditions achieved the maximum deterministic
score in every repetition.

## Terminal trial heads

| Repetition | US cache head | Markdown cache head |
|---|---|---|
| 1 | `367aa9b7ea5f71a21740b576fd0b8a0b469df8f2` | `f09fa2904b18a4f8fdabdc4ade5139b2e66cfc73` |
| 2 | `d8e03010b6fe6ac27a531dab66dd53a886afa9bd` | `78792799e405949e3bbe698b4a9184ec8f718269` |
| 3 | `488031e170e4146f49eed0d763d2ecadf5ad9eb5` | `6a152bfd21dbd23817d5b776d42b947b7ae49d7d` |
| 4 | `234bd45ba68688dc67199e371e1bf6e3ae4811e8` | `98e9f70070fa1dfbdb1d85cb1bbbe1df157c76a4` |
| 5 | `51b9597a4f5cb215853df99dcf839834c563271c` | `d01ac0dd789df98a0fc53e761ddc3a40adc0000b` |

## Interpretation boundary

This result falsifies the claim that this particular ReportBuilder pilot, with
its frozen checks and maintenance sequence, demonstrates a measurable US
representation advantage.

It does not justify parser/compiler work or production integration.

A future experiment must be a new version rather than a post-hoc modification
of this frozen pilot.

## Sensitivity observations

Human review was kept separate from deterministic scoring.

Some implementations exposed qualitative differences in source-row isolation
that the frozen deterministic evaluator did not always distinguish. This is
evidence that the pilot's measurement surface had blind spots even though the
predeclared scoring must remain unchanged.

The all-perfect score pattern is therefore best treated as a benchmark
sensitivity/ceiling finding, not as proof that representation never matters.

## Execution limitations

- Python 3.11 was unavailable in the trial execution environments; model agents
  generally executed sanity tests under Python 3.13.5, with Python 3.11 grammar
  compatibility checked in later runs.
- One Markdown Run 1 cache report claimed additional local cache tests while the
  committed test blob matched the earlier CSV-stage test blob. The committed
  implementation still satisfied the frozen cache criteria; the discrepancy is
  retained as provenance metadata rather than repaired.
- A formal repository run manifest pinning model identity/settings/tool
  permissions was not created before execution. The paired prompts used the
  intended isolation pattern, but this limits stronger reproducibility claims.

## Gate decision

Gate A is complete with a valid null outcome.

Do not promote US Language into production parser/IR/schema/verifier surfaces
from this evidence.

The research track may either stop here or define a new, harder,
information-equivalent experiment designed to avoid the ceiling effect. Any new
experiment must preserve this Gate A series unchanged.
