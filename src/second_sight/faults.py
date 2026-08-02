"""Deterministic fault injection for portable Second Sight event streams."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from second_sight.stream import event_time_ns, iter_events

FAULT_TYPES = {
    "vanish",
    "phantom",
    "freeze",
    "teleport",
    "confidence_collapse",
    "liveness",
}
TARGET_KINDS = {"detections", "trajectory", "all"}


@dataclass(frozen=True)
class FaultSpec:
    id: str
    type: str
    start_seconds: float
    duration_seconds: float
    target: str = "detections"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    faults: tuple[FaultSpec, ...]


@dataclass
class FaultStats:
    active_events: int = 0
    modified_events: int = 0
    dropped_events: int = 0


def load_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("scenario must use schema_version 1")

    faults = []
    seen_ids = set()
    for raw_fault in raw.get("faults", []):
        fault = FaultSpec(
            id=str(raw_fault["id"]),
            type=str(raw_fault["type"]),
            start_seconds=float(raw_fault["start_seconds"]),
            duration_seconds=float(raw_fault["duration_seconds"]),
            target=str(raw_fault.get("target", "detections")),
            parameters=dict(raw_fault.get("parameters", {})),
        )
        if fault.id in seen_ids:
            raise ValueError(f"duplicate fault id: {fault.id}")
        if fault.type not in FAULT_TYPES:
            raise ValueError(f"unsupported fault type: {fault.type}")
        if fault.target not in TARGET_KINDS:
            raise ValueError(f"unsupported target: {fault.target}")
        if fault.start_seconds < 0 or fault.duration_seconds <= 0:
            raise ValueError(
                f"fault {fault.id} must have a non-negative start and positive duration"
            )
        if fault.type not in {"freeze", "liveness"} and fault.target != "detections":
            raise ValueError(f"fault {fault.id} only supports the detections target")
        if fault.type == "freeze" and fault.target == "all":
            raise ValueError(f"fault {fault.id} must target detections or trajectory")
        seen_ids.add(fault.id)
        faults.append(fault)

    if not faults:
        raise ValueError("scenario must contain at least one fault")
    return Scenario(
        name=str(raw.get("name", path.stem)),
        seed=int(raw.get("seed", 0)),
        faults=tuple(faults),
    )


def targets(fault: FaultSpec, event: dict[str, Any]) -> bool:
    return fault.target == "all" or fault.target == event["kind"]


def object_label(detected_object: dict[str, Any]) -> int | None:
    classifications = detected_object.get("classification", [])
    if not classifications:
        return None
    return max(classifications, key=lambda item: item.get("probability", 0)).get("label")


def distance(position_a: dict[str, float], position_b: dict[str, float]) -> float:
    return math.sqrt(
        sum((position_a[axis] - position_b[axis]) ** 2 for axis in ("x", "y", "z"))
    )


def select_object(
    objects: list[dict[str, Any]], parameters: dict[str, Any], state: dict[str, Any]
) -> int | None:
    label = parameters.get("class_label")
    candidates = [
        index
        for index, detected_object in enumerate(objects)
        if label is None or object_label(detected_object) == label
    ]
    if not candidates:
        return None

    anchor = state.get("anchor_position")
    if anchor is None:
        candidate_index = int(parameters.get("object_index", 0))
        selected = candidates[min(candidate_index, len(candidates) - 1)]
    else:
        selected = min(candidates, key=lambda index: distance(objects[index]["position"], anchor))
    state["anchor_position"] = copy.deepcopy(objects[selected]["position"])
    return selected


def phantom_object(parameters: dict[str, Any]) -> dict[str, Any]:
    position = parameters.get("position")
    if not isinstance(position, dict) or not all(axis in position for axis in ("x", "y", "z")):
        raise ValueError("phantom fault requires parameters.position with x, y, and z")
    dimensions = parameters.get("dimensions", {"x": 0.8, "y": 0.8, "z": 1.8})
    return {
        "existence_probability": float(parameters.get("existence_probability", 1.0)),
        "classification": [
            {
                "label": int(parameters.get("class_label", 7)),
                "probability": float(parameters.get("classification_probability", 1.0)),
            }
        ],
        "position": {axis: float(position[axis]) for axis in ("x", "y", "z")},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "orientation_availability": 0,
        "linear_velocity": None,
        "angular_velocity": None,
        "shape": {
            "type": 0,
            "dimensions": {axis: float(dimensions[axis]) for axis in ("x", "y", "z")},
            "footprint": [],
        },
    }


def apply_fault(
    event: dict[str, Any], fault: FaultSpec, state: dict[str, Any]
) -> tuple[dict[str, Any] | None, bool, dict[str, Any]]:
    if fault.type == "liveness":
        return None, True, {}

    result = copy.deepcopy(event)
    details: dict[str, Any] = {}
    modified = False

    if fault.type == "vanish":
        selected = select_object(result.get("objects", []), fault.parameters, state)
        if selected is not None:
            removed = result["objects"].pop(selected)
            details = {"removed_index": selected, "removed_label": object_label(removed)}
            modified = True
    elif fault.type == "phantom":
        result.setdefault("objects", []).append(phantom_object(fault.parameters))
        details = {"inserted_index": len(result["objects"]) - 1}
        modified = True
    elif fault.type == "freeze":
        payload_key = "objects" if event["kind"] == "detections" else "points"
        snapshot = state.get("snapshot")
        if snapshot is None:
            snapshot = {
                "payload": copy.deepcopy(event.get(payload_key, [])),
                "frame_id": event.get("frame_id", ""),
                "timestamp_ns": event["timestamp_ns"],
            }
            state["snapshot"] = snapshot
        result[payload_key] = copy.deepcopy(snapshot["payload"])
        result["frame_id"] = snapshot["frame_id"]
        result["source_timestamp_ns"] = snapshot["timestamp_ns"]
        details = {"frozen_from_timestamp_ns": snapshot["timestamp_ns"]}
        modified = event["timestamp_ns"] != snapshot["timestamp_ns"]
    elif fault.type == "teleport":
        selected = select_object(result.get("objects", []), fault.parameters, state)
        if selected is not None:
            offset = fault.parameters.get("offset", {})
            for axis in ("x", "y", "z"):
                result["objects"][selected]["position"][axis] += float(offset.get(axis, 0.0))
            details = {"teleported_index": selected, "offset": offset}
            modified = True
    elif fault.type == "confidence_collapse":
        factor = float(fault.parameters.get("factor", 0.05))
        if not 0 <= factor <= 1:
            raise ValueError("confidence collapse factor must be between 0 and 1")
        selected_objects = result.get("objects", [])
        for detected_object in selected_objects:
            detected_object["existence_probability"] *= factor
            for classification in detected_object.get("classification", []):
                classification["probability"] *= factor
        details = {"factor": factor, "affected_objects": len(selected_objects)}
        modified = bool(selected_objects)

    return result, modified, details


class StreamingFaultInjector:
    """Apply a scenario incrementally while retaining deterministic fault state."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.timeline_start_ns: int | None = None
        self.timeline_end_ns: int | None = None
        self.states = {fault.id: {} for fault in scenario.faults}
        self.stats = {fault.id: FaultStats() for fault in scenario.faults}

    def reset(self) -> None:
        self.timeline_start_ns = None
        self.timeline_end_ns = None
        self.states = {fault.id: {} for fault in self.scenario.faults}
        self.stats = {fault.id: FaultStats() for fault in self.scenario.faults}

    def process(self, original_event: dict[str, Any]) -> dict[str, Any] | None:
        current_time_ns = event_time_ns(original_event)
        if self.timeline_start_ns is None:
            self.timeline_start_ns = current_time_ns
        self.timeline_end_ns = max(self.timeline_end_ns or current_time_ns, current_time_ns)
        relative_seconds = (current_time_ns - self.timeline_start_ns) / 1_000_000_000
        event: dict[str, Any] | None = original_event

        for fault in self.scenario.faults:
            if fault.type == "freeze" and targets(fault, original_event):
                start = fault.start_seconds
                if relative_seconds < start:
                    payload_key = "objects" if original_event["kind"] == "detections" else "points"
                    self.states[fault.id]["snapshot"] = {
                        "payload": copy.deepcopy(original_event.get(payload_key, [])),
                        "frame_id": original_event.get("frame_id", ""),
                        "timestamp_ns": original_event["timestamp_ns"],
                    }

            is_active = (
                fault.start_seconds
                <= relative_seconds
                < fault.start_seconds + fault.duration_seconds
            )
            if event is None or not is_active or not targets(fault, original_event):
                continue

            self.stats[fault.id].active_events += 1
            event, modified, details = apply_fault(event, fault, self.states[fault.id])
            if event is None:
                self.stats[fault.id].dropped_events += 1
                break
            if modified:
                self.stats[fault.id].modified_events += 1
            event.setdefault("faults", []).append(
                {
                    "id": fault.id,
                    "type": fault.type,
                    "modified": modified,
                    **details,
                }
            )
        return event

    def report(self, source: str = "") -> dict[str, Any]:
        if self.timeline_start_ns is None or self.timeline_end_ns is None:
            raise ValueError("cannot report an empty stream")
        return {
            "schema_version": 1,
            "scenario": self.scenario.name,
            "seed": self.scenario.seed,
            "source": source,
            "timeline_start_ns": self.timeline_start_ns,
            "timeline_end_ns": self.timeline_end_ns,
            "faults": [
                {
                    "id": fault.id,
                    "type": fault.type,
                    "target": fault.target,
                    "start_ns": self.timeline_start_ns
                    + round(fault.start_seconds * 1_000_000_000),
                    "end_ns": self.timeline_start_ns
                    + round((fault.start_seconds + fault.duration_seconds) * 1_000_000_000),
                    "active_events": self.stats[fault.id].active_events,
                    "modified_events": self.stats[fault.id].modified_events,
                    "dropped_events": self.stats[fault.id].dropped_events,
                }
                for fault in self.scenario.faults
            ],
        }


def inject_events(
    events: Iterable[dict[str, Any]], scenario: Scenario, source: str = ""
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    injector = StreamingFaultInjector(scenario)
    output_events = []
    for original_event in events:
        event = injector.process(original_event)
        if event is not None:
            output_events.append(event)
    if injector.timeline_start_ns is None:
        raise ValueError("cannot inject an empty stream")
    return output_events, injector.report(source)


def inject_file(
    source: Path, output: Path, ground_truth: Path, scenario: Scenario
) -> dict[str, Any]:
    events, report = inject_events(iter_events(source), scenario, str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, separators=(",", ":")) + "\n")
    ground_truth.parent.mkdir(parents=True, exist_ok=True)
    ground_truth.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
