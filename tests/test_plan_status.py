from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.plan_status import (
    MAX_TODO_ITEMS,
    PlanStatusError,
    build_status,
    check_repository,
    parse_plan,
    parse_progress,
    record_done,
    record_partial,
    render_todo,
    repository_status,
    sync_repository,
)


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "plan_status.py"

PLAN = """# Plan

### Phase A1 — First phase

#### A1.1 — First stage

- Goal: finish the first stage exactly.

#### A1.2 — Second stage

- Goal: finish the second stage.

### Phase B2 — Later phase

- B2.1 — Compact stage
  with a continued title
"""

EMPTY_PROGRESS = """# Progress
"""


def done(stage: str, title: str = "stage") -> str:
    return f"## 2026-08-09 - {stage}: {title} - DONE\n\nEvidence: pass.\n"


def partial(stage: str, resume: str = "resume here") -> str:
    return (
        f"## 2026-08-09 - {stage}: stage - PARTIAL\n\n"
        f"Resume: {resume}\n"
    )


def write_repository(root: Path, plan: str, progress: str, baseline: int = 5) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "guardrails").mkdir(exist_ok=True)
    (root / "PLAN.md").write_bytes(plan.encode("utf-8"))
    (root / "PROGRESS.md").write_bytes(progress.encode("utf-8"))
    (root / "guardrails" / "test_baseline.txt").write_text(
        f"{baseline}\n", encoding="utf-8", newline="\n"
    )
    (root / "TODO.md").write_bytes(render_todo(plan, progress).encode("utf-8"))


