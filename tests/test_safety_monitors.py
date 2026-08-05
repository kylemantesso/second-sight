from second_sight.safety_monitors import DetectionSafetyMonitors, monitor_config_from_metadata


def config() -> dict:
    return {
        "schema_version": 1,
        "confidence_health": {
            "mean_existence_floor": 0.4,
            "mean_classification_floor": 0.5,
            "consecutive_frames": 2,
        },
        "source_freshness": {"max_source_age_ms": 20.0, "consecutive_frames": 2},
        "perception_liveness": {"timeout_ms": 300.0},
    }


def row(**overrides: float) -> dict[str, float]:
    result = {
        "object_count": 1.0,
        "mean_existence_probability": 0.9,
        "mean_classification_probability": 0.8,
        "source_age_ms": 1.0,
    }
    result.update(overrides)
    return result


def test_confidence_health_requires_two_low_object_bearing_frames() -> None:
    monitors = DetectionSafetyMonitors(config())

    low_confidence = row(mean_existence_probability=0.1, mean_classification_probability=0.2)
    first = monitors.observe(low_confidence)
    second = monitors.observe(low_confidence)
    cleared = monitors.observe(row(object_count=0.0))

    assert not first[0]["anomalous"]
    assert first[0]["consecutive_anomalies"] == 1
    assert second[0]["anomalous"]
    assert second[0]["consecutive_anomalies"] == 2
    assert not cleared[0]["anomalous"]
    assert cleared[0]["consecutive_anomalies"] == 0


def test_source_freshness_requires_two_stale_frames() -> None:
    monitors = DetectionSafetyMonitors(config())

    first = monitors.observe(row(source_age_ms=21.0))
    second = monitors.observe(row(source_age_ms=22.0))
    fresh = monitors.observe(row(source_age_ms=1.0))

    assert not first[1]["anomalous"]
    assert second[1]["anomalous"]
    assert not fresh[1]["anomalous"]
    assert fresh[1]["consecutive_anomalies"] == 0


def test_metadata_validation_accepts_v2_monitor_config() -> None:
    assert monitor_config_from_metadata({"safety_monitors": config()}) == config()
