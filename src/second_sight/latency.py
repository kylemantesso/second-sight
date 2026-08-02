"""Correlation of live fault, anomaly, and safe-stop timing events.

The tracker is deliberately ROS-independent so the correlation policy can be
tested without a ROS installation. Producers must use the same host's
``time.monotonic_ns()`` clock for a latency value to be valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def milliseconds(later_ns: int, earlier_ns: int) -> float:
    """Return a monotonic-clock interval in milliseconds."""
    if later_ns < earlier_ns:
        raise ValueError("timing events must be recorded in monotonic-clock order")
    return (later_ns - earlier_ns) / 1_000_000


@dataclass
class FaultTiming:
    """Timing state for one injected-fault interval."""

    fault_id: str
    fault_type: str
    injected_monotonic_ns: int
    decision_monotonic_ns: int | None = None
    safe_stop_monotonic_ns: int | None = None


class LatencyTracker:
    """Attach the first anomalous decision and safe-stop request to each fault.

    Scenarios are expected to inject one fault interval at a time. When several
    intervals are pending, a decision belongs to the most recently injected
    fault that has not yet been detected. A safe-stop request belongs to the
    most recently detected fault without a recorded request.
    """

    def __init__(self) -> None:
        self.faults: list[FaultTiming] = []

    def record_fault(
        self, fault_id: str, fault_type: str, injected_monotonic_ns: int
    ) -> dict[str, Any]:
        timing = FaultTiming(fault_id, fault_type, injected_monotonic_ns)
        self.faults.append(timing)
        return {
            "event": "fault_injected",
            "fault_id": fault_id,
            "fault_type": fault_type,
            "injected_monotonic_ns": injected_monotonic_ns,
        }

    def record_anomaly(
        self, decision_monotonic_ns: int, inference_ms: float | None = None
    ) -> dict[str, Any] | None:
        candidates = [
            timing
            for timing in self.faults
            if timing.decision_monotonic_ns is None
            and timing.injected_monotonic_ns <= decision_monotonic_ns
        ]
        if not candidates:
            return None
        timing = candidates[-1]
        timing.decision_monotonic_ns = decision_monotonic_ns
        measurement: dict[str, Any] = {
            "event": "anomaly_decision",
            "fault_id": timing.fault_id,
            "fault_type": timing.fault_type,
            "injected_monotonic_ns": timing.injected_monotonic_ns,
            "decision_monotonic_ns": decision_monotonic_ns,
            "fault_to_anomaly_ms": milliseconds(
                decision_monotonic_ns, timing.injected_monotonic_ns
            ),
        }
        if inference_ms is not None:
            measurement["inference_ms"] = inference_ms
        return measurement

    def record_safe_stop(self, safe_stop_monotonic_ns: int) -> dict[str, Any] | None:
        candidates = [
            timing
            for timing in self.faults
            if timing.decision_monotonic_ns is not None
            and timing.safe_stop_monotonic_ns is None
            and timing.decision_monotonic_ns <= safe_stop_monotonic_ns
        ]
        if not candidates:
            return None
        timing = candidates[-1]
        timing.safe_stop_monotonic_ns = safe_stop_monotonic_ns
        return {
            "event": "safe_stop_requested",
            "fault_id": timing.fault_id,
            "fault_type": timing.fault_type,
            "injected_monotonic_ns": timing.injected_monotonic_ns,
            "decision_monotonic_ns": timing.decision_monotonic_ns,
            "safe_stop_monotonic_ns": safe_stop_monotonic_ns,
            "fault_to_anomaly_ms": milliseconds(
                timing.decision_monotonic_ns, timing.injected_monotonic_ns
            ),
            "fault_to_safe_stop_ms": milliseconds(
                safe_stop_monotonic_ns, timing.injected_monotonic_ns
            ),
            "anomaly_to_safe_stop_ms": milliseconds(
                safe_stop_monotonic_ns, timing.decision_monotonic_ns
            ),
        }