class PlanStatusTests(unittest.TestCase):
    def test_plan_parses_heading_and_compact_stages_in_order(self) -> None:
        plan = parse_plan(PLAN)

        self.assertEqual(tuple(stage.id for stage in plan.stages), ("A1.1", "A1.2", "B2.1"))
        self.assertEqual(plan.stages[0].goal, "finish the first stage exactly.")
        self.assertEqual(plan.stages[2].title, "Compact stage with a continued title")
        self.assertEqual(plan.stages[2].phase_title, "Later phase")
        with self.assertRaises(FrozenInstanceError):
            plan.stages[0].title = "changed"  # type: ignore[misc]

    def test_duplicate_and_malformed_plan_stages_fail_closed(self) -> None:
        with self.assertRaisesRegex(PlanStatusError, "duplicate PLAN stage A1.1"):
            parse_plan(PLAN + "\n#### A1.1 — duplicate\n")
        with self.assertRaisesRegex(PlanStatusError, "malformed PLAN stage"):
            parse_plan("# Plan\n\n#### A1.1 missing separator\n")
        with self.assertRaisesRegex(PlanStatusError, "end with LF"):
            parse_plan(PLAN.rstrip("\n"))

    def test_progress_requires_known_stage_and_terminal_status(self) -> None:
        plan = parse_plan(PLAN)
        with self.assertRaisesRegex(PlanStatusError, "unknown stage C3.1"):
            parse_progress(done("C3.1"), plan)
        with self.assertRaisesRegex(PlanStatusError, "malformed PROGRESS"):
            parse_progress(
                "# Progress\n\n## 2026-08-09 - A1.1: missing status\n",
                plan,
            )

    def test_partial_never_completes_and_later_done_wins(self) -> None:
        plan = parse_plan(PLAN)
        progress = parse_progress(partial("A1.1", "line 40"), plan)
        self.assertEqual(progress.completed, frozenset())
        self.assertEqual(progress.latest_partial_resume("A1.1"), "line 40")

        progress = parse_progress(partial("A1.1") + "\n" + done("A1.1"), plan)
        self.assertEqual(progress.completed, frozenset({"A1.1"}))
        self.assertIsNone(progress.latest_partial_resume("A1.1"))

    def test_todo_contains_only_remaining_work_and_exact_counts(self) -> None:
        rendered = render_todo(PLAN, done("A1.1"))

        self.assertIn("Status: 1/3 stages complete; 2 remaining.", rendered)
        self.assertNotIn("Goal: finish the first stage", rendered)
        self.assertIn("A1.2 — Second stage", rendered)
        self.assertIn("B2.1 (1 stage) — Later phase", rendered)
        self.assertIn("PLAN source: `sha256:", rendered)
        self.assertEqual(rendered, render_todo(PLAN, done("A1.1")))

    def test_todo_groups_without_hiding_or_exceeding_seven_items(self) -> None:
        lines = ["# Plan", "", "### Phase A1 — Active"]
        for number in range(1, 9):
            lines.extend(("", f"#### A1.{number} — active {number}", "", f"- Goal: goal {number}."))
        for phase in ("B2", "C3"):
            lines.extend(("", f"### Phase {phase} — phase {phase}", "", f"#### {phase}.1 — later"))
        plan = "\n".join(lines) + "\n"
        rendered = render_todo(plan, EMPTY_PROGRESS)

        bullets = [line for line in rendered.splitlines() if line.startswith("- ")]
        self.assertLessEqual(len(bullets), MAX_TODO_ITEMS)
        for stage in ("A1.1", "A1.8", "B2.1", "C3.1"):
            self.assertIn(stage, rendered)

    def test_too_many_phase_groups_fail_instead_of_omitting_work(self) -> None:
        lines = ["# Plan"]
        for number in range(1, 9):
            lines.extend(
                (
                    "",
                    f"### Phase A{number} — phase {number}",
                    "",
                    f"#### A{number}.1 — stage {number}",
                )
            )
        with self.assertRaisesRegex(PlanStatusError, "too many unfinished"):
            render_todo("\n".join(lines) + "\n", EMPTY_PROGRESS)

    def test_sync_is_relocated_and_check_detects_stale_todo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for name in ("one", "two"):
                root = Path(directory) / name
                write_repository(root, PLAN, done("A1.1"))
                status = sync_repository(root)
                outputs.append((root / "TODO.md").read_bytes())
                self.assertEqual(status.completed_count, 1)
                check_repository(root)
            self.assertEqual(outputs[0], outputs[1])

            (Path(directory) / "one" / "TODO.md").write_text(
                "stale\n", encoding="utf-8", newline="\n"
            )
            with self.assertRaisesRegex(PlanStatusError, "stale"):
                check_repository(Path(directory) / "one")

    def test_done_verifier_failure_and_count_mismatch_write_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, EMPTY_PROGRESS)
            before = ((root / "PROGRESS.md").read_bytes(), (root / "TODO.md").read_bytes())

            def fail(_: Path) -> int:
                raise PlanStatusError("injected verifier failure")

            with self.assertRaisesRegex(PlanStatusError, "injected"):
                record_done(
                    root,
                    stage_id="A1.1",
                    recorded_on="2026-08-09",
                    positive=("implemented",),
                    negative=("no blocker",),
                    evidence=("focused pass",),
                    verifier=fail,
                )
            self.assertEqual(
                before,
                ((root / "PROGRESS.md").read_bytes(), (root / "TODO.md").read_bytes()),
            )

            with self.assertRaisesRegex(PlanStatusError, "does not equal baseline"):
                record_done(
                    root,
                    stage_id="A1.1",
                    recorded_on="2026-08-09",
                    positive=("implemented",),
                    negative=("no blocker",),
                    evidence=("focused pass",),
                    verifier=lambda _: 4,
                )
            self.assertEqual(before[0], (root / "PROGRESS.md").read_bytes())

    def test_done_appends_without_changing_prefix_and_synchronizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, EMPTY_PROGRESS)
            prefix = (root / "PROGRESS.md").read_bytes()
            status, count = record_done(
                root,
                stage_id="A1.1",
                recorded_on="2026-08-09",
                positive=("implemented",),
                negative=("no blocker",),
                evidence=("focused pass",),
                verifier=lambda _: 5,
            )

            progress = (root / "PROGRESS.md").read_bytes()
            self.assertTrue(progress.startswith(prefix))
            self.assertEqual(count, 5)
            self.assertEqual(status.completed_count, 1)
            self.assertIn(b"A1.1: First stage - DONE", progress)
            self.assertNotIn("A1.1 — First stage", (root / "TODO.md").read_text(encoding="utf-8"))
            check_repository(root)

    def test_done_rejects_existing_stage_invalid_date_and_stale_todo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, done("A1.1"))
            common = dict(
                root=root,
                stage_id="A1.1",
                recorded_on="2026-08-09",
                positive=("implemented",),
                negative=("no blocker",),
                evidence=("focused pass",),
                verifier=lambda _: 5,
            )
            with self.assertRaisesRegex(PlanStatusError, "already DONE"):
                record_done(**common)

            common["stage_id"] = "A1.2"
            common["recorded_on"] = "09-08-2026"
            with self.assertRaisesRegex(PlanStatusError, "ISO"):
                record_done(**common)

            common["recorded_on"] = "2026-08-09"
            (root / "TODO.md").write_text("stale\n", encoding="utf-8")
            with self.assertRaisesRegex(PlanStatusError, "stale"):
                record_done(**common)

    def test_partial_requires_resume_and_surfaces_it_in_todo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, EMPTY_PROGRESS)
            with self.assertRaisesRegex(PlanStatusError, "resume"):
                record_partial(
                    root,
                    stage_id="A1.1",
                    recorded_on="2026-08-09",
                    positive=("started",),
                    negative=("blocked",),
                    evidence=("focused incomplete",),
                    resume="",
                )
            status = record_partial(
                root,
                stage_id="A1.1",
                recorded_on="2026-08-09",
                positive=("started",),
                negative=("blocked",),
                evidence=("focused incomplete",),
                resume="continue at exact file line 40",
            )
            self.assertEqual(status.completed_count, 0)
            todo = (root / "TODO.md").read_text(encoding="utf-8")
            self.assertIn("Resume: continue at exact file line 40", todo)

    def test_cli_sync_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, done("A1.1"))
            (root / "TODO.md").write_text("stale\n", encoding="utf-8")
            sync = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "sync"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            check = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "check"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync.returncode, 0, sync.stderr)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("2 remaining", sync.stdout)

    def test_staged_check_uses_index_and_detects_staged_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repository(root, PLAN, EMPTY_PROGRESS)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "PLAN.md", "PROGRESS.md", "TODO.md"], cwd=root, check=True)

            (root / "TODO.md").write_text("unstaged noise\n", encoding="utf-8")
            clean_index = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "check", "--staged"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(clean_index.returncode, 0, clean_index.stderr)

            (root / "PROGRESS.md").write_text(done("A1.1"), encoding="utf-8", newline="\n")
            subprocess.run(["git", "add", "PROGRESS.md"], cwd=root, check=True)
            stale_index = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "check", "--staged"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(stale_index.returncode, 2)
            self.assertIn("staged TODO.md is stale", stale_index.stderr)

    def test_live_repository_has_only_the_declared_remaining_programs(self) -> None:
        status = repository_status(ROOT)
        remaining = {stage.id for stage in status.remaining}
        expected = {
            *(f"A7.{number}" for number in range(4, 9)),
            *(f"B5.{number}" for number in range(0, 6)),
            *(f"F6.{number}" for number in range(0, 4)),
        }
        self.assertEqual(len(status.plan.stages), 137)
        self.assertTrue(expected <= remaining)
        self.assertLessEqual(remaining, expected | {"F5.5", "F5.6", "F5.7"})


if __name__ == "__main__":
    unittest.main()
