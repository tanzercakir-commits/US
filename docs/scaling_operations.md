# Scaling Operations and A5 Phase Gate

## Purpose

The A5 gate checks operational scaling without changing proof meaning. It uses
the committed scaling slice, exact structured merge target, persistent cache,
and deterministic file budget. It records hashes and work units, never timing
values.

## Required commands

Run the integrated gate with the production-default cross-check backend:

```powershell
python tools/scaling_phase_gate.py --backend both
```

Re-run the isolated path-growth probe:

```powershell
python tools/path_scaling_probe.py
```

Then run repository acceptance:

```powershell
python -m unittest discover -s tests
python tools/regenerate_fixtures.py --check
```

## Frozen acceptance rules

- uncached, cache-fill, and warm-cache report bytes are identical;
- the warm run invokes the wrapped backend zero times;
- repeated runs with `--max-checks 5` are byte-identical and start five checks;
- budget exhaustion remains explicit `unknown`;
- the 1/2/4/8-diamond probe reports 1/1/1/1 assertion obligations while its
  expected paths remain 2/4/16/256;
- the full test ratchet and all current fixtures remain green.

The gate output schema is `codeskeptic.scaling-phase-gate/v0`. Output is sorted
JSON with stable display paths, SHA-256 hashes, counts, and one trailing newline.
It deliberately excludes duration, temporary cache paths, process IDs, and
solver stdout/model text.

## Failure handling

Any mismatch or non-zero warm backend count fails the command. Treat changed
hashes as review prompts: inspect source, report, schema, backend configuration,
and budget policy before updating a recorded target. Never weaken a status or
soundness test to restore the gate. Cache deletion is safe because a cold run
recomputes every entry.
