# E2 paired repair experiment

Status: E2.1 seeded-bug corpus is implemented. Paired arm execution and the
honest aggregate report follow in E2.2 and E2.3.

## Evidence scope

The quoted "consciousness experiment" name is historical shorthand. This is a
bounded repair-context experiment. A recorded or scripted proposer result can
measure only that exact evidence class; it cannot establish consciousness,
general model behavior, or causality.

The predeclared primary hypothesis is that the semantic-bundle arm has a median
censored repair score at least 40 percent lower than the compiler/test-only arm.
E2.2 uses a four-proposal cap. E2.3 retains an exhausted trial with score five
instead of dropping it.

## Seeded-bug corpus

benchmarks/experiment_e2/corpus freezes exactly twenty standalone supported-
subset C++ functions. Each source has one concrete replayable violated
postcondition under the admitted affine referee. Its separate oracle changes one
non-contract line and makes the complete target result set verified without
changing either human-authored contract.

manifest.json is a codeskeptic.experiment-corpus/v1 content-addressed index. It
cites the source, compiler context, and hidden oracle for every unique case. The
loader rejects missing or undeclared files, unsafe or stale paths, stale hashes,
duplicate identities, unsupported schemas, malformed UTF-8, contract leaks,
and non-canonical linked JSON.

A codeskeptic.experiment-compiler-context/v1 artifact contains only:

- the exact target source identity;
- source with every contract line blanked while preserving line numbers; and
- one frozen black-box test-failure diagnostic.

It contains no contract text, obligation, Semantic IR, counterexample, repair
bundle, or repair oracle. The codeskeptic.experiment-repair-oracle/v1 files live
in a separate directory and are referee inputs, never arm-A context.

The corpus checker parses every original, requires one isolated violated
postcondition with a concrete replay, applies the one-line oracle in memory, and
requires every repaired result to be verified:

    python tools/check_experiment_corpus.py benchmarks/experiment_e2/corpus

A successful check prints deterministic codeskeptic.experiment-corpus-check/v1
JSON and exits 0. Structural, frontend, replay, or verification failure exits 2.
No corpus operation uses a wall clock, randomness, network call, model package,
or source mutation.
