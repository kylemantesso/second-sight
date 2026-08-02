"""Correlation of live fault, anomaly, and safe-stop timing events.

The tracker is deliberately ROS-independent so the correlation policy can be
tested without a ROS installation. Producers must use the same host's
``time.monotonic_ns()`` clock for a latency value to be valid.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


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
    decision_path: str | None = None
    safe_stop_monotonic_ns: int | None = None
    safe_stop_path: str | None = None
    safe_stop_emitted: bool = False


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
        self,
        decision_monotonic_ns: int,
        inference_ms: float | None = None,
        path: str | None = None,
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
        timing.decision_path = path
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
        if path is not None:
            measurement["decision_path"] = path
        return measurement

    def completed_safe_stop(self) -> dict[str, Any] | None:
        """Return one previously buffered stop once its decision is known.

        Decision and stop telemetry use different ROS topics. DDS preserves
        order within each topic, but a subscriber can observe the stop before
        its preceding decision. Buffering that stop preserves the true
        monotonic timestamps instead of losing a valid near-zero interval.
        """
        candidates = [
            timing
            for timing in self.faults
            if timing.decision_monotonic_ns is not None
            and timing.safe_stop_monotonic_ns is not None
            and not timing.safe_stop_emitted
        ]
        if not candidates:
            return None
        timing = candidates[-1]
        timing.safe_stop_emitted = True
        assert timing.safe_stop_monotonic_ns is not None
        assert timing.decision_monotonic_ns is not None
        measurement = {
            "event": "safe_stop_requested",
            "fault_id": timing.fault_id,
            "fault_type": timing.fault_type,
            "injected_monotonic_ns": timing.injected_monotonic_ns,
            "decision_monotonic_ns": timing.decision_monotonic_ns,
            "safe_stop_monotonic_ns": timing.safe_stop_monotonic_ns,
            "fault_to_anomaly_ms": milliseconds(
                timing.decision_monotonic_ns, timing.injected_monotonic_ns
            ),
            "fault_to_safe_stop_ms": milliseconds(
                timing.safe_stop_monotonic_ns, timing.injected_monotonic_ns
            ),
            "anomaly_to_safe_stop_ms": milliseconds(
                timing.safe_stop_monotonic_ns, timing.decision_monotonic_ns
            ),
        }
        if timing.decision_path is not None:
            measurement["decision_path"] = timing.decision_path
        if timing.safe_stop_path is not None:
            measurement["safe_stop_path"] = timing.safe_stop_path
        return measurement

    def record_safe_stop(
        self, safe_stop_monotonic_ns: int, path: str | None = None
    ) -> dict[str, Any] | None:
        candidates = [
            timing
            for timing in self.faults
            if timing.safe_stop_monotonic_ns is None
            and timing.injected_monotonic_ns <= safe_stop_monotonic_ns
        ]
        if not candidates:
            return None
        timing = candidates[-1]
        timing.safe_stop_monotonic_ns = safe_stop_monotonic_ns
        timing.safe_stop_path = path
        return self.completed_safe_stop()


def latency_percentiles(values: list[float]) -> dict[str, float]:
    """Return standard percentiles for a non-empty run-level measurement list."""
    if not values:
        raise ValueError("cannot summarize an empty latency sample")
    sample = np.asarray(values, dtype=np.float64)
    return {
        "min": float(sample.min()),
        "p50": float(np.percentile(sample, 50)),
        "p95": float(np.percentile(sample, 95)),
        "p99": float(np.percentile(sample, 99)),
        "max": float(sample.max()),
    }


def aggregate_latency_runs(paths: list[Path], output: Path) -> dict[str, Any]:
    """Aggregate one completed fault-to-stop JSONL trace per input path.

    The raw per-run traces remain the source of truth. This summary only
    accepts files containing exactly one safe-stop record so accidental mixed
    scenario traces cannot silently distort percentiles.
    """
    if not paths:
        raise ValueError("at least one latency trace is required")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        try:
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}: invalid JSONL") from error
        stops = [record for record in records if record.get("event") == "safe_stop_requested"]
        if len(stops) != 1:
            raise ValueError(f"{path}: expected exactly one safe-stop record, found {len(stops)}")
        stop = stops[0]
        try:
            fault_id = str(stop["fault_id"])
            fault_type = str(stop["fault_type"])
            fault_to_anomaly_ms = float(stop["fault_to_anomaly_ms"])
            fault_to_safe_stop_ms = float(stop["fault_to_safe_stop_ms"])
            anomaly_to_safe_stop_ms = float(stop["anomaly_to_safe_stop_ms"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{path}: malformed safe-stop record") from error
        decision_path = str(stop.get("decision_path", "unknown"))
        groups[(fault_id, fault_type, decision_path)].append(
            {
                "path": str(path),
                "fault_to_anomaly_ms": fault_to_anomaly_ms,
                "fault_to_safe_stop_ms": fault_to_safe_stop_ms,
                "anomaly_to_safe_stop_ms": anomaly_to_safe_stop_ms,
            }
        )

    summaries = []
    for (fault_id, fault_type, decision_path), runs in sorted(groups.items()):
        summaries.append(
            {
                "fault_id": fault_id,
                "fault_type": fault_type,
                "decision_path": decision_path,
                "run_count": len(runs),
                "fault_to_anomaly_ms": latency_percentiles(
                    [run["fault_to_anomaly_ms"] for run in runs]
                ),
                "fault_to_safe_stop_ms": latency_percentiles(
                    [run["fault_to_safe_stop_ms"] for run in runs]
                ),
                "anomaly_to_safe_stop_ms": latency_percentiles(
                    [run["anomaly_to_safe_stop_ms"] for run in runs]
                ),
                "source_paths": [run["path"] for run in runs],
            }
        )
    report = {
        "schema_version": 1,
        "kind": "live_latency_summary",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "trace_count": len(paths),
        "groups": summaries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
