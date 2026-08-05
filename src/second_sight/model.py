"""Isolation Forest training and fault-interval evaluation."""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from second_sight.features import FEATURE_NAMES, FeatureExtractor, read_feature_csv
from second_sight.liveness import DetectionLiveness
from second_sight.safety_monitors import (
    ConfidenceHealthConfig,
    DetectionSafetyMonitors,
    SourceFreshnessConfig,
    monitor_config_from_metadata,
)
from second_sight.stream import event_time_ns, iter_events

EXPERIMENTAL_FEATURES = {
    "missing_near_object_count",
    "max_missing_near_object_ticks",
}
MODEL_FEATURE_NAMES = tuple(name for name in FEATURE_NAMES if name not in EXPERIMENTAL_FEATURES)

# Generic guardrails must tolerate a new route's legitimate traffic density and
# class composition. Absolute counts and confidence are therefore handled by
# the forest and the dedicated confidence monitor, not by hard bounds.
GUARDRAIL_FEATURES = (
    "mean_object_displacement_m",
    "max_object_displacement_m",
    "max_relative_object_displacement_m",
    "unmatched_previous_object_count",
    "unexpected_object_drop_count",
    "object_count_delta",
    "centroid_shift_m",
)
PERCEPTION_GUARDRAIL_FEATURES = tuple(
    name
    for name in GUARDRAIL_FEATURES
    if name
    not in {
        # These are calculated using the current/planning ego pose. A detection
        # message alone cannot provide stable values for them.
        "max_relative_object_displacement_m",
        "unexpected_object_drop_count",
    }
)
DEFAULT_GUARDRAIL_BOUND_QUANTILE = 0.005
SENSITIVE_GUARDRAIL_BOUND_QUANTILE = 0.02
SENSITIVE_GUARDRAIL_FEATURES = {
    "object_count_delta",
    "max_relative_object_displacement_m",
    "unexpected_object_drop_count",
}
SAFETY_MONITOR_BRANCH_COUNT = 4
SAFETY_MONITOR_CONSECUTIVE_FRAMES = 2
LIVENESS_MIN_TIMEOUT_MS = 300.0
LIVENESS_TIMEOUT_MARGIN = 1.5


def learn_guardrails(matrix: np.ndarray) -> dict[str, dict[str, float]]:
    bounds = {}
    for name in GUARDRAIL_FEATURES:
        values = matrix[:, MODEL_FEATURE_NAMES.index(name)]
        if name in SENSITIVE_GUARDRAIL_FEATURES:
            quantile = SENSITIVE_GUARDRAIL_BOUND_QUANTILE
        else:
            quantile = DEFAULT_GUARDRAIL_BOUND_QUANTILE
        lower = float(np.quantile(values, quantile))
        upper = float(np.quantile(values, 1 - quantile))
        spread = max(
            float(np.quantile(values, 0.75) - np.quantile(values, 0.25)),
            upper - lower,
            abs(float(np.median(values))) * 0.01,
            1e-6,
        )
        bounds[name] = {
            "lower": lower,
            "upper": upper,
            "spread": spread,
            "tolerance": max(spread * 1e-6, 1e-9),
            "bound_quantile": quantile,
        }
    return bounds


def score_guardrails(
    matrix: np.ndarray, bounds: dict[str, dict[str, float]]
) -> tuple[np.ndarray, np.ndarray]:
    violations = np.zeros((len(matrix), len(GUARDRAIL_FEATURES)), dtype=np.float64)
    for column, name in enumerate(GUARDRAIL_FEATURES):
        values = matrix[:, MODEL_FEATURE_NAMES.index(name)]
        bound = bounds[name]
        below = (bound["lower"] - bound["tolerance"] - values) / bound["spread"]
        above = (values - bound["upper"] - bound["tolerance"]) / bound["spread"]
        violations[:, column] = np.maximum(np.maximum(below, above), 0.0)
    return violations.max(axis=1), violations


