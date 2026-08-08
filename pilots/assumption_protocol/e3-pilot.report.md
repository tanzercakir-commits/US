# E3 Repository Assumption Pilot

The declaration sub-gate froze manifest
`sha256:13ecfcb8a49d419ad196106836d3d26818399d6eb8d77d0d69d89cd996c55ebb`
before the pilot tool, evidence tests, and resolution overlay existed. The
closure links that unchanged identity and all five unchanged snapshot files.

The linked resolution has five test dispositions and one uncheckable
disposition. The repository test command passes all five checkable claims. The
external-model generalization claim remains uncheckable because this pilot has
no independently sampled external AI model or controlled external-model run.

This result establishes only that the frozen repository evidence satisfies the
declared local tests. It does not establish consciousness, general AI-model
behavior, external-model repair performance, or causality. Evidence hashes and
anchors establish citation integrity; they do not replace execution by the
repository test runner.

Reproduce the closure check:

    python tools/run_assumption_pilot.py pilots/assumption_protocol/e3-pilot.manifest.json pilots/assumption_protocol/e3-pilot.resolution.json --root . --validation-root pilots/assumption_protocol/archive --check pilots/assumption_protocol/e3-pilot.summary.json
