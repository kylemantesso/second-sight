import json
from pathlib import Path

import numpy as np

from second_sight.faults import FaultSpec, Scenario, inject_file
from second_sight.features import FEATURE_NAMES, write_feature_csv
from second_sight.model import (
    GUARDRAIL_FEATURES,
    MODEL_FEATURE_NAMES,
    PERCEPTION_GUARDRAIL_FEATURES,
    SecondSightScorer,
    calibrate_model,
    learn_guardrails,
    score_guardrails,
    select_guardrail_violations,
    train_model,
)


def event(kind: str, timestamp_ns: int) -> dict:
    if kind == "detections":
        return {
            "schema_version": 1,
            "kind": kind,
            "timestamp_ns": timestamp_ns,
            "recorded_ns": timestamp_ns,
            "frame_id": "map",
            "objects": [
                {
                    "existence_probability": 0.9,
                    "classification": [{"label": 1, "probability": 0.8}],
                    "position": {"x": 5.0, "y": 0.0, "z": 0.0},
                }
            ],
        }
    point = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "longitudinal_velocity_mps": 2.0,
        "acceleration_mps2": 0.5,
    }
    return {
        "schema_version": 1,
        "kind": "trajectory",
        "timestamp_ns": timestamp_ns,
        "recorded_ns": timestamp_ns,
        "frame_id": "map",
        "points": [point, {**point, "position": {"x": 2.0, "y": 0.0, "z": 0.0}}],
    }


def write_stream(path: Path) -> None:
    events = []
    for tick in range(21):
        timestamp_ns = tick * 50_000_000
        events.append(event("trajectory", timestamp_ns))
        if tick % 2 == 0:
            events.append(event("detections", timestamp_ns))
    events.sort(key=lambda item: (item["timestamp_ns"], item["kind"] == "trajectory"))
    path.write_text("".join(json.dumps(item) + "\n" for item in events), encoding="utf-8")


def test_guardrails_accept_clean_values_and_flag_safety_feature_violations() -> None:
    clean = np.zeros((3, len(MODEL_FEATURE_NAMES)), dtype=np.float64)
    clean[:, MODEL_FEATURE_NAMES.index("source_age_ms")] = [10.0, 20.0, 30.0]
    clean[:, MODEL_FEATURE_NAMES.index("min_classification_probability")] = [0.8, 0.9, 1.0]
    bounds = learn_guardrails(clean)

    clean_scores, _ = score_guardrails(clean, bounds)
    assert clean_scores[1] == 0

    faulty = clean[:1].copy()
    faulty[0, MODEL_FEATURE_NAMES.index("source_age_ms")] = 1000.0
    faulty[0, MODEL_FEATURE_NAMES.index("min_classification_probability")] = 0.05
    scores, violations = score_guardrails(faulty, bounds)

    assert scores[0] > 0
    assert violations[0, GUARDRAIL_FEATURES.index("source_age_ms")] > 0
    assert violations[0, GUARDRAIL_FEATURES.index("min_classification_probability")] > 0


def test_fast_path_excludes_trajectory_dependent_guardrails() -> None:
    violations = np.zeros((1, len(GUARDRAIL_FEATURES)), dtype=np.float64)
    violations[0, GUARDRAIL_FEATURES.index("max_relative_object_displacement_m")] = 4.0
    violations[0, GUARDRAIL_FEATURES.index("object_count_delta")] = 2.0

    scores, selected = select_guardrail_violations(
        violations, ("object_count_delta", "source_age_ms")
    )

    assert scores.tolist() == [2.0]
    assert "max_relative_object_displacement_m" not in PERCEPTION_GUARDRAIL_FEATURES
    assert "unexpected_object_drop_count" not in PERCEPTION_GUARDRAIL_FEATURES
    assert selected.tolist() == [[2.0, 0.0]]


