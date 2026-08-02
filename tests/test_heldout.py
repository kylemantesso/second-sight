import json
from pathlib import Path

from second_sight.heldout import aggregate_heldout_evaluations


def write_report(path: Path, *, normal: int, false_positives: int, faults: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "detector_mode": "hybrid",
                "normal_ticks": normal,
                "false_positive_ticks": false_positives,
                "faults": faults,
            }
        ),
        encoding="utf-8",
    )


def test_heldout_aggregation_reports_clean_fpr_and_detection_rate(tmp_path: Path) -> None:
    clean_one = tmp_path / "clean-one.json"
    clean_two = tmp_path / "clean-two.json"
    fault_one = tmp_path / "fault-one.json"
    fault_two = tmp_path / "fault-two.json"
    write_report(clean_one, normal=100, false_positives=1, faults=[])
    write_report(clean_two, normal=50, false_positives=2, faults=[])
    write_report(
        fault_one,
        normal=80,
        false_positives=0,
        faults=[
            {
                "id": "vanish",
                "type": "vanish",
                "scored_ticks": 10,
                "detected": True,
                "time_to_detect_ms": 4.0,
            }
        ],
    )
    write_report(
        fault_two,
        normal=80,
        false_positives=0,
        faults=[
            {
                "id": "vanish",
                "type": "vanish",
                "scored_ticks": 10,
                "detected": False,
                "time_to_detect_ms": None,
            }
        ],
    )

    output = tmp_path / "summary.json"
    report = aggregate_heldout_evaluations([clean_one, clean_two], [fault_one, fault_two], output)

    assert report["clean_cohort"]["normal_ticks"] == 150
    assert report["clean_cohort"]["false_positive_ticks"] == 3
    assert report["clean_cohort"]["false_positive_rate"] == 0.02
    fault = report["injected_fault_cohort"]["faults"][0]
    assert fault["detected_runs"] == 1
    assert fault["evaluable_run_count"] == 2
    assert fault["excluded_run_count"] == 0
    assert fault["detection_rate"] == 0.5
    assert fault["time_to_detect_ms"]["p50"] == 4.0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["kind"] == "heldout_configuration_validation"


def test_heldout_aggregation_excludes_unscored_fault_interval(tmp_path: Path) -> None:
    clean = tmp_path / "clean.json"
    fault = tmp_path / "fault.json"
    write_report(clean, normal=10, false_positives=0, faults=[])
    write_report(
        fault,
        normal=0,
        false_positives=0,
        faults=[
            {
                "id": "vanish",
                "type": "vanish",
                "scored_ticks": 0,
                "detected": False,
                "time_to_detect_ms": None,
            }
        ],
    )

    report = aggregate_heldout_evaluations([clean], [fault], tmp_path / "summary.json")
    result = report["injected_fault_cohort"]["faults"][0]
    assert result["evaluable_run_count"] == 0
    assert result["excluded_run_count"] == 1
    assert result["detection_rate"] is None
