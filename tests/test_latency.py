from __future__ import annotations

import pytest

from second_sight.latency import LatencyTracker, milliseconds


def test_tracker_records_fault_to_anomaly_and_safe_stop() -> None:
    tracker = LatencyTracker()

    assert tracker.record_fault("phantom-pedestrian", "phantom", 1_000_000_000) == {
        "event": "fault_injected",
        "fault_id": "phantom-pedestrian",
        "fault_type": "phantom",
        "injected_monotonic_ns": 1_000_000_000,
    }

    decision = tracker.record_anomaly(
        1_037_125_000, inference_ms=0.8, path="perception_guardrails"
    )
    assert decision == {
        "event": "anomaly_decision",
        "fault_id": "phantom-pedestrian",
        "fault_type": "phantom",
        "injected_monotonic_ns": 1_000_000_000,
        "decision_monotonic_ns": 1_037_125_000,
        "fault_to_anomaly_ms": 37.125,
        "inference_ms": 0.8,
        "decision_path": "perception_guardrails",
    }

    stop = tracker.record_safe_stop(1_037_875_000, path="perception_guardrails")
    assert stop == {
        "event": "safe_stop_requested",
        "fault_id": "phantom-pedestrian",
        "fault_type": "phantom",
        "injected_monotonic_ns": 1_000_000_000,
        "decision_monotonic_ns": 1_037_125_000,
        "safe_stop_monotonic_ns": 1_037_875_000,
        "fault_to_anomaly_ms": 37.125,
        "fault_to_safe_stop_ms": 37.875,
        "anomaly_to_safe_stop_ms": 0.75,
        "decision_path": "perception_guardrails",
        "safe_stop_path": "perception_guardrails",
    }


def test_tracker_uses_most_recent_pending_fault() -> None:
    tracker = LatencyTracker()
    tracker.record_fault("vanish-car", "vanish", 1_000_000_000)
    tracker.record_fault("teleport-car", "teleport", 2_000_000_000)

    decision = tracker.record_anomaly(2_020_000_000)

    assert decision is not None
    assert decision["fault_id"] == "teleport-car"
    assert decision["fault_to_anomaly_ms"] == 20.0


def test_tracker_buffers_stop_that_arrives_before_decision() -> None:
    tracker = LatencyTracker()
    tracker.record_fault("teleport-car", "teleport", 1_000_000_000)

    assert tracker.record_safe_stop(1_040_000_000, path="trajectory_hybrid") is None
    decision = tracker.record_anomaly(1_030_000_000, path="trajectory_hybrid")
    stop = tracker.completed_safe_stop()

    assert decision is not None
    assert stop is not None
    assert stop["fault_id"] == "teleport-car"
    assert stop["fault_to_anomaly_ms"] == 30.0
    assert stop["fault_to_safe_stop_ms"] == 40.0
    assert stop["anomaly_to_safe_stop_ms"] == 10.0


def test_tracker_ignores_events_without_a_preceding_fault() -> None:
    tracker = LatencyTracker()

    assert tracker.record_anomaly(1_000_000_000) is None
    assert tracker.record_safe_stop(1_000_000_000) is None


def test_milliseconds_rejects_non_monotonic_events() -> None:
    with pytest.raises(ValueError, match="monotonic-clock order"):
        milliseconds(1, 2)