def test_optimized_guardrail_scorer_matches_reference_decisions(tmp_path: Path) -> None:
    clean = np.zeros((4, len(MODEL_FEATURE_NAMES)), dtype=np.float64)
    clean[:, MODEL_FEATURE_NAMES.index("source_age_ms")] = [10.0, 20.0, 30.0, 40.0]
    features = tmp_path / "clean.csv"
    write_feature_csv(
        features,
        [
            {
                "timestamp_ns": index,
                **{
                    name: (
                        float(row[MODEL_FEATURE_NAMES.index(name)])
                        if name in MODEL_FEATURE_NAMES
                        else 0.0
                    )
                    for name in FEATURE_NAMES
                },
            }
            for index, row in enumerate(clean)
        ],
    )
    model = tmp_path / "model.joblib"
    train_model([features], model, trees=5)
    reference = SecondSightScorer(model, "guardrails", implementation="reference")
    optimized = SecondSightScorer(model, "guardrails", implementation="optimized")

    for age in (10.0, 25.0, 1_000.0):
        row = {name: 0.0 for name in MODEL_FEATURE_NAMES}
        row["source_age_ms"] = age
        expected = reference.score(row)
        actual = optimized.score(row)
        assert actual["anomalous"] == expected["anomalous"]
        assert actual["guardrail_score"] == expected["guardrail_score"]
        assert actual["guardrail_features"] == expected["guardrail_features"]
        assert actual["forest_score"] is None


def test_calibration_freezes_validation_only_hybrid_thresholds(tmp_path: Path) -> None:
    def write_clean(path: Path, offset: float) -> None:
        rows = []
        for index in range(100):
            row = {name: 0.0 for name in FEATURE_NAMES}
            row["timestamp_ns"] = index
            row["source_age_ms"] = offset + index
            row["object_count"] = 1 + (index % 3)
            rows.append(row)
        write_feature_csv(path, rows)

    training = tmp_path / "training.csv"
    validation = tmp_path / "validation.csv"
    write_clean(training, 0.0)
    write_clean(validation, 10.0)
    source_model = tmp_path / "source.joblib"
    frozen_model = tmp_path / "frozen.joblib"
    train_model([training], source_model, trees=5)

    metadata = calibrate_model(
        source_model,
        [validation],
        frozen_model,
        target_clean_fpr=0.1,
        min_rows_per_dataset=50,
    )

    calibration = metadata["calibration"]
    assert frozen_model.exists()
    assert calibration["validation_datasets"] == [str(validation)]
    assert calibration["validation_rows"] == 100
    assert calibration["target_clean_fpr"] == 0.1
    assert calibration["observed_validation_false_positive_rate"] <= 0.1


def test_evaluation_reports_liveness_from_missing_detection_stream(tmp_path: Path) -> None:
    from second_sight.features import extract_features
    from second_sight.model import evaluate_model
    from second_sight.stream import iter_events

    clean_stream = tmp_path / "clean.jsonl"
    write_stream(clean_stream)
    features = tmp_path / "clean.csv"
    write_feature_csv(features, extract_features(iter_events(clean_stream)))
    source_model = tmp_path / "source.joblib"
    frozen_model = tmp_path / "frozen.joblib"
    train_model([features], source_model, trees=5)
    metadata = calibrate_model(
        source_model,
        [features],
        frozen_model,
        monitor_streams=[clean_stream],
    )
    assert metadata["calibration"]["monitor_calibration_source"] == "direct_detection_streams"
    assert metadata["safety_monitors"]["perception_liveness"]["timeout_ms"] == 300.0

    scenario = Scenario(
        name="liveness-test",
        seed=2026,
        faults=(FaultSpec("hang", "liveness", 0.3, 0.5),),
    )
    faulty_stream = tmp_path / "faulty.jsonl"
    ground_truth = tmp_path / "truth.json"
    inject_file(clean_stream, faulty_stream, ground_truth, scenario)
    report = evaluate_model(
        faulty_stream,
        frozen_model,
        ground_truth,
        tmp_path / "report.json",
        mode="hybrid",
    )

    fault = report["faults"][0]
    assert fault["detected"]
    assert "perception_liveness_timeout" in fault["decision_paths"]
