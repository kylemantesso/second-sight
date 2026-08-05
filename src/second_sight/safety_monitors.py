"""Deterministic, normal-data-calibrated perception safety monitors.

These monitors deliberately complement, rather than replace, the statistical
anomaly model.  They run directly on detection frames, so a missing detection
stream, collapsed confidence, or stale source timestamp has a clear and
auditable decision path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceHealthConfig:
    """Clean-data floors for an object-bearing perception frame."""

    mean_existence_floor: float
    mean_classification_floor: float
    consecutive_frames: int = 2

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ConfidenceHealthConfig:
        config = cls(
            mean_existence_floor=float(value["mean_existence_floor"]),
            mean_classification_floor=float(value["mean_classification_floor"]),
            consecutive_frames=int(value.get("consecutive_frames", 2)),
        )
        if not 0 <= config.mean_existence_floor <= 1:
            raise ValueError("confidence existence floor must be between 0 and 1")
        if not 0 <= config.mean_classification_floor <= 1:
            raise ValueError("confidence classification floor must be between 0 and 1")
        if config.consecutive_frames <= 0:
            raise ValueError("confidence consecutive_frames must be positive")
        return config

    def as_dict(self) -> dict[str, float | int]:
        return {
            "mean_existence_floor": self.mean_existence_floor,
            "mean_classification_floor": self.mean_classification_floor,
            "consecutive_frames": self.consecutive_frames,
        }


@dataclass(frozen=True)
class SourceFreshnessConfig:
    """Clean-data source-age limit for a perception frame."""

    max_source_age_ms: float
    consecutive_frames: int = 2

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SourceFreshnessConfig:
        config = cls(
            max_source_age_ms=float(value["max_source_age_ms"]),
            consecutive_frames=int(value.get("consecutive_frames", 2)),
        )
        if config.max_source_age_ms < 0:
            raise ValueError("source freshness age must be non-negative")
        if config.consecutive_frames <= 0:
            raise ValueError("source freshness consecutive_frames must be positive")
        return config

    def as_dict(self) -> dict[str, float | int]:
        return {
            "max_source_age_ms": self.max_source_age_ms,
            "consecutive_frames": self.consecutive_frames,
        }


def monitor_config_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Return a validated v2 monitor configuration, if the model has one."""
    raw = metadata.get("safety_monitors")
    if raw is None:
        return None
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported safety monitor schema")
    confidence = ConfidenceHealthConfig.from_dict(raw["confidence_health"])
    freshness = SourceFreshnessConfig.from_dict(raw["source_freshness"])
    timeout_ms = float(raw["perception_liveness"]["timeout_ms"])
    if timeout_ms <= 0:
        raise ValueError("perception liveness timeout must be positive")
    return {
        "schema_version": 1,
        "confidence_health": confidence.as_dict(),
        "source_freshness": freshness.as_dict(),
        "perception_liveness": {"timeout_ms": timeout_ms},
    }


class ConsecutiveCondition:
    """Latch only after a condition has been true on consecutive frames."""

    def __init__(self, required: int) -> None:
        if required <= 0:
            raise ValueError("required consecutive frames must be positive")
        self.required = required
        self.count = 0

    def observe(self, active: bool) -> tuple[bool, int]:
        self.count = self.count + 1 if active else 0
        return self.count >= self.required, self.count


class DetectionSafetyMonitors:
    """Stateful confidence and source-freshness checks for detection frames."""

    def __init__(self, config: dict[str, Any] | None) -> None:
        self.config = config
        self.confidence: ConfidenceHealthConfig | None = None
        self.freshness: SourceFreshnessConfig | None = None
        self.confidence_condition: ConsecutiveCondition | None = None
        self.freshness_condition: ConsecutiveCondition | None = None
        if config is not None:
            self.confidence = ConfidenceHealthConfig.from_dict(config["confidence_health"])
            self.freshness = SourceFreshnessConfig.from_dict(config["source_freshness"])
            self.confidence_condition = ConsecutiveCondition(self.confidence.consecutive_frames)
            self.freshness_condition = ConsecutiveCondition(self.freshness.consecutive_frames)

    @property
    def enabled(self) -> bool:
        return self.config is not None

    def observe(self, row: dict[str, float | int]) -> list[dict[str, Any]]:
        """Score one detection-frame feature row and return all decision paths."""
        if not self.enabled:
            return []
        assert self.confidence is not None
        assert self.freshness is not None
        assert self.confidence_condition is not None
        assert self.freshness_condition is not None

        object_bearing = float(row["object_count"]) > 0
        low_confidence = object_bearing and (
            float(row["mean_existence_probability"])
            < self.confidence.mean_existence_floor
            and float(row["mean_classification_probability"])
            < self.confidence.mean_classification_floor
        )
        confidence_anomalous, confidence_count = self.confidence_condition.observe(low_confidence)

        stale = float(row["source_age_ms"]) > self.freshness.max_source_age_ms
        freshness_anomalous, freshness_count = self.freshness_condition.observe(stale)
        return [
            {
                "path": "confidence_health",
                "anomalous": confidence_anomalous,
                "consecutive_anomalies": confidence_count,
                "object_bearing": object_bearing,
                "mean_existence_probability": float(row["mean_existence_probability"]),
                "mean_classification_probability": float(
                    row["mean_classification_probability"]
                ),
            },
            {
                "path": "source_freshness",
                "anomalous": freshness_anomalous,
                "consecutive_anomalies": freshness_count,
                "source_age_ms": float(row["source_age_ms"]),
            },
        ]
