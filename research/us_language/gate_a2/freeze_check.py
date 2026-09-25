#!/usr/bin/env python3
"""Validate Gate A2 design parity and, optionally, exact trial readiness."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
FACT_RE = re.compile(r"F\d{2}")
HEX40_RE = re.compile(r"[0-9a-f]{40}")

FROZEN_ARTIFACTS = (
    "REPRESENTATION_V0.md",
    "FACT_MANIFEST.json",
    "render_conditions.py",
    "WORKFLOWRELAY.us.txt",
    "WORKFLOWRELAY.md",
    "REQUEST_0_INITIAL.md",
    "REQUEST_1_BATCH.md",
    "REQUEST_2_MULTI_EXPORT.md",
    "REQUEST_3_RETRY.md",
    "EXPERIMENT_CONTRACT.md",
    "SCORING.md",
    "evaluator.py",
    "score_series.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_digests() -> dict[str, str]:
    return {name: sha256(ROOT / name) for name in FROZEN_ARTIFACTS}


def fact_counts(path: Path) -> Counter[str]:
    return Counter(FACT_RE.findall(path.read_text(encoding="utf-8")))


def design_failures() -> list[str]:
    failures: list[str] = []
    required_files = set(FROZEN_ARTIFACTS) | {
        "README.md",
        "RUN_MANIFEST.template.json",
    }
    missing = sorted(name for name in required_files if not (ROOT / name).is_file())
    if missing:
        failures.append(f"missing Gate A2 files: {missing}")
        return failures

    manifest = json.loads((ROOT / "FACT_MANIFEST.json").read_text(encoding="utf-8"))
    facts = manifest.get("facts", [])
    ids = [fact.get("id") for fact in facts]
    required = manifest.get("parity_rule", {}).get("required_fact_ids", [])

    if ids != required:
        failures.append("manifest fact order/IDs differ from parity required_fact_ids")
    if len(ids) != 39 or len(set(ids)) != 39:
        failures.append(f"expected 39 unique facts, got {len(ids)} / {len(set(ids))}")
    if ids != [f"F{i:02d}" for i in range(1, 40)]:
        failures.append("fact IDs must be contiguous F01-F39")

    classes = Counter(fact.get("class") for fact in facts)
    expected_classes = {
        "intent": 2,
        "architecture": 11,
        "rules": 12,
        "freedom": 5,
        "flow": 7,
        "unknowns": 2,
    }
    if dict(classes) != expected_classes:
        failures.append(f"unexpected class counts: {dict(classes)}")

    wanted = Counter({fact_id: 1 for fact_id in required})
    for name in ("WORKFLOWRELAY.us.txt", "WORKFLOWRELAY.md"):
        counts = fact_counts(ROOT / name)
        if counts != wanted:
            failures.append(f"{name}: fact IDs are not exactly F01-F39 once each")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "render_conditions.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        failures.append(
            "render_conditions.py --check failed: "
            + (proc.stderr.strip() or proc.stdout.strip())
        )

    contract = (ROOT / "EXPERIMENT_CONTRACT.md").read_text(encoding="utf-8")
    scoring = (ROOT / "SCORING.md").read_text(encoding="utf-8")
    if "FROZEN BEFORE MODEL OUTPUTS" not in contract:
        failures.append("EXPERIMENT_CONTRACT.md missing freeze marker")
    if "FROZEN BEFORE MODEL OUTPUTS" not in scoring:
        failures.append("SCORING.md missing freeze marker")

    multi = (ROOT / "REQUEST_2_MULTI_EXPORT.md").read_text(encoding="utf-8")
    retry = (ROOT / "REQUEST_3_RETRY.md").read_text(encoding="utf-8")
    if "does **not** specify what `fanout_policy=None` means" not in multi:
        failures.append("multi-export request no longer preserves unresolved fanout case")
    if "does **not** specify what" not in retry or "retry_enabled=True" not in retry:
        failures.append("retry request no longer preserves unresolved retry case")

    return failures


def trial_failures() -> list[str]:
    failures = design_failures()
    path = ROOT / "RUN_MANIFEST.json"
    if not path.is_file():
        return failures + ["RUN_MANIFEST.json is required for --trial-ready"]

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "us-language-gate-a2-run-manifest-v0":
        failures.append("RUN_MANIFEST.json schema mismatch")
    if data.get("status") != "FROZEN_BEFORE_MODEL_OUTPUTS":
        failures.append("run manifest status must be FROZEN_BEFORE_MODEL_OUTPUTS")

    source_commit = data.get("source_commit", "")
    if not isinstance(source_commit, str) or not HEX40_RE.fullmatch(source_commit):
        failures.append("source_commit must be an exact lowercase 40-hex commit")

    for key in ("model_identity", "reasoning_setting"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or "TO_FILL" in value:
            failures.append(f"{key} must be frozen exactly")

    tools = data.get("tool_permissions")
    if (
        not isinstance(tools, list)
        or not tools
        or any(not isinstance(item, str) or "TO_FILL" in item for item in tools)
    ):
        failures.append("tool_permissions must be a non-placeholder list")

    if data.get("network_access") is not False:
        failures.append("network_access must remain false")

    runtime = data.get("evaluation_runtime")
    if not isinstance(runtime, dict):
        failures.append("evaluation_runtime must be present")
    else:
        for key in ("python", "platform"):
            value = runtime.get(key)
            if not isinstance(value, str) or not value.strip() or "TO_FILL" in value:
                failures.append(f"evaluation_runtime.{key} must be frozen exactly")

    expected_order = [
        ["us", "markdown"],
        ["markdown", "us"],
        ["us", "markdown"],
        ["markdown", "us"],
        ["us", "markdown"],
    ]
    if data.get("pair_order") != expected_order:
        failures.append("pair_order differs from frozen contract")
    if data.get("fresh_context_per_stage") is not True:
        failures.append("fresh_context_per_stage must be true")

    if data.get("artifact_sha256") != expected_digests():
        failures.append("artifact_sha256 does not match current frozen artifacts")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-ready", action="store_true")
    parser.add_argument("--print-digests", action="store_true")
    args = parser.parse_args()

    if args.print_digests:
        sys.stdout.write(json.dumps(expected_digests(), sort_keys=True, indent=2) + "\n")
        return 0

    failures = trial_failures() if args.trial_ready else design_failures()
    result = {
        "schema": "us-language-gate-a2-freeze-check-v0",
        "mode": "trial-ready" if args.trial_ready else "design",
        "ok": not failures,
        "failures": failures,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
