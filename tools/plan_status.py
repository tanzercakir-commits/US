"""Synchronize PLAN, PROGRESS, and the generated TODO view."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_verifier.plan_status import (  # noqa: E402
    PlanStatusError,
    build_status,
    check_repository,
    record_done,
    record_partial,
    render_todo,
    sync_repository,
)


def _notes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--positive", action="append", required=True)
    parser.add_argument("--negative", action="append", required=True)
    parser.add_argument("--evidence", action="append", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TODO and append guarded PROGRESS records."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync", help="regenerate TODO from PLAN and PROGRESS")
    check = commands.add_parser("check", help="fail when TODO is stale")
    check.add_argument(
        "--staged",
        action="store_true",
        help="read PLAN, PROGRESS, and TODO from the Git index",
    )
    done = commands.add_parser(
        "record-done", help="run the full suite and append one DONE record"
    )
    _notes(done)
    partial = commands.add_parser(
        "record-partial", help="append one PARTIAL record and exact resume point"
    )
    _notes(partial)
    partial.add_argument("--resume", required=True)
    return parser


def _staged_text(root: Path, relative: str) -> str:
    completed = subprocess.run(
        ["git", "show", f":{relative}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PlanStatusError(f"cannot read staged {relative}: {reason}")
    try:
        return completed.stdout.decode("utf-8")
    except UnicodeError as error:
        raise PlanStatusError(f"staged {relative} is not UTF-8") from error


def _check_staged(root: Path) -> tuple[int, int]:
    plan_text = _staged_text(root, "PLAN.md")
    progress_text = _staged_text(root, "PROGRESS.md")
    todo_text = _staged_text(root, "TODO.md")
    expected = render_todo(plan_text, progress_text)
    if todo_text != expected:
        raise PlanStatusError("staged TODO.md is stale; run plan_status.py sync")
    status = build_status(plan_text, progress_text)
    return status.completed_count, len(status.remaining)


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = arguments.root.resolve()
    try:
        if arguments.command == "sync":
            status = sync_repository(root)
            print(
                f"TODO synchronized: {status.completed_count}/"
                f"{len(status.plan.stages)} complete; {len(status.remaining)} remaining"
            )
        elif arguments.command == "check":
            if arguments.staged:
                completed, remaining = _check_staged(root)
            else:
                status = check_repository(root)
                completed, remaining = status.completed_count, len(status.remaining)
            print(f"plan status synchronized: {completed} complete; {remaining} remaining")
        elif arguments.command == "record-done":
            status, count = record_done(
                root,
                stage_id=arguments.stage,
                recorded_on=arguments.date,
                positive=arguments.positive,
                negative=arguments.negative,
                evidence=arguments.evidence,
            )
            print(
                f"recorded {arguments.stage} DONE after {count} tests; "
                f"{len(status.remaining)} stages remain"
            )
        else:
            status = record_partial(
                root,
                stage_id=arguments.stage,
                recorded_on=arguments.date,
                positive=arguments.positive,
                negative=arguments.negative,
                evidence=arguments.evidence,
                resume=arguments.resume,
            )
            print(
                f"recorded {arguments.stage} PARTIAL; "
                f"{len(status.remaining)} stages remain"
            )
    except PlanStatusError as error:
        print(f"plan status error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
