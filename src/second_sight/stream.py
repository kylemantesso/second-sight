"""Read and inspect the ROS-independent Second Sight event stream."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EVENT_KINDS = {"detections", "trajectory"}


def event_time_ns(event: dict[str, Any]) -> int:
    """Return the replay timeline timestamp, falling back to the source header."""
    recorded_ns = event.get("recorded_ns")
    return recorded_ns if isinstance(recorded_ns, int) else event["timestamp_ns"]


@dataclass(frozen=True)
class StreamSummary:
    event_count: int
    counts: dict[str, int]
    rates_hz: dict[str, float]
    duration_seconds: float
    detection_frames: int
    object_count: int
    fault_event_count: int


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield validated events from a newline-delimited JSON stream."""
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error

            if event.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(f"{path}:{line_number}: unsupported schema version")
            if event.get("kind") not in EVENT_KINDS:
                raise ValueError(f"{path}:{line_number}: unsupported event kind")
            if not isinstance(event.get("timestamp_ns"), int):
                raise ValueError(f"{path}:{line_number}: timestamp_ns must be an integer")
            yield event


def summarize_stream(path: Path) -> StreamSummary:
    counts: Counter[str] = Counter()
    timestamps: dict[str, list[int]] = defaultdict(list)
    object_count = 0
    fault_event_count = 0

    for event in iter_events(path):
        kind = event["kind"]
        counts[kind] += 1
        timestamps[kind].append(event["timestamp_ns"])
        if kind == "detections":
            object_count += len(event.get("objects", []))
        if event.get("faults"):
            fault_event_count += 1

    all_timestamps = [timestamp for values in timestamps.values() for timestamp in values]
    duration_seconds = 0.0
    if len(all_timestamps) > 1:
        duration_seconds = (max(all_timestamps) - min(all_timestamps)) / 1_000_000_000

    rates_hz = {}
    for kind, values in timestamps.items():
        span_seconds = (max(values) - min(values)) / 1_000_000_000 if len(values) > 1 else 0
        rates_hz[kind] = (len(values) - 1) / span_seconds if span_seconds > 0 else 0.0

    return StreamSummary(
        event_count=sum(counts.values()),
        counts=dict(counts),
        rates_hz=rates_hz,
        duration_seconds=duration_seconds,
        detection_frames=counts["detections"],
        object_count=object_count,
        fault_event_count=fault_event_count,
    )
