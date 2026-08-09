"""Deterministic PLAN/PROGRESS/TODO synchronization."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import textwrap


MAX_TODO_ITEMS = 7

_STAGE_ID_PATTERN = r"[A-F]\d+\.\d+"
_STAGE_DECLARATION = re.compile(
    rf"^(?:####\s+|-\s+)(?P<id>{_STAGE_ID_PATTERN})\s+(?:—|-)\s+"
    r"(?P<title>\S.*)$"
)
_STAGE_LIKE = re.compile(rf"^(?:####\s+|-\s+){_STAGE_ID_PATTERN}\b")
_PHASE_DECLARATION = re.compile(
    r"^###\s+Phase\s+(?P<id>[A-F]\d+)\s+(?:—|-)\s+(?P<title>\S.*)$"
)
_PROGRESS_HEADING = re.compile(
    rf"^##\s+(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s+(?:—|-)\s+"
    rf"[^\r\n]*?\b(?P<id>{_STAGE_ID_PATTERN})\b[^\r\n]*?"
    r"\b(?P<status>DONE|PARTIAL)\b"
)
_PROGRESS_STAGE_LIKE = re.compile(
    rf"^##\s+\d{{4}}-\d{{2}}-\d{{2}}\s+(?:—|-)\s+[^\r\n]*?"
    rf"\b{_STAGE_ID_PATTERN}\b"
)
_TEST_COUNT = re.compile(r"Ran\s+(\d+)\s+tests?\b")


class PlanStatusError(ValueError):
    """Raised when plan-status input is malformed or inconsistent."""


@dataclass(frozen=True)
class StageDefinition:
    id: str
    title: str
    goal: str
    phase_id: str
    phase_title: str
    ordinal: int


@dataclass(frozen=True)
class ProgressRecord:
    stage_id: str
    status: str
    recorded_on: str
    resume: str | None
    ordinal: int


@dataclass(frozen=True)
class PlanDocument:
    stages: tuple[StageDefinition, ...]

    @property
    def by_id(self) -> dict[str, StageDefinition]:
        return {stage.id: stage for stage in self.stages}


@dataclass(frozen=True)
class ProgressDocument:
    records: tuple[ProgressRecord, ...]
    completed: frozenset[str]

    def latest_partial_resume(self, stage_id: str) -> str | None:
        for record in reversed(self.records):
            if record.stage_id == stage_id:
                if record.status == "DONE":
                    return None
                return record.resume
        return None


@dataclass(frozen=True)
class PlanStatus:
    plan: PlanDocument
    progress: ProgressDocument
    remaining: tuple[StageDefinition, ...]

    @property
    def completed_count(self) -> int:
        return len(self.plan.stages) - len(self.remaining)


def _normalized_words(parts: Sequence[str]) -> str:
    return " ".join(" ".join(parts).split())


def _continuation(lines: Sequence[str], start: int) -> tuple[str, ...]:
    parts: list[str] = []
    for line in lines[start:]:
        if not line.startswith("  ") or line.lstrip().startswith("- "):
            break
        stripped = line.strip()
        if not stripped:
            break
        parts.append(stripped)
    return tuple(parts)


def _stage_goal(lines: Sequence[str], start: int, fallback: str) -> str:
    for index in range(start, len(lines)):
        line = lines[index]
        if _STAGE_DECLARATION.match(line) or _PHASE_DECLARATION.match(line):
            break
        if line.startswith("#### ") or line.startswith("### Phase "):
            break
        if line.startswith("- Goal:"):
            first = line.removeprefix("- Goal:").strip()
            return _normalized_words((first, *_continuation(lines, index + 1)))
    return fallback


def parse_plan(text: str) -> PlanDocument:
    """Parse ordered stage definitions without inferring status."""

    try:
        text.encode("utf-8")
    except UnicodeError as error:
        raise PlanStatusError("PLAN is not valid UTF-8 text") from error
    if not text.endswith("\n"):
        raise PlanStatusError("PLAN must end with LF")

    lines = text.splitlines()
    phase_titles: dict[str, str] = {}
    for line in lines:
        phase = _PHASE_DECLARATION.match(line)
        if phase:
            phase_titles[phase.group("id")] = phase.group("title").strip()

    stages: list[StageDefinition] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        declaration = _STAGE_DECLARATION.match(line)
        if declaration is None:
            if _STAGE_LIKE.match(line):
                raise PlanStatusError(
                    f"malformed PLAN stage declaration on line {index + 1}"
                )
            continue

        stage_id = declaration.group("id")
        if stage_id in seen:
            raise PlanStatusError(f"duplicate PLAN stage {stage_id}")
        seen.add(stage_id)
        title_parts = [declaration.group("title").strip()]
        if line.startswith("- "):
            title_parts.extend(_continuation(lines, index + 1))
        title = _normalized_words(title_parts)
        phase_id = stage_id.split(".", 1)[0]
        stages.append(
            StageDefinition(
                id=stage_id,
                title=title,
                goal=_stage_goal(lines, index + 1, title),
                phase_id=phase_id,
                phase_title=phase_titles.get(phase_id, phase_id),
                ordinal=len(stages),
            )
        )

    if not stages:
        raise PlanStatusError("PLAN declares no stages")
    return PlanDocument(tuple(stages))


def parse_progress(text: str, plan: PlanDocument) -> ProgressDocument:
    """Parse explicit DONE/PARTIAL headings and validate their stage IDs."""

    if not text.endswith("\n"):
        raise PlanStatusError("PROGRESS must end with LF")
    lines = text.splitlines()
    records: list[ProgressRecord] = []
    plan_ids = set(plan.by_id)

    for index, line in enumerate(lines):
        heading = _PROGRESS_HEADING.match(line)
        if heading is None:
            if _PROGRESS_STAGE_LIKE.match(line):
                raise PlanStatusError(
                    f"malformed PROGRESS stage heading on line {index + 1}"
                )
            continue
        stage_id = heading.group("id")
        if stage_id not in plan_ids:
            raise PlanStatusError(
                f"PROGRESS line {index + 1} names unknown stage {stage_id}"
            )
        _validate_date(heading.group("date"))
        resume: str | None = None
        for body_line in lines[index + 1 :]:
            if body_line.startswith("## "):
                break
            if body_line.startswith("Resume:"):
                resume = body_line.removeprefix("Resume:").strip()
                break
        records.append(
            ProgressRecord(
                stage_id=stage_id,
                status=heading.group("status"),
                recorded_on=heading.group("date"),
                resume=resume,
                ordinal=len(records),
            )
        )

    completed = frozenset(
        record.stage_id for record in records if record.status == "DONE"
    )
    return ProgressDocument(tuple(records), completed)


def build_status(plan_text: str, progress_text: str) -> PlanStatus:
    plan = parse_plan(plan_text)
    progress = parse_progress(progress_text, plan)
    remaining = tuple(
        stage for stage in plan.stages if stage.id not in progress.completed
    )
    return PlanStatus(plan, progress, remaining)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def _item(text: str) -> str:
    return textwrap.fill(
        text,
        width=88,
        initial_indent="- ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _individual_item(stage: StageDefinition) -> str:
    return _item(f"{stage.id} — {stage.title}. Goal: {_sentence(stage.goal)}")


def _group_item(stages: Sequence[StageDefinition]) -> str:
    first = stages[0]
    last = stages[-1]
    identifier = first.id if len(stages) == 1 else f"{first.id}–{last.id}"
    titles = "; ".join(f"{stage.id} {stage.title}" for stage in stages)
    return _item(
        f"{identifier} ({len(stages)} stage{'s' if len(stages) != 1 else ''}) — "
        f"{first.phase_title}: {_sentence(titles)}"
    )


def _todo_groups(
    remaining: Sequence[StageDefinition],
) -> tuple[tuple[StageDefinition, ...], ...]:
    groups: list[list[StageDefinition]] = []
    for stage in remaining:
        if not groups or groups[-1][0].phase_id != stage.phase_id:
            groups.append([])
        groups[-1].append(stage)
    return tuple(tuple(group) for group in groups)


def _todo_items(
    remaining: Sequence[StageDefinition],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    groups = _todo_groups(remaining)
    if not groups:
        return "", (), ()

    active = groups[0]
    later_groups = groups[1:]
    available_after_now = MAX_TODO_ITEMS - 1 - len(later_groups)
    if available_after_now < 0:
        raise PlanStatusError("too many unfinished phase groups for TODO limit")

    rest = active[1:]
    next_items: list[str] = []
    if len(rest) <= available_after_now:
        next_items.extend(_individual_item(stage) for stage in rest)
    else:
        if available_after_now == 0:
            raise PlanStatusError("active phase cannot fit within TODO limit")
        individual_count = max(0, available_after_now - 1)
        next_items.extend(
            _individual_item(stage) for stage in rest[:individual_count]
        )
        next_items.append(_group_item(rest[individual_count:]))

    later_items = tuple(_group_item(group) for group in later_groups)
    item_count = 1 + len(next_items) + len(later_items)
    if item_count > MAX_TODO_ITEMS:
        raise PlanStatusError("generated TODO exceeds item limit")
    return _individual_item(active[0]), tuple(next_items), later_items


def render_todo(plan_text: str, progress_text: str) -> str:
    """Render the exact generated TODO view."""

    status = build_status(plan_text, progress_text)
    now, next_items, later_items = _todo_items(status.remaining)
    lines = [
        "# TODO — Generated remaining work",
        "",
        "> Generated by `python tools/plan_status.py sync`. Do not edit by hand.",
        "> PLAN defines stages; PROGRESS records DONE/PARTIAL; this file shows only",
        "> unfinished work.",
        "",
        f"Status: {status.completed_count}/{len(status.plan.stages)} stages complete; "
        f"{len(status.remaining)} remaining.",
        f"PLAN source: `{_sha256(plan_text)}`.",
        f"PROGRESS source: `{_sha256(progress_text)}`.",
        "",
    ]

    if not status.remaining:
        lines.extend(("All declared stages are complete.", ""))
    else:
        lines.extend(("## Now", "", now, ""))
        resume = status.progress.latest_partial_resume(status.remaining[0].id)
        lines.append(
            "Resume: " + (resume if resume is not None else "no PARTIAL record.")
        )
        lines.append("")
        if next_items:
            lines.extend((f"## Next in {status.remaining[0].phase_id}", ""))
            lines.extend(next_items)
            lines.append("")
        if later_items:
            lines.extend(("## Later phases", ""))
            lines.extend(later_items)
            lines.append("")

    lines.extend(
        (
            "Completed work and evidence remain in [PROGRESS.md](PROGRESS.md).",
            "Stage definitions and dependencies remain in [PLAN.md](PLAN.md).",
            "",
        )
    )
    return "\n".join(lines)


def _repository_text(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise PlanStatusError(f"cannot read {relative}: {error}") from error


def repository_status(root: Path) -> PlanStatus:
    return build_status(
        _repository_text(root, "PLAN.md"),
        _repository_text(root, "PROGRESS.md"),
    )


def sync_repository(root: Path) -> PlanStatus:
    plan_text = _repository_text(root, "PLAN.md")
    progress_text = _repository_text(root, "PROGRESS.md")
    rendered = render_todo(plan_text, progress_text)
    try:
        (root / "TODO.md").write_bytes(rendered.encode("utf-8"))
    except OSError as error:
        raise PlanStatusError(f"cannot write TODO.md: {error}") from error
    return build_status(plan_text, progress_text)


def check_repository(root: Path) -> PlanStatus:
    plan_text = _repository_text(root, "PLAN.md")
    progress_text = _repository_text(root, "PROGRESS.md")
    expected = render_todo(plan_text, progress_text)
    actual = _repository_text(root, "TODO.md")
    if actual != expected:
        raise PlanStatusError("TODO.md is stale; run plan_status.py sync")
    return build_status(plan_text, progress_text)


def _validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PlanStatusError("date must be ISO YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise PlanStatusError("date must be canonical ISO YYYY-MM-DD")
    return value


def _validate_notes(name: str, values: Sequence[str]) -> tuple[str, ...]:
    if not values:
        raise PlanStatusError(f"at least one {name} note is required")
    normalized: list[str] = []
    for value in values:
        if not value or value.strip() != value or "\n" in value or "\r" in value:
            raise PlanStatusError(f"{name} notes must be non-empty single lines")
        normalized.append(value)
    return tuple(normalized)


def run_full_suite(root: Path) -> int:
    """Run the mandatory verifier suite and return its exact test count."""

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        tail = "\n".join(output.splitlines()[-15:])
        raise PlanStatusError(f"full verifier suite failed\n{tail}")
    matches = _TEST_COUNT.findall(output)
    if not matches:
        raise PlanStatusError("cannot determine full-suite test count")
    count = int(matches[-1])
    return count


def _baseline_count(root: Path) -> int:
    try:
        baseline = int(_repository_text(root, "guardrails/test_baseline.txt").strip())
    except ValueError as error:
        raise PlanStatusError("test baseline is not an integer") from error
    if baseline <= 0:
        raise PlanStatusError("test baseline must be positive")
    return baseline


def _wrapped_entry_line(prefix: str, text: str) -> str:
    return textwrap.fill(
        text,
        width=88,
        initial_indent=prefix,
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _append_entry(
    root: Path,
    progress_text: str,
    entry: str,
) -> PlanStatus:
    if not progress_text.endswith("\n"):
        raise PlanStatusError("PROGRESS must end with LF before append")
    updated_progress = progress_text + "\n" + entry
    plan_text = _repository_text(root, "PLAN.md")
    updated_todo = render_todo(plan_text, updated_progress)
    try:
        (root / "PROGRESS.md").write_bytes(updated_progress.encode("utf-8"))
        (root / "TODO.md").write_bytes(updated_todo.encode("utf-8"))
    except OSError as error:
        raise PlanStatusError(f"cannot update progress files: {error}") from error
    return build_status(plan_text, updated_progress)


def _validated_record_inputs(
    root: Path,
    stage_id: str,
    recorded_on: str,
    positive: Sequence[str],
    negative: Sequence[str],
    evidence: Sequence[str],
) -> tuple[PlanStatus, StageDefinition, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    status = check_repository(root)
    stage = status.plan.by_id.get(stage_id)
    if stage is None:
        raise PlanStatusError(f"unknown stage {stage_id}")
    if stage_id in status.progress.completed:
        raise PlanStatusError(f"stage {stage_id} is already DONE")
    _validate_date(recorded_on)
    return (
        status,
        stage,
        _validate_notes("positive", positive),
        _validate_notes("negative", negative),
        _validate_notes("evidence", evidence),
    )


def record_done(
    root: Path,
    *,
    stage_id: str,
    recorded_on: str,
    positive: Sequence[str],
    negative: Sequence[str],
    evidence: Sequence[str],
    verifier: Callable[[Path], int] = run_full_suite,
) -> tuple[PlanStatus, int]:
    """Verify, append one DONE record, and synchronize TODO."""

    status, stage, positives, negatives, evidence_notes = _validated_record_inputs(
        root, stage_id, recorded_on, positive, negative, evidence
    )
    count = verifier(root)
    baseline = _baseline_count(root)
    if count != baseline:
        raise PlanStatusError(
            f"full-suite count {count} does not equal baseline {baseline}"
        )
    lines = [
        f"## {recorded_on} - {stage.id}: {stage.title} - DONE",
        "",
        *(_wrapped_entry_line("+ ", note) for note in positives),
        *(_wrapped_entry_line("- ", note) for note in negatives),
        _wrapped_entry_line(
            "Evidence: ",
            f"full suite -> {count}/{count}; " + "; ".join(evidence_notes) + ".",
        ),
    ]
    simulated_progress = status.progress.completed | {stage.id}
    next_stage = next(
        (item for item in status.plan.stages if item.id not in simulated_progress),
        None,
    )
    lines.append(
        "Next: all declared stages complete."
        if next_stage is None
        else _wrapped_entry_line("Next: ", f"{next_stage.id} — {next_stage.title}.")
    )
    lines.append("")
    return _append_entry(
        root,
        _repository_text(root, "PROGRESS.md"),
        "\n".join(lines),
    ), count


def record_partial(
    root: Path,
    *,
    stage_id: str,
    recorded_on: str,
    positive: Sequence[str],
    negative: Sequence[str],
    evidence: Sequence[str],
    resume: str,
) -> PlanStatus:
    """Append one PARTIAL record and synchronize TODO without completing it."""

    status, stage, positives, negatives, evidence_notes = _validated_record_inputs(
        root, stage_id, recorded_on, positive, negative, evidence
    )
    resumes = _validate_notes("resume", (resume,))
    lines = [
        f"## {recorded_on} - {stage.id}: {stage.title} - PARTIAL",
        "",
        *(_wrapped_entry_line("+ ", note) for note in positives),
        *(_wrapped_entry_line("- ", note) for note in negatives),
        _wrapped_entry_line("Evidence: ", "; ".join(evidence_notes) + "."),
        _wrapped_entry_line("Resume: ", resumes[0]),
        _wrapped_entry_line("Next: ", f"{stage.id} remains active."),
        "",
    ]
    return _append_entry(
        root,
        _repository_text(root, "PROGRESS.md"),
        "\n".join(lines),
    )
