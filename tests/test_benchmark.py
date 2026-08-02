import json
from pathlib import Path

from second_sight.benchmark import benchmark_model
from second_sight.features import extract_features, write_feature_csv
from second_sight.model import train_model


def detection(timestamp: int, x: float) -> dict:
    return {
        "schema_version": 1,
        "kind": "detections",
        "timestamp_ns": timestamp,
        "recorded_ns": timestamp,
        "frame_id": "map",
        "objects": [
            {
                "existence_probability": 0.9,
                "classification": [{"label": 1, "probability": 0.8}],
                "position": {"x": x, "y": 0.0, "z": 0.0},
            }
        ],
    }


def trajectory(timestamp: int) -> dict:
    point = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "longitudinal_velocity_mps": 2.0,
        "acceleration_mps2": 0.5,
    }
    return {
        "schema_version": 1,
        "kind": "trajectory",
        "timestamp_ns": timestamp,
        "recorded_ns": timestamp,
        "frame_id": "map",
        "points": [point, {**point, "position": {"x": 2.0, "y": 0.0, "z": 0.0}}],
    }


def test_benchmark_writes_host_and_latency_report(tmp_path: Path) -> None:
    events = [
        detection(0, 1.0),
        trajectory(50_000_000),
        detection(100_000_000, 2.0),
        trajectory(150_000_000),
        detection(200_000_000, 3.0),
        trajectory(250_000_000),
    ]
    stream = tmp_path / "stream.jsonl"
    stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    features = tmp_path / "features.csv"
    write_feature_csv(features, extract_features(events))
    model = tmp_path / "model.joblib"
    train_model([features], model, trees=5)

    output = tmp_path / "benchmark.json"
    report = benchmark_model(
        model, stream, output, warmup=2, samples=5, host_label="test-host"
    )

    assert report["sample_count"] == 5
    assert report["scoring_implementation"] == "optimized"
    assert report["host"]["label"] == "test-host"
    assert report["stream"]["feature_rows"] == 3
    assert report["model"]["bytes"] > 0
    assert report["inference_us"]["max"] >= report["inference_us"]["min"]
    assert json.loads(output.read_text(encoding="utf-8"))["kind"] == "inference_microbenchmark"
