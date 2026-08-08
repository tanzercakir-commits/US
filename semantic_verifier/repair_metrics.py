"""Append-only repair-loop metrics with an isolated timing boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .repair_bundle import RepairBundle
from .repair_loop import RepairLoopLog


REPAIR_METRIC_SCHEMA = "codeskeptic.repair-metrics/v1"
REPAIR_METRIC_ID_SCHEMA = "codeskeptic.repair-metrics-identity/v1"


class RepairMetricsError(ValueError):
    """Raised when repair telemetry violates its append-only contract."""


def _identity_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _content_id(payload: Mapping[str, Any]) -> str:
    return _sha256(
        _identity_bytes(
            {
                "kind": "repair-metric",
                "schema": REPAIR_METRIC_ID_SCHEMA,
                "value": payload,
            }
        )
    )


def _require_hash(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in value[7:]
        )
    ):
        raise RepairMetricsError(
            f"{field} must be a lowercase sha256 identity"
        )
    return value


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RepairMetricsError(
            f"{field} must be non-empty text"
        )
    return value


def _exact_keys(
    payload: Mapping[str, Any],
    required: set[str],
    field: str,
) -> None:
    actual = set(payload)
    missing = sorted(required - actual)
    unknown = sorted(actual - required)
    if missing:
        raise RepairMetricsError(
            f"{field} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise RepairMetricsError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class RepairMetric:
    id: str
    bundle: str
    loop: str
    obligation: str
    iterations: int
    success: bool
    final_status: str
    elapsed_ns: int

    def __post_init__(self) -> None:
        _require_hash(self.bundle, "metric.bundle")
        _require_hash(self.loop, "metric.loop")
        _require_text(self.obligation, "metric.obligation")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 1
        ):
            raise RepairMetricsError(
                "metric.iterations must be a positive integer"
            )
        if not isinstance(self.success, bool):
            raise RepairMetricsError(
                "metric.success must be bool"
            )
        if self.final_status not in {"exhausted", "verified"}:
            raise RepairMetricsError(
                "metric.final_status is unsupported"
            )
        if self.success != (self.final_status == "verified"):
            raise RepairMetricsError(
                "metric success/final_status disagree"
            )
        if (
            isinstance(self.elapsed_ns, bool)
            or not isinstance(self.elapsed_ns, int)
            or self.elapsed_ns < 0
        ):
            raise RepairMetricsError(
                "metric.elapsed_ns must be a non-negative integer"
            )
        expected = _content_id(self.content_dict())
        if _require_hash(self.id, "metric.id") != expected:
            raise RepairMetricsError(
                "metric.id does not match canonical content"
            )

    @classmethod
    def create(
        cls,
        *,
        bundle: str,
        loop: str,
        obligation: str,
        iterations: int,
        success: bool,
        final_status: str,
        elapsed_ns: int,
    ) -> "RepairMetric":
        content = {
            "bundle": bundle,
            "elapsed_ns": elapsed_ns,
            "final_status": final_status,
            "iterations": iterations,
            "loop": loop,
            "obligation": obligation,
            "schema": REPAIR_METRIC_SCHEMA,
            "success": success,
        }
        return cls(
            _content_id(content),
            bundle,
            loop,
            obligation,
            iterations,
            success,
            final_status,
            elapsed_ns,
        )

    @classmethod
    def from_artifacts(
        cls,
        bundle: RepairBundle,
        loop: RepairLoopLog,
        elapsed_ns: int,
    ) -> "RepairMetric":
        if loop.initial_bundle != bundle.id:
            raise RepairMetricsError(
                "loop does not cite supplied bundle"
            )
        return cls.create(
            bundle=bundle.id,
            loop=loop.id,
            obligation=str(bundle.obligation["id"]),
            iterations=len(loop.attempts),
            success=loop.status == "verified",
            final_status=loop.status,
            elapsed_ns=elapsed_ns,
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "bundle": self.bundle,
            "elapsed_ns": self.elapsed_ns,
            "final_status": self.final_status,
            "iterations": self.iterations,
            "loop": self.loop,
            "obligation": self.obligation,
            "schema": REPAIR_METRIC_SCHEMA,
            "success": self.success,
        }

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.content_dict()}

    def to_json_line(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ) + "\n"


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RepairMetricsError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RepairMetricsError(
        f"non-finite JSON number {value!r} is not allowed"
    )


def load_metric_json(text: str) -> RepairMetric:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise RepairMetricsError(
            f"invalid repair metric JSON: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise RepairMetricsError(
            "repair metric must be a JSON object"
        )
    _exact_keys(
        payload,
        {
            "bundle",
            "elapsed_ns",
            "final_status",
            "id",
            "iterations",
            "loop",
            "obligation",
            "schema",
            "success",
        },
        "metric",
    )
    if payload["schema"] != REPAIR_METRIC_SCHEMA:
        raise RepairMetricsError(
            "unsupported repair metric schema"
        )
    return RepairMetric(
        payload["id"],
        payload["bundle"],
        payload["loop"],
        payload["obligation"],
        payload["iterations"],
        payload["success"],
        payload["final_status"],
        payload["elapsed_ns"],
    )


def load_metrics_jsonl(text: str) -> tuple[RepairMetric, ...]:
    if not text:
        return ()
    if not text.endswith("\n"):
        raise RepairMetricsError(
            "metrics JSONL must end with a newline"
        )
    rows: list[RepairMetric] = []
    for index, line in enumerate(text.splitlines()):
        if not line:
            raise RepairMetricsError(
                f"metrics line {index + 1} is empty"
            )
        row = load_metric_json(line)
        if row.to_json_line().rstrip("\n") != line:
            raise RepairMetricsError(
                f"metrics line {index + 1} is not canonical"
            )
        rows.append(row)
    ids = [row.id for row in rows]
    loops = [row.loop for row in rows]
    if len(ids) != len(set(ids)):
        raise RepairMetricsError(
            "metrics ledger has duplicate row IDs"
        )
    if len(loops) != len(set(loops)):
        raise RepairMetricsError(
            "metrics ledger has duplicate loop IDs"
        )
    return tuple(rows)


def append_metric(
    path: str | os.PathLike[str],
    metric: RepairMetric,
) -> None:
    target = Path(path)
    try:
        prior = (
            target.read_bytes().decode("utf-8")
            if target.exists()
            else ""
        )
    except (OSError, UnicodeError) as error:
        raise RepairMetricsError(
            f"cannot read metrics ledger: {error}"
        ) from error
    rows = load_metrics_jsonl(prior)
    if metric.id in {row.id for row in rows}:
        raise RepairMetricsError(
            "metrics ledger already contains row ID"
        )
    if metric.loop in {row.loop for row in rows}:
        raise RepairMetricsError(
            "metrics ledger already contains loop ID"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    data = metric.to_json_line().encode("utf-8")
    try:
        with target.open("ab") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise RepairMetricsError(
            f"cannot append metrics ledger: {error}"
        ) from error


def measure_repair(
    run: Callable[[], RepairLoopLog],
    bundle: RepairBundle,
    *,
    clock_ns: Callable[[], int],
) -> tuple[RepairLoopLog, RepairMetric]:
    """Measure outside the loop; duration never enters run decisions."""

    start = clock_ns()
    loop = run()
    stop = clock_ns()
    for value, field in ((start, "start"), (stop, "stop")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise RepairMetricsError(
                f"clock {field} must be an integer"
            )
    if stop < start:
        raise RepairMetricsError(
            "monotonic clock moved backwards"
        )
    return loop, RepairMetric.from_artifacts(
        bundle,
        loop,
        stop - start,
    )


def summarize_metrics(
    rows: Sequence[RepairMetric],
) -> dict[str, object]:
    ordered = tuple(sorted(rows, key=lambda row: row.id))
    return {
        "count": len(ordered),
        "failed": sum(not row.success for row in ordered),
        "schema": "codeskeptic.repair-metrics-summary/v1",
        "succeeded": sum(row.success for row in ordered),
        "total_elapsed_ns": sum(
            row.elapsed_ns for row in ordered
        ),
        "total_iterations": sum(
            row.iterations for row in ordered
        ),
    }


def summary_json(rows: Sequence[RepairMetric]) -> str:
    return (
        json.dumps(
            summarize_metrics(rows),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
