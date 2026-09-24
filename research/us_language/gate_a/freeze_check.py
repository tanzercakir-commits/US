#!/usr/bin/env python3
"""Validate the frozen Gate A representation experiment before model trials."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
FACT_RE = re.compile(r"F\d{2}")


def ids_in(path: Path) -> Counter[str]:
    return Counter(FACT_RE.findall(path.read_text(encoding="utf-8")))


def main() -> int:
    manifest = json.loads((ROOT / "FACT_MANIFEST.json").read_text(encoding="utf-8"))
    required = manifest["parity_rule"]["required_fact_ids"]
    required_counts = Counter({fact_id: 1 for fact_id in required})

    failures: list[str] = []
    observations: dict[str, object] = {}

    for name in ("REPORTBUILDER.us.txt", "REPORTBUILDER.md"):
        counts = ids_in(ROOT / name)
        observations[name] = dict(sorted(counts.items()))
        if counts != required_counts:
            failures.append(
                f"{name}: fact IDs must equal F01-F14 exactly once; got {dict(counts)}"
            )

    frozen_docs = {
        "EXPERIMENT_CONTRACT.md": "FROZEN BEFORE MODEL OUTPUTS",
        "SCORING.md": "FROZEN BEFORE MODEL OUTPUTS",
    }
    for name, marker in frozen_docs.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        if marker not in text:
            failures.append(f"{name}: missing freeze marker {marker!r}")

    required_files = [
        "REPRESENTATION_V0.md",
        "FACT_MANIFEST.json",
        "REPORTBUILDER.us.txt",
        "REPORTBUILDER.md",
        "REQUEST_0_INITIAL.md",
        "REQUEST_1_CSV.md",
        "REQUEST_2_CACHE.md",
        "EXPERIMENT_CONTRACT.md",
        "SCORING.md",
        "evaluator.py",
    ]
    missing = [name for name in required_files if not (ROOT / name).is_file()]
    if missing:
        failures.append(f"missing Gate A files: {missing}")

    cache_request = (ROOT / "REQUEST_2_CACHE.md").read_text(encoding="utf-8")
    if "does not specify what `eviction_policy=None` means" not in cache_request:
        failures.append(
            "REQUEST_2_CACHE.md must keep eviction_policy=None unresolved"
        )

    result = {
        "schema": "us-language-gate-a-freeze-check-v0",
        "ok": not failures,
        "failures": failures,
        "observations": observations,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
