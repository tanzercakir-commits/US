#!/usr/bin/env python3
"""Render both Gate A2 model-facing conditions from one canonical fact manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SECTIONS = ("intent", "architecture", "rules", "freedom", "flow", "unknowns")
MD_TITLES = {
    "intent": "Intent",
    "architecture": "Architecture",
    "rules": "Required rules",
    "freedom": "Deliberately delegated choices",
    "flow": "Required flow",
    "unknowns": "Open decisions",
}


def load_manifest() -> dict:
    return json.loads((ROOT / "FACT_MANIFEST.json").read_text(encoding="utf-8"))


def facts_by_section(manifest: dict) -> dict[str, list[dict]]:
    grouped = {section: [] for section in SECTIONS}
    for fact in manifest["facts"]:
        grouped[fact["class"]].append(fact)
    return grouped


def render_us(manifest: dict) -> str:
    grouped = facts_by_section(manifest)
    lines = [f"system {manifest['system']}", ""]
    for section in SECTIONS:
        lines.append(f"{section}:")
        for fact in grouped[section]:
            lines.append(f"    [{fact['id']}] {fact['us']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(manifest: dict) -> str:
    grouped = facts_by_section(manifest)
    lines = [
        f"# {manifest['system']} specification",
        "",
        "Every bracketed fact ID corresponds to the same canonical fact used by",
        "the sibling structured condition. The prose below is normative.",
        "",
    ]
    for section in SECTIONS:
        lines.append(f"## {MD_TITLES[section]}")
        lines.append("")
        for fact in grouped[section]:
            lines.append(f"- **[{fact['id']}]** {fact['canonical']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest()
    expected = {
        ROOT / "WORKFLOWRELAY.us.txt": render_us(manifest),
        ROOT / "WORKFLOWRELAY.md": render_markdown(manifest),
    }

    if args.check:
        failures = []
        for path, content in expected.items():
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                failures.append(str(path.name))
        if failures:
            raise SystemExit("condition rendering mismatch: " + ", ".join(failures))
        return 0

    for path, content in expected.items():
        path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
