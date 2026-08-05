"""Aggregate no-leakage clean and injected-fault evaluation reports."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def summary_statistics(values: list[float]) -> dict[str, float]:
    """Return standard percentiles for one non-empty sample."""
    if not values:
        raise ValueError("cannot summarize an empty sample")
    sample = np.asarray(values, dtype=np.float64)
    return {
        "min": float(sample.min()),
        "p50": float(np.percentile(sample, 50)),
        "p95": float(np.percentile(sample, 95)),
        "p99": float(np.percentile(sample, 99)),
        "max": float(sample.max()),
    }


def read_evaluation(path: Path) -> dict[str, Any]:
    """Load one evaluation report and reject malformed required fields."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON") from error
    required = {"detector_mode", "normal_ticks", "false_positive_ticks", "faults"}
    missing = required.difference(report)
    if missing:
        raise ValueError(f"{path}: missing required fields: {sorted(missing)}")
    if int(report["normal_ticks"]) < 0 or int(report["false_positive_ticks"]) < 0:
        raise ValueError(f"{path}: normal and false-positive ticks must be non-negative")
    if not isinstance(report["faults"], list):
        raise ValueError(f"{path}: faults must be a list")
    return report


def aggregate_heldout_evaluations(
    clean_paths: list[Path], fault_paths: list[Path], output_path: Path
) -> dict[str, Any]:
    """Aggregate disjoint clean and injected-fault evaluation reports.

    The caller chooses non-overlapping training and hold-out cohorts. False
    positives are aggregated by ticks; fault detection is by held-out stream.
    """
    if not clean_paths:
        raise ValueError("at least one clean evaluation report is required")
    if not fault_paths:
        raise ValueError("at least one injected-fault evaluation report is required")

    clean_reports = [(path, read_evaluation(path)) for path in clean_paths]
    fault_reports = [(path, read_evaluation(path)) for path in fault_paths]
    detector_modes = {str(report["detector_mode"]) for _, report in clean_reports + fault_reports}
    if len(detector_modes) != 1:
        raise ValueError("all evaluation reports must use the same detector mode")
    if any(report["faults"] for _, report in clean_reports):
        raise ValueError("clean evaluation reports must not contain injected faults")

    evaluable_clean_reports = [
        (path, report) for path, report in clean_reports if int(report["normal_ticks"]) > 0
    ]
    normal_ticks = sum(int(report["normal_ticks"]) for _, report in evaluable_clean_reports)
    false_positive_ticks = sum(
        int(report["false_positive_ticks"]) for _, report in evaluable_clean_reports
    )
    if normal_ticks <= 0:
        raise ValueError("clean evaluation reports contain no normal ticks")

    fault_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path, report in fault_reports:
        if not report["faults"]:
            raise ValueError(f"{path}: injected-fault evaluation contains no fault reports")
        for fault in report["faults"]:
            try:
                fault_id = str(fault["id"])
                fault_type = str(fault["type"])
                detected = bool(fault["detected"])
                scored_ticks = int(fault["scored_ticks"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"{path}: malformed fault report") from error
            fault_groups[(fault_id, fault_type)].append(
                {
                    "evaluation_path": str(path),
                    "evaluable": scored_ticks > 0,
                    "detected": detected,
                    "time_to_detect_ms": (
                        float(fault["time_to_detect_ms"]) if detected else None
                    ),
                    "first_decision_path": (
                        str(fault["first_decision_path"])
                        if fault.get("first_decision_path") is not None
                        else None
                    ),
                    "decision_paths": [str(path) for path in fault.get("decision_paths", [])],
                }
            )

    faults = []
    for (fault_id, fault_type), runs in sorted(fault_groups.items()):
        evaluable = [run for run in runs if run["evaluable"]]
        detected = [run for run in evaluable if run["detected"]]
        timings = [float(run["time_to_detect_ms"]) for run in detected]
        first_path_counts: dict[str, int] = defaultdict(int)
        decision_path_counts: dict[str, int] = defaultdict(int)
        for run in detected:
            if run["first_decision_path"] is not None:
                first_path_counts[str(run["first_decision_path"])] += 1
            for path in run["decision_paths"]:
                decision_path_counts[path] += 1
        faults.append(
            {
                "id": fault_id,
                "type": fault_type,
                "candidate_run_count": len(runs),
                "evaluable_run_count": len(evaluable),
                "excluded_run_count": len(runs) - len(evaluable),
                "detected_runs": len(detected),
                "detection_rate": len(detected) / len(evaluable) if evaluable else None,
                "time_to_detect_ms": summary_statistics(timings) if timings else None,
                "first_decision_path_counts": dict(sorted(first_path_counts.items())),
                "decision_path_counts": dict(sorted(decision_path_counts.items())),
                "source_reports": [run["evaluation_path"] for run in runs],
            }
        )

    result = {
        "schema_version": 1,
        "kind": "heldout_configuration_validation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "detector_mode": detector_modes.pop(),
        "clean_cohort": {
            "report_count": len(clean_reports),
            "evaluable_report_count": len(evaluable_clean_reports),
            "excluded_report_count": len(clean_reports) - len(evaluable_clean_reports),
            "normal_ticks": normal_ticks,
            "false_positive_ticks": false_positive_ticks,
            "false_positive_rate": false_positive_ticks / normal_ticks,
            "source_reports": [str(path) for path, _ in clean_reports],
        },
        "injected_fault_cohort": {
            "report_count": len(fault_reports),
            "faults": faults,
            "source_reports": [str(path) for path, _ in fault_reports],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