def select_guardrail_violations(
    violations: np.ndarray, features: tuple[str, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Return the maximum score and per-feature violations for a feature subset."""
    unknown = set(features).difference(GUARDRAIL_FEATURES)
    if unknown:
        raise ValueError(f"unknown guardrail features: {sorted(unknown)}")
    if not features:
        raise ValueError("at least one guardrail feature is required")
    indices = [GUARDRAIL_FEATURES.index(name) for name in features]
    selected = violations[:, indices]
    return selected.max(axis=1), selected


def score_feature_matrix(
    bundle: dict[str, Any], matrix: np.ndarray, mode: str
) -> dict[str, np.ndarray | float]:
    metadata = bundle["metadata"]
    forest_scores = -bundle["model"].score_samples(matrix)
    forest_threshold = float(metadata["threshold"])
    forest_predictions = forest_scores >= forest_threshold
    guardrail_scores, guardrail_violations = score_guardrails(matrix, metadata["guardrails"])
    guardrail_threshold = float(metadata["guardrail_threshold"])
    guardrail_predictions = guardrail_scores > guardrail_threshold
    if mode == "isolation_forest":
        predictions = forest_predictions
    elif mode == "guardrails":
        predictions = guardrail_predictions
    elif mode == "hybrid":
        predictions = forest_predictions | guardrail_predictions
    else:
        raise ValueError(f"unsupported detector mode: {mode}")
    return {
        "forest_scores": forest_scores,
        "forest_threshold": forest_threshold,
        "guardrail_scores": guardrail_scores,
        "guardrail_threshold": guardrail_threshold,
        "guardrail_violations": guardrail_violations,
        "predictions": predictions,
    }


class SecondSightScorer:
    """Score incremental feature rows using a persisted detector bundle."""

    def __init__(
        self,
        model_path: Path,
        mode: str = "hybrid",
        guardrail_features: tuple[str, ...] = GUARDRAIL_FEATURES,
        implementation: str = "optimized",
    ) -> None:
        self.bundle = joblib.load(model_path)
        self.mode = mode
        self.guardrail_features = guardrail_features
        self.implementation = implementation
        # Validate once on construction instead of during a live decision.
        select_guardrail_violations(
            np.zeros((1, len(GUARDRAIL_FEATURES)), dtype=np.float64), guardrail_features
        )
        if self.bundle["metadata"]["feature_names"] != list(MODEL_FEATURE_NAMES):
            raise ValueError("model feature schema does not match this package")
        if implementation not in {"reference", "optimized"}:
            raise ValueError("implementation must be 'reference' or 'optimized'")
        self.guardrail_indices = np.asarray(
            [MODEL_FEATURE_NAMES.index(name) for name in guardrail_features], dtype=np.intp
        )
        metadata = self.bundle["metadata"]
        self.safety_monitor_config = monitor_config_from_metadata(metadata)
        self.guardrail_lower = np.asarray(
            [metadata["guardrails"][name]["lower"] for name in guardrail_features],
            dtype=np.float64,
        )
        self.guardrail_upper = np.asarray(
            [metadata["guardrails"][name]["upper"] for name in guardrail_features],
            dtype=np.float64,
        )
        self.guardrail_spread = np.asarray(
            [metadata["guardrails"][name]["spread"] for name in guardrail_features],
            dtype=np.float64,
        )
        self.guardrail_tolerance = np.asarray(
            [metadata["guardrails"][name]["tolerance"] for name in guardrail_features],
            dtype=np.float64,
        )
        self.guardrail_threshold = float(metadata["guardrail_threshold"])

    def score(self, row: dict[str, float | int]) -> dict[str, Any]:
        """Score one feature row.

        The perception fast path uses guardrails only. In its optimized mode,
        deliberately skip Isolation Forest scoring: the old implementation
        performed a full forest traversal and then discarded it. Hybrid and
        forest modes retain the reference forest calculation.
        """
        matrix = np.asarray([[float(row[name]) for name in MODEL_FEATURE_NAMES]], dtype=np.float64)
        if self.mode == "guardrails" and self.implementation == "optimized":
            return self.score_guardrails_only(matrix)
        result = score_feature_matrix(self.bundle, matrix, self.mode)
        guardrail_scores, selected_violations = select_guardrail_violations(
            result["guardrail_violations"], self.guardrail_features
        )
        violations = selected_violations[0]
        threshold = float(result["guardrail_threshold"])
        forest_anomalous = bool(result["forest_scores"][0] >= result["forest_threshold"])
        guardrail_anomalous = bool(guardrail_scores[0] > threshold)
        if self.mode == "isolation_forest":
            anomalous = forest_anomalous
        elif self.mode == "guardrails":
            anomalous = guardrail_anomalous
        elif self.mode == "hybrid":
            anomalous = forest_anomalous or guardrail_anomalous
        else:
            raise ValueError(f"unsupported detector mode: {self.mode}")
        return {
            "anomalous": anomalous,
            "forest_score": float(result["forest_scores"][0]),
            "forest_threshold": float(result["forest_threshold"]),
            "guardrail_score": float(guardrail_scores[0]),
            "guardrail_features": [
                name
                for index, name in enumerate(self.guardrail_features)
                if violations[index] > threshold
            ],
        }

    def score_guardrails_only(self, matrix: np.ndarray) -> dict[str, Any]:
        """Score selected guardrails without evaluating the unused forest.

        This matches the guardrail decision and per-feature violation policy of
        :func:`score_feature_matrix` for one row. ``forest_score`` is ``None``
        by design because no Isolation Forest work occurred.
        """
        values = matrix[0, self.guardrail_indices]
        below = (self.guardrail_lower - self.guardrail_tolerance - values) / (
            self.guardrail_spread
        )
        above = (values - self.guardrail_upper - self.guardrail_tolerance) / (
            self.guardrail_spread
        )
        violations = np.maximum(np.maximum(below, above), 0.0)
        guardrail_score = float(violations.max())
        return {
            "anomalous": bool(guardrail_score > self.guardrail_threshold),
            "forest_score": None,
            "forest_threshold": float(self.bundle["metadata"]["threshold"]),
            "guardrail_score": guardrail_score,
            "guardrail_features": [
                name
                for index, name in enumerate(self.guardrail_features)
                if violations[index] > self.guardrail_threshold
            ],
        }


def train_model(
    datasets: list[Path],
    output: Path,
    *,
    trees: int = 300,
    threshold_quantile: float = 0.99,
    min_rows_per_dataset: int = 1,
) -> dict[str, Any]:
    if trees <= 0:
        raise ValueError("trees must be positive")
    if not 0.5 < threshold_quantile < 1:
        raise ValueError("threshold quantile must be between 0.5 and 1")
    if min_rows_per_dataset <= 0:
        raise ValueError("minimum rows per dataset must be positive")

    rows = []
    included_datasets = []
    skipped_datasets = []
    selected_indices = [FEATURE_NAMES.index(name) for name in MODEL_FEATURE_NAMES]
    for dataset in datasets:
        _, values = read_feature_csv(dataset)
        if len(values) < min_rows_per_dataset:
            skipped_datasets.append(str(dataset))
            continue
        rows.extend([[row[index] for index in selected_indices] for row in values])
        included_datasets.append(str(dataset))
    if not rows:
        raise ValueError("no datasets met the minimum row requirement")
    matrix = np.asarray(rows, dtype=np.float64)
    model = make_pipeline(
        StandardScaler(),
        IsolationForest(
            n_estimators=trees,
            max_samples=min(256, len(matrix)),
            contamination="auto",
            random_state=2026,
            n_jobs=-1,
        ),
    )
    started = time.perf_counter()
    model.fit(matrix)
    training_seconds = time.perf_counter() - started
    training_scores = -model.score_samples(matrix)
    threshold = float(np.quantile(training_scores, threshold_quantile))
    guardrails = learn_guardrails(matrix)
    guardrail_threshold = 0.0
    metadata = {
        "schema_version": 1,
        "model_type": "isolation_forest",
        "feature_names": list(MODEL_FEATURE_NAMES),
        "training_datasets": included_datasets,
        "skipped_datasets": skipped_datasets,
        "training_rows": len(matrix),
        "trees": trees,
        "threshold_quantile": threshold_quantile,
        "min_rows_per_dataset": min_rows_per_dataset,
        "threshold": threshold,
        "training_seconds": training_seconds,
        "training_score_min": float(training_scores.min()),
        "training_score_max": float(training_scores.max()),
        "guardrail_features": list(GUARDRAIL_FEATURES),
        "guardrails": guardrails,
        "guardrail_threshold": guardrail_threshold,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metadata": metadata}, output)
    output.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def file_sha256(path: Path) -> str:
    """Return a SHA-256 digest without loading a model twice into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def calibration_matrix(
    datasets: list[Path], min_rows_per_dataset: int
) -> tuple[np.ndarray, list[str]]:
    """Read the production-model columns from validation-only feature CSVs."""
    selected_indices = [FEATURE_NAMES.index(name) for name in MODEL_FEATURE_NAMES]
    rows = []
    included = []
    for dataset in datasets:
        _, values = read_feature_csv(dataset)
        if len(values) < min_rows_per_dataset:
            continue
        rows.extend([[row[index] for index in selected_indices] for row in values])
        included.append(str(dataset))
    if not rows:
        raise ValueError("no validation datasets met the minimum row requirement")
    return np.asarray(rows, dtype=np.float64), included


def monitor_rows_from_streams(
    streams: list[Path],
) -> tuple[list[dict[str, float | int]], list[str]]:
    """Extract one direct-perception row per detection frame from clean streams.

    The hybrid model is trained on planning ticks, while deterministic safety
    monitors act when a perception message arrives.  Calibrating those paths
    from direct detection rows avoids counting one perception frame repeatedly
    at the planner's higher rate.
    """
    from second_sight.features import FeatureExtractor

    rows: list[dict[str, float | int]] = []
    included: list[str] = []
    for stream in streams:
        extractor = FeatureExtractor()
        stream_rows = []
        for event in iter_events(stream):
            if event["kind"] == "trajectory":
                extractor.update_trajectory_context(event)
            else:
                stream_rows.append(extractor.process_detection_tick(event))
        if stream_rows:
            rows.extend(stream_rows)
            included.append(str(stream))
    if not rows:
        raise ValueError("no detection frames found in monitor calibration streams")
    return rows, included


def monitor_rows_from_features(matrix: np.ndarray) -> list[dict[str, float]]:
    """Compatibility fallback for older calibration invocations.

    New final runs should pass monitor streams.  This fallback keeps the CLI
    usable with existing feature-only experiments and marks that limitation in
    frozen metadata.
    """
    return [
        {name: float(row[index]) for index, name in enumerate(MODEL_FEATURE_NAMES)}
        for row in matrix
    ]


def lower_tail_floor(values: np.ndarray, allocation: float) -> float:
    """Pick a strict lower bound that cannot exceed its empirical allocation."""
    selected = float(np.quantile(values, allocation, method="lower"))
    return max(0.0, float(np.nextafter(selected, -np.inf)))


def build_safety_monitor_config(
    monitor_rows: list[dict[str, float | int]], *, branch_allocation: float
) -> dict[str, Any]:
    """Freeze direct-perception monitor thresholds from normal data only."""
    if not monitor_rows:
        raise ValueError("cannot calibrate safety monitors without detection rows")
    object_rows = [row for row in monitor_rows if float(row["object_count"]) > 0]
    if not object_rows:
        raise ValueError("monitor calibration requires object-bearing detection frames")
    existence = np.asarray(
        [float(row["mean_existence_probability"]) for row in object_rows], dtype=np.float64
    )
    classification = np.asarray(
        [float(row["mean_classification_probability"]) for row in object_rows], dtype=np.float64
    )
    source_age = np.asarray(
        [float(row["source_age_ms"]) for row in monitor_rows], dtype=np.float64
    )
    gaps = np.asarray(
        [
            float(row["detection_gap_ms"])
            for row in monitor_rows
            if float(row["detection_gap_ms"]) > 0
        ],
        dtype=np.float64,
    )
    # Feature-only compatibility calibration cannot distinguish planner ticks
    # from detection frames, so it may not retain an inter-message gap. New
    # final runs pass direct streams; legacy callers get the conservative
    # minimum timeout and are marked as such in calibration metadata.
    observed_gap_ms = float(gaps.max()) if len(gaps) else None
    timeout_ms = max(
        LIVENESS_MIN_TIMEOUT_MS,
        (observed_gap_ms or 0.0) * LIVENESS_TIMEOUT_MARGIN,
    )
    timeout_ms = float(np.ceil(timeout_ms / 10.0) * 10.0)
    existence_floor = lower_tail_floor(existence, branch_allocation)
    classification_floor = lower_tail_floor(classification, branch_allocation)
    confidence = ConfidenceHealthConfig(
        # Some Autoware sources intentionally publish zero existence
        # probabilities. A zero floor cannot distinguish a collapse, so omit
        # that channel and rely on the remaining calibrated confidence signal.
        mean_existence_floor=existence_floor if existence_floor > 0 else None,
        mean_classification_floor=(
            classification_floor if classification_floor > 0 else None
        ),
        consecutive_frames=SAFETY_MONITOR_CONSECUTIVE_FRAMES,
    )
    freshness = SourceFreshnessConfig(
        max_source_age_ms=upper_tail_threshold(source_age, branch_allocation, strict=False),
        consecutive_frames=SAFETY_MONITOR_CONSECUTIVE_FRAMES,
    )
    return {
        "schema_version": 1,
        "confidence_health": confidence.as_dict(),
        "source_freshness": freshness.as_dict(),
        "perception_liveness": {"timeout_ms": timeout_ms},
        "calibration": {
            "branch_allocation": branch_allocation,
            "detection_frames": len(monitor_rows),
            "object_bearing_detection_frames": len(object_rows),
            "max_observed_detection_gap_ms": observed_gap_ms,
            "liveness_timeout_margin": LIVENESS_TIMEOUT_MARGIN,
            "liveness_minimum_timeout_ms": LIVENESS_MIN_TIMEOUT_MS,
        },
    }


def score_safety_monitors(
    rows: list[dict[str, float | int]], config: dict[str, Any]
) -> np.ndarray:
    """Return one union prediction per direct detection frame."""
    monitors = DetectionSafetyMonitors(config)
    return np.asarray(
        [any(result["anomalous"] for result in monitors.observe(row)) for row in rows], dtype=bool
    )


def upper_tail_threshold(values: np.ndarray, allocation: float, *, strict: bool) -> float:
    """Choose a deterministic empirical upper-tail threshold.

    ``strict`` is used for the forest's ``>=`` decision so ties at the chosen
    rank cannot exceed the allocation.  Guardrails use a strict ``>`` decision
    and therefore retain the exact selected value.
    """
    selected = float(np.quantile(values, 1 - allocation, method="higher"))
    return float(np.nextafter(selected, np.inf)) if strict else selected


def calibrate_model(
    source_model_path: Path,
    validation_datasets: list[Path],
    output: Path,
    *,
    target_clean_fpr: float = 0.01,
    min_rows_per_dataset: int = 1,
    monitor_streams: list[Path] | None = None,
) -> dict[str, Any]:
    """Freeze hybrid thresholds using clean validation data only.

    The forest, generic guardrails, confidence-health, and source-freshness
    branches each receive one quarter of the prescribed FPR budget. Their OR
    is therefore bounded by that budget on the calibration cohort, without
    looking at faults or final-test streams. Liveness is calibrated to the
    observed clean inter-message cadence and must be validated independently.
    """
    if not 0 < target_clean_fpr < 0.5:
        raise ValueError("target clean FPR must be between 0 and 0.5")
    if min_rows_per_dataset <= 0:
        raise ValueError("minimum rows per dataset must be positive")
    bundle = joblib.load(source_model_path)
    metadata = bundle["metadata"]
    if metadata["feature_names"] != list(MODEL_FEATURE_NAMES):
        raise ValueError("model feature schema does not match this package")
    matrix, included = calibration_matrix(validation_datasets, min_rows_per_dataset)
    scores = score_feature_matrix(bundle, matrix, "hybrid")
    allocation = target_clean_fpr / SAFETY_MONITOR_BRANCH_COUNT
    forest_threshold = upper_tail_threshold(scores["forest_scores"], allocation, strict=True)
    guardrail_threshold = upper_tail_threshold(scores["guardrail_scores"], allocation, strict=False)

    if monitor_streams:
        monitor_rows, monitor_sources = monitor_rows_from_streams(monitor_streams)
        monitor_calibration_source = "direct_detection_streams"
    else:
        monitor_rows = monitor_rows_from_features(matrix)
        monitor_sources = included
        monitor_calibration_source = "feature_rows_compatibility_fallback"
    safety_monitors = build_safety_monitor_config(monitor_rows, branch_allocation=allocation)

    frozen_bundle = deepcopy(bundle)
    frozen_metadata = frozen_bundle["metadata"]
    frozen_metadata["threshold"] = forest_threshold
    frozen_metadata["guardrail_threshold"] = guardrail_threshold
    frozen_metadata["safety_monitors"] = safety_monitors
    frozen_scores = score_feature_matrix(frozen_bundle, matrix, "hybrid")
    hybrid_predictions = np.asarray(frozen_scores["predictions"], dtype=bool)
    monitor_predictions = score_safety_monitors(monitor_rows, safety_monitors)
    calibration = {
        "method": "validation_upper_tail_four_branch_budget",
        "target_clean_fpr": target_clean_fpr,
        "branch_allocation": allocation,
        "validation_datasets": included,
        "validation_rows": int(len(matrix)),
        "source_model": str(source_model_path),
        "source_model_sha256": file_sha256(source_model_path),
        "forest_threshold_before": float(metadata["threshold"]),
        "forest_threshold_after": forest_threshold,
        "guardrail_threshold_before": float(metadata["guardrail_threshold"]),
        "guardrail_threshold_after": guardrail_threshold,
        "observed_hybrid_false_positive_rate": float(hybrid_predictions.mean()),
        "observed_hybrid_false_positive_ticks": int(hybrid_predictions.sum()),
        "monitor_calibration_source": monitor_calibration_source,
        "monitor_calibration_datasets": monitor_sources,
        "monitor_false_positive_rate": float(monitor_predictions.mean()),
        "monitor_false_positive_frames": int(monitor_predictions.sum()),
    }
    # Retain these compatibility names for existing reports and callers. They
    # describe the hybrid planning-tick branch only; monitor outcomes are
    # recorded separately because their denominator is detection frames.
    calibration["observed_validation_false_positive_rate"] = calibration[
        "observed_hybrid_false_positive_rate"
    ]
    calibration["observed_validation_false_positive_ticks"] = calibration[
        "observed_hybrid_false_positive_ticks"
    ]
    frozen_metadata["calibration"] = calibration
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(frozen_bundle, output)
    output.with_suffix(".metadata.json").write_text(
        json.dumps(frozen_metadata, indent=2) + "\n", encoding="utf-8"
    )
    return frozen_metadata


def evaluate_model(
    stream: Path,
    model_path: Path,
    ground_truth_path: Path,
    output: Path,
    *,
    mode: str = "isolation_forest",
) -> dict[str, Any]:
    bundle = joblib.load(model_path)
    metadata = bundle["metadata"]
    if metadata["feature_names"] != list(MODEL_FEATURE_NAMES):
        raise ValueError("model feature schema does not match this package")

    monitor_config = monitor_config_from_metadata(metadata)
    rows: list[dict[str, float | int]] = []
    monitor_rows: list[dict[str, float | int]] = []
    decisions: list[dict[str, Any]] = []
    extractor = FeatureExtractor()
    monitor_extractor = FeatureExtractor() if monitor_config is not None else None
    monitors = DetectionSafetyMonitors(monitor_config)
    liveness = (
        DetectionLiveness(float(monitor_config["perception_liveness"]["timeout_ms"]))
        if monitor_config is not None
        else None
    )
    for event in iter_events(stream):
        now_ns = event_time_ns(event)
        if liveness is not None and liveness.timed_out(now_ns):
            timeout_ns = liveness.timeout_at_ns()
            assert timeout_ns is not None
            decisions.append(
                {
                    "timestamp_ns": timeout_ns,
                    "path": "perception_liveness_timeout",
                    "anomalous": True,
                    "consecutive_anomalies": 1,
                }
            )
        if event["kind"] == "detections":
            if liveness is not None:
                liveness.record_detection(now_ns)
            if monitor_extractor is not None:
                monitor_row = monitor_extractor.process_detection_tick(event)
                monitor_rows.append(monitor_row)
                for result in monitors.observe(monitor_row):
                    decisions.append(
                        {
                            "timestamp_ns": int(monitor_row["timestamp_ns"]),
                            **result,
                        }
                    )
        elif monitor_extractor is not None:
            monitor_extractor.update_trajectory_context(event)

        row = extractor.process_event(event)
        if row is not None:
            rows.append(row)

    if not rows:
        raise ValueError(f"{stream} contains no complete perception/planning ticks")
    timestamps = np.asarray([row["timestamp_ns"] for row in rows], dtype=np.int64)
    matrix = np.asarray(
        [[float(row[name]) for name in MODEL_FEATURE_NAMES] for row in rows], dtype=np.float64
    )
    scoring = score_feature_matrix(bundle, matrix, mode)
    scores = scoring["forest_scores"]
    threshold = float(scoring["forest_threshold"])
    predictions = scoring["predictions"]
    guardrail_scores = scoring["guardrail_scores"]
    guardrail_violations = scoring["guardrail_violations"]
    guardrail_threshold = float(scoring["guardrail_threshold"])
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))

    for timestamp, prediction in zip(timestamps, predictions, strict=True):
        decisions.append(
            {
                "timestamp_ns": int(timestamp),
                "path": "trajectory_hybrid",
                "anomalous": bool(prediction),
            }
        )

    active_any = np.zeros(len(timestamps), dtype=bool)
    recovery_window_ns = 500_000_000
    fault_reports = []
    for fault in ground_truth["faults"]:
        active = (timestamps >= fault["start_ns"]) & (timestamps < fault["end_ns"])
        active_any |= (timestamps >= fault["start_ns"]) & (
            timestamps < fault["end_ns"] + recovery_window_ns
        )
        active_decisions = [
            decision
            for decision in decisions
            if bool(decision["anomalous"])
            and int(fault["start_ns"]) <= int(decision["timestamp_ns"]) < int(fault["end_ns"])
        ]
        active_decisions.sort(key=lambda decision: int(decision["timestamp_ns"]))
        first_decision = active_decisions[0] if active_decisions else None
        first_detection_ns = (
            int(first_decision["timestamp_ns"]) if first_decision is not None else None
        )
        active_violations = guardrail_violations[active]
        triggered_features = [
            name
            for index, name in enumerate(GUARDRAIL_FEATURES)
            if active_violations.size and np.any(active_violations[:, index] > 0)
        ]
        fault_reports.append(
            {
                **fault,
                "scored_ticks": int(active.sum()),
                "anomalous_ticks": int((active & predictions).sum()),
                "anomalous_decisions": len(active_decisions),
                "detected": first_detection_ns is not None,
                "first_detection_ns": first_detection_ns,
                "first_decision_path": (
                    str(first_decision["path"]) if first_decision is not None else None
                ),
                "decision_paths": sorted(
                    {str(decision["path"]) for decision in active_decisions}
                ),
                "time_to_detect_ms": (
                    (first_detection_ns - fault["start_ns"]) / 1_000_000
                    if first_detection_ns is not None
                    else None
                ),
                "peak_score": float(scores[active].max()) if active.any() else None,
                "peak_guardrail_score": (
                    float(guardrail_scores[active].max()) if active.any() else None
                ),
                "guardrail_features": triggered_features,
            }
        )

    normal = ~active_any
    monitor_timestamps = np.asarray(
        [int(row["timestamp_ns"]) for row in monitor_rows], dtype=np.int64
    )
    monitor_normal = np.ones(len(monitor_rows), dtype=bool)
    for fault in ground_truth["faults"]:
        monitor_normal &= ~(
            (monitor_timestamps >= int(fault["start_ns"]))
            & (monitor_timestamps < int(fault["end_ns"]) + recovery_window_ns)
        )
    monitor_decisions = [
        decision
        for decision in decisions
        if str(decision["path"]) in {"confidence_health", "source_freshness"}
    ]
    monitor_by_timestamp_path = {
        (int(decision["timestamp_ns"]), str(decision["path"])): bool(decision["anomalous"])
        for decision in monitor_decisions
    }
    monitor_false_positives = 0
    monitor_path_false_positives: dict[str, int] = {
        "confidence_health": 0,
        "source_freshness": 0,
    }
    for timestamp, is_normal in zip(monitor_timestamps, monitor_normal, strict=True):
        if not is_normal:
            continue
        for path in monitor_path_false_positives:
            if monitor_by_timestamp_path.get((int(timestamp), path), False):
                monitor_false_positives += 1
                monitor_path_false_positives[path] += 1
    liveness_false_positives = sum(
        1
        for decision in decisions
        if str(decision["path"]) == "perception_liveness_timeout"
        and not any(
            int(fault["start_ns"]) <= int(decision["timestamp_ns"])
            < int(fault["end_ns"]) + recovery_window_ns
            for fault in ground_truth["faults"]
        )
    )
    normal_guardrail_trigger_counts = {
        name: int(np.sum(guardrail_violations[normal, index] > guardrail_threshold))
        for index, name in enumerate(GUARDRAIL_FEATURES)
    }
    core_false_positives = int((normal & predictions).sum())
    normal_decisions = int(normal.sum()) + int(monitor_normal.sum())
    false_positive_decisions = (
        core_false_positives + monitor_false_positives + liveness_false_positives
    )
    report = {
        "schema_version": 2,
        "model": str(model_path),
        "stream": str(stream),
        "detector_mode": mode,
        "threshold": threshold,
        "guardrail_threshold": guardrail_threshold,
        "tick_count": len(rows),
        "normal_ticks": normal_decisions,
        "hybrid_normal_ticks": int(normal.sum()),
        "monitor_normal_frames": int(monitor_normal.sum()),
        "recovery_window_ms": recovery_window_ns / 1_000_000,
        "false_positive_ticks": false_positive_decisions,
        "hybrid_false_positive_ticks": core_false_positives,
        "monitor_false_positive_frames": monitor_false_positives,
        "liveness_false_positive_timeouts": liveness_false_positives,
        "monitor_path_false_positives": monitor_path_false_positives,
        "false_positive_rate": float(false_positive_decisions / normal_decisions)
        if normal_decisions
        else 0.0,
        "score_min": float(scores.min()),
        "score_max": float(scores.max()),
        "guardrail_score_max": float(guardrail_scores.max()),
        "normal_guardrail_trigger_counts": normal_guardrail_trigger_counts,
        "safety_monitor_config": monitor_config,
        "faults": fault_reports,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
