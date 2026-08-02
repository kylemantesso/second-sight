from pathlib import Path

import pytest

from second_sight.faults import FaultSpec, Scenario, inject_events, load_scenario


def detection(timestamp: int, x: float = 1.0) -> dict:
    return {
        "schema_version": 1,
        "kind": "detections",
        "timestamp_ns": timestamp,
        "recorded_ns": timestamp,
        "frame_id": "map",
        "objects": [
            {
                "existence_probability": 1.0,
                "classification": [{"label": 1, "probability": 1.0}],
                "position": {"x": x, "y": 2.0, "z": 0.0},
            }
        ],
    }


def scenario(fault_type: str, parameters: dict | None = None) -> Scenario:
    return Scenario(
        name=fault_type,
        seed=1,
        faults=(
            FaultSpec(
                id="fault",
                type=fault_type,
                start_seconds=1,
                duration_seconds=2,
                parameters=parameters or {},
            ),
        ),
    )


def source_events() -> list[dict]:
    return [detection(second * 1_000_000_000, float(second)) for second in range(4)]


def test_vanish() -> None:
    events, report = inject_events(source_events(), scenario("vanish", {"class_label": 1}))
    assert len(events[1]["objects"]) == 0
    assert len(events[2]["objects"]) == 0
    assert report["faults"][0]["modified_events"] == 2


def test_phantom() -> None:
    parameters = {"position": {"x": 10, "y": 20, "z": 0}, "class_label": 7}
    events, _ = inject_events(source_events(), scenario("phantom", parameters))
    assert len(events[1]["objects"]) == 2
    assert events[1]["objects"][-1]["classification"][0]["label"] == 7


def test_freeze_uses_last_clean_payload() -> None:
    events, _ = inject_events(source_events(), scenario("freeze"))
    assert events[1]["objects"] == events[0]["objects"]
    assert events[2]["objects"] == events[0]["objects"]
    assert events[2]["source_timestamp_ns"] == 0
    assert events[2]["timestamp_ns"] == 2_000_000_000


def test_freeze_at_start_uses_first_frame_as_baseline() -> None:
    zero_start = Scenario(
        name="freeze-at-start",
        seed=1,
        faults=(FaultSpec("fault", "freeze", 0, 2),),
    )
    events, report = inject_events(source_events(), zero_start)
    assert events[1]["objects"] == events[0]["objects"]
    assert events[1]["source_timestamp_ns"] == 0
    assert report["faults"][0]["modified_events"] == 1


def test_teleport() -> None:
    parameters = {"class_label": 1, "offset": {"x": 20, "y": -5}}
    events, _ = inject_events(source_events(), scenario("teleport", parameters))
    assert events[1]["objects"][0]["position"] == {"x": 21.0, "y": -3.0, "z": 0.0}


def test_confidence_collapse() -> None:
    events, _ = inject_events(source_events(), scenario("confidence_collapse", {"factor": 0.1}))
    assert events[1]["objects"][0]["existence_probability"] == pytest.approx(0.1)
    assert events[1]["objects"][0]["classification"][0]["probability"] == pytest.approx(0.1)


def test_liveness_drops_events_and_reports_ground_truth() -> None:
    events, report = inject_events(source_events(), scenario("liveness"))
    assert [event["timestamp_ns"] for event in events] == [0, 3_000_000_000]
    assert report["faults"][0]["dropped_events"] == 2
    assert report["faults"][0]["start_ns"] == 1_000_000_000
    assert report["faults"][0]["end_ns"] == 3_000_000_000


def test_load_scenario_rejects_duplicate_ids(tmp_path: Path) -> None:
    config = tmp_path / "scenario.yaml"
    config.write_text(
        """schema_version: 1
faults:
  - {id: duplicate, type: vanish, start_seconds: 0, duration_seconds: 1}
  - {id: duplicate, type: liveness, start_seconds: 1, duration_seconds: 1}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate fault id"):
        load_scenario(config)
