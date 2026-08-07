# E2 paired repair experiment

Status: E2.1 seeded-bug corpus and E2.2 paired arm execution are implemented.
The honest aggregate report follows in E2.3.

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
## Paired trial protocol

E2.2 freezes forty trials: one compiler_test row and one semantic_bundle row for
each corpus case. Both arms use the same original source, target function,
replay-attested initial bundle, affine referee, RepairHarness, PatchProposer
seam, and maximum of four proposals.

Arm-A context contains only the contract-redacted source identity and black-box
test diagnostic described above. Arm-B context contains exactly the E1.1 repair
bundle. Strict content identities link every context, recorded proposal script,
proposal, initial bundle, repair-loop log, and trial row. Any context leak,
cross-arm link, stale proposal chain, mixed proposer provenance, missing pair,
or changed result fails closed.

The proposal evidence class is codeskeptic.recorded-scripted-proxy/v1. These are
frozen untrusted proposal transcripts used to exercise the paired protocol; no
model is called by the reference runner. Every candidate is applied in memory
and only the verifier can mark a loop successful. Exhaustion consumes all four
proposals and receives censored score five.

The frozen raw outcomes are:

- compiler_test: 16 verified and 4 exhausted; scores
  5,5,5,5,4,4,4,4,4,4,3,3,3,3,3,2,2,2,1,1;
- semantic_bundle: 20 verified and 0 exhausted; every score is 1.

These are raw protocol results, not yet the predeclared E2.3 statistical report.
They do not establish behavior for an independently sampled AI model.

Run or reproduce-check all forty trials:

    python tools/run_experiment_e2.py benchmarks/experiment_e2/corpus benchmarks/experiment_e2/contexts benchmarks/experiment_e2/proposals benchmarks/experiment_e2/results/trials.json
    python tools/run_experiment_e2.py benchmarks/experiment_e2/corpus benchmarks/experiment_e2/contexts benchmarks/experiment_e2/proposals benchmarks/experiment_e2/results/trials.json --check

Generation and an exact check exit 0, a check mismatch exits 1, and strict
corpus/context/script/referee/result failures exit 2. The canonical
codeskeptic.experiment-trials/v1 artifact embeds every repair-loop log and uses
no timing, random value, network call, or hidden retry.
