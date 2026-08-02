from second_sight.features import FEATURE_NAMES, FeatureExtractor, extract_features


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


def empty_detection(timestamp: int) -> dict:
    return {
        "schema_version": 1,
        "kind": "detections",
        "timestamp_ns": timestamp,
        "recorded_ns": timestamp,
        "frame_id": "map",
        "objects": [],
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


def test_extracts_complete_feature_rows_and_detection_age() -> None:
    rows = extract_features(
        [
            detection(0, 1.0),
            trajectory(50_000_000),
            trajectory(150_000_000),
            detection(200_000_000, 2.0),
            trajectory(250_000_000),
        ]
    )
    assert len(rows) == 3
    assert set(rows[0]) == {"timestamp_ns", *FEATURE_NAMES}
    assert rows[0]["detection_age_ms"] == 50.0
    assert rows[1]["detection_age_ms"] == 150.0
    assert rows[2]["max_object_displacement_m"] == 1.0
    assert rows[2]["max_relative_object_displacement_m"] == 1.0
    assert rows[2]["trajectory_length_m"] == 2.0


def test_flags_object_drop_while_object_is_near_ego() -> None:
    rows = extract_features(
        [
            detection(0, 10.0),
            trajectory(50_000_000),
            empty_detection(100_000_000),
            trajectory(150_000_000),
        ]
    )
    assert rows[1]["unmatched_previous_object_count"] == 1.0
    assert rows[1]["unexpected_object_drop_count"] == 1.0
    assert rows[1]["missing_near_object_count"] == 1.0
    assert rows[1]["max_missing_near_object_ticks"] == 1.0


def test_detection_tick_builds_row_without_waiting_for_trajectory() -> None:
    extractor = FeatureExtractor()

    assert extractor.process_detection_tick(detection(0, 10.0)) is None
    extractor.update_trajectory_context(trajectory(50_000_000))
    baseline = extractor.process_detection_tick(detection(100_000_000, 10.0))
    second = extractor.process_detection_tick(empty_detection(200_000_000))

    assert baseline is not None
    assert second is not None
    assert second["trajectory_point_count"] > 0.0
    assert second["unmatched_previous_object_count"] == 1.0
    assert second["object_count_delta"] == -1.0
