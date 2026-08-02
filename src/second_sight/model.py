"""Isolation Forest training and fault-interval evaluation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from second_sight.features import FEATURE_NAMES, extract_features, read_feature_csv
from second_sight.stream import iter_events

EXPERIMENTAL_FEATURES = {
    "missing_near_object_count",
    "max_missing_near_object_ticks",
}
MODEL_FEATURE_NAMES = tuple(name for name in FEATURE_NAMES if name not in EXPERIMENTAL_FEATURES)

GUARDRAIL_FEATURES = (
    "object_count",
    "car_count",
    "pedestrian_count",
    "unknown_count",
    "mean_existence_probability",
    "min_existence_probability",
    "mean_classification_probability",
    "min_classification_probability",
    "mean_object_displacement_m",
    "max_object_displacement_m",
    "max_relative_object_displacement_m",
    "unmatched_previous_object_count",
    "unexpected_object_drop_count",
    "object_count_delta",
    "centroid_shift_m",
    "source_age_ms",
)
PERCEPTION_GUARDRAIL_FEATURES = tuple(
    name
    for name in GUARDRAIL_FEATURES
    if name
    not in {
        # This requires an accurate, same-tick ego pose. The fast path uses a
        # cached pose, so retain only the robust relative-motion feature below.
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
    ) -> None:
        self.bundle = joblib.load(model_path)
        self.mode = mode
        self.guardrail_features = guardrail_features
        # Validate once on construction instead of during a live decision.
        select_guardrail_violations(
            np.zeros((1, len(GUARDRAIL_FEATURES)), dtype=np.float64), guardrail_features
        )
        if self.bundle["metadata"]["feature_names"] != list(MODEL_FEATURE_NAMES):
            raise ValueError("model feature schema does not match this package")

    def score(self, row: dict[str, float | int]) -> dict[str, Any]:
        matrix = np.asarray([[float(row[name]) for name in MODEL_FEATURE_NAMES]], dtype=np.float64)
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

    rows = extract_features(iter_events(stream))
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

    active_any = np.zeros(len(timestamps), dtype=bool)
    recovery_window_ns = 500_000_000
    fault_reports = []
    for fault in ground_truth["faults"]:
        active = (timestamps >= fault["start_ns"]) & (timestamps < fault["end_ns"])
        active_any |= (timestamps >= fault["start_ns"]) & (
            timestamps < fault["end_ns"] + recovery_window_ns
        )
        detected_indices = np.flatnonzero(active & predictions)
        first_detection_ns = int(timestamps[detected_indices[0]]) if len(detected_indices) else None
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
                "detected": first_detection_ns is not None,
                "first_detection_ns": first_detection_ns,
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
    normal_guardrail_trigger_counts = {
        name: int(np.sum(guardrail_violations[normal, index] > guardrail_threshold))
        for index, name in enumerate(GUARDRAIL_FEATURES)
    }
    report = {
        "schema_version": 1,
        "model": str(model_path),
        "stream": str(stream),
        "detector_mode": mode,
        "threshold": threshold,
        "guardrail_threshold": guardrail_threshold,
        "tick_count": len(rows),
        "normal_ticks": int(normal.sum()),
        "recovery_window_ms": recovery_window_ns / 1_000_000,
        "false_positive_ticks": int((normal & predictions).sum()),
        "false_positive_rate": float((normal & predictions).sum() / normal.sum())
        if normal.any()
        else 0.0,
        "score_min": float(scores.min()),
        "score_max": float(scores.max()),
        "guardrail_score_max": float(guardrail_scores.max()),
        "normal_guardrail_trigger_counts": normal_guardrail_trigger_counts,
        "faults": fault_reports,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
