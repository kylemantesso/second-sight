import json
from pathlib import Path

import pytest

from second_sight.latency import aggregate_latency_runs


def write_trace(path: Path, stop_ms: float) -> None:
    records = [
        {"event": "fault_injected", "fault_id": "vanish-car", "fault_type": "vanish"},
        {
            "event": "safe_stop_requested",
            "fault_id": "vanish-car",
            "fault_type": "vanish",
            "decision_path": "perception_guardrails",
            "fault_to_anomaly_ms": stop_ms - 100,
            "fault_to_safe_stop_ms": stop_ms,
            "anomaly_to_safe_stop_ms": 100.0,
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


def test_aggregate_latency_runs_writes_percentile_summary(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    output = tmp_path / "summary.json"
    write_trace(first, 101.0)
    write_trace(second, 103.0)

    report = aggregate_latency_runs([first, second], output)

    assert report["trace_count"] == 2
    assert report["groups"][0]["run_count"] == 2
    assert report["groups"][0]["fault_to_safe_stop_ms"]["p50"] == 102.0
    assert json.loads(output.read_text())["kind"] == "live_latency_summary"


def test_aggregate_latency_runs_rejects_incomplete_trace(tmp_path: Path) -> None:
    trace = tmp_path / "incomplete.jsonl"
    trace.write_text(json.dumps({"event": "fault_injected"}) + "\n")

    with pytest.raises(ValueError, match="exactly one safe-stop"):
        aggregate_latency_runs([trace], tmp_path / "summary.json")
