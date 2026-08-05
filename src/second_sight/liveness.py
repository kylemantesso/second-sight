"""Monotonic-clock liveness tracking for a perception stream."""

from __future__ import annotations


class DetectionLiveness:
    """Arm only after the first detection, then report one elapsed timeout."""

    def __init__(self, timeout_ms: float) -> None:
        if timeout_ms <= 0:
            raise ValueError("liveness timeout must be positive")
        self.timeout_ns = round(timeout_ms * 1_000_000)
        self.last_detection_ns: int | None = None
        self.reported = False

    def record_detection(self, monotonic_ns: int) -> None:
        self.last_detection_ns = monotonic_ns
        self.reported = False

    def timed_out(self, monotonic_ns: int) -> bool:
        if self.last_detection_ns is None or self.reported:
            return False
        if monotonic_ns - self.last_detection_ns < self.timeout_ns:
            return False
        self.reported = True
        return True

    def timeout_at_ns(self) -> int | None:
        """Return the deadline for the currently armed timeout."""
        if self.last_detection_ns is None:
            return None
        return self.last_detection_ns + self.timeout_ns
