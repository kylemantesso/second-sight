import json
from pathlib import Path

import pytest

from second_sight.stream import iter_events, summarize_stream


def write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def test_summarize_stream(tmp_path: Path) -> None:
    stream = tmp_path / "events.jsonl"
    write_events(
        stream,
        [
            {"schema_version": 1, "kind": "detections", "timestamp_ns": 0, "objects": [{}, {}]},
            {"schema_version": 1, "kind": "trajectory", "timestamp_ns": 0, "points": []},
            {
                "schema_version": 1,
                "kind": "detections",
                "timestamp_ns": 1_000_000_000,
                "objects": [{}],
            },
            {
                "schema_version": 1,
                "kind": "trajectory",
                "timestamp_ns": 1_000_000_000,
                "points": [],
            },
        ],
    )

    summary = summarize_stream(stream)

    assert summary.event_count == 4
    assert summary.counts == {"detections": 2, "trajectory": 2}
    assert summary.rates_hz == {"detections": 1.0, "trajectory": 1.0}
    assert summary.duration_seconds == 1.0
    assert summary.object_count == 3


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    stream = tmp_path / "events.jsonl"
    write_events(stream, [{"schema_version": 2, "kind": "detections", "timestamp_ns": 0}])

    with pytest.raises(ValueError, match="unsupported schema version"):
        list(iter_events(stream))
