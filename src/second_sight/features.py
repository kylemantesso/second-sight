"""Convert portable perception and trajectory events into per-tick features."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from second_sight.stream import event_time_ns

FEATURE_NAMES = (
    "object_count",
    "car_count",
    "pedestrian_count",
    "unknown_count",
    "mean_existence_probability",
    "min_existence_probability",
    "mean_classification_probability",
    "min_classification_probability",
    "mean_object_distance_m",
    "min_object_distance_m",
    "mean_object_displacement_m",
    "max_object_displacement_m",
    "mean_relative_object_displacement_m",
    "max_relative_object_displacement_m",
    "unmatched_previous_object_count",
    "unexpected_object_drop_count",
    "missing_near_object_count",
    "max_missing_near_object_ticks",
    "object_count_delta",
    "centroid_shift_m",
    "detection_age_ms",
    "source_age_ms",
    "detection_gap_ms",
    "trajectory_point_count",
    "trajectory_length_m",
    "trajectory_direct_distance_m",
    "trajectory_mean_speed_mps",
    "trajectory_speed_std_mps",
    "trajectory_max_acceleration_mps2",
    "trajectory_mean_heading_change_rad",
    "trajectory_max_heading_change_rad",
    "trajectory_mean_curvature",
)


def vector_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(sum((a[axis] - b[axis]) ** 2 for axis in ("x", "y", "z")))


def primary_class(detected_object: dict[str, Any]) -> tuple[int, float]:
    classifications = detected_object.get("classification", [])
    if not classifications:
        return 0, 0.0
    primary = max(classifications, key=lambda item: item.get("probability", 0.0))
    return int(primary.get("label", 0)), float(primary.get("probability", 0.0))


def centroid(objects: list[dict[str, Any]]) -> dict[str, float] | None:
    if not objects:
        return None
    return {
        axis: fmean(detected_object["position"][axis] for detected_object in objects)
        for axis in ("x", "y", "z")
    }


def match_object_changes(
    current: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> tuple[list[float], set[int]]:
    unmatched = set(range(len(previous)))
    displacements = []
    for detected_object in current:
        label, _ = primary_class(detected_object)
        candidates = [
            index for index in unmatched if primary_class(previous[index])[0] == label
        ]
        if not candidates:
            continue
        match = min(
            candidates,
            key=lambda index: vector_distance(
                detected_object["position"], previous[index]["position"]
            ),
        )
        unmatched.remove(match)
        displacements.append(
            vector_distance(detected_object["position"], previous[match]["position"])
        )
    return displacements, unmatched


def match_displacements(
    current: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> list[float]:
    return match_object_changes(current, previous)[0]


def relative_objects(
    objects: list[dict[str, Any]], ego_position: dict[str, float]
) -> list[dict[str, Any]]:
    return [
        {
            "classification": detected_object.get("classification", []),
            "position": {
                axis: detected_object["position"][axis] - ego_position[axis]
                for axis in ("x", "y", "z")
            },
        }
        for detected_object in objects
    ]


def quaternion_yaw(orientation: dict[str, float]) -> float:
    x = orientation["x"]
    y = orientation["y"]
    z = orientation["z"]
    w = orientation["w"]
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def angle_difference(a: float, b: float) -> float:
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def trajectory_features(points: list[dict[str, Any]]) -> dict[str, float]:
    segments = [
        vector_distance(previous["position"], current["position"])
        for previous, current in zip(points, points[1:], strict=False)
    ]
    heading_changes = [
        angle_difference(
            quaternion_yaw(previous["orientation"]), quaternion_yaw(current["orientation"])
        )
        for previous, current in zip(points, points[1:], strict=False)
    ]
    curvatures = [
        heading_change / segment
        for heading_change, segment in zip(heading_changes, segments, strict=False)
        if segment > 1e-6
    ]
    speeds = [abs(float(point["longitudinal_velocity_mps"])) for point in points]
    accelerations = [abs(float(point["acceleration_mps2"])) for point in points]
    direct_distance = (
        vector_distance(points[0]["position"], points[-1]["position"]) if points else 0.0
    )
    return {
        "trajectory_point_count": float(len(points)),
        "trajectory_length_m": sum(segments),
        "trajectory_direct_distance_m": direct_distance,
        "trajectory_mean_speed_mps": fmean(speeds) if speeds else 0.0,
        "trajectory_speed_std_mps": pstdev(speeds) if len(speeds) > 1 else 0.0,
        "trajectory_max_acceleration_mps2": max(accelerations, default=0.0),
        "trajectory_mean_heading_change_rad": fmean(heading_changes) if heading_changes else 0.0,
        "trajectory_max_heading_change_rad": max(heading_changes, default=0.0),
        "trajectory_mean_curvature": fmean(curvatures) if curvatures else 0.0,
    }


def detection_features(
    detection: dict[str, Any],
    previous_objects: list[dict[str, Any]],
    previous_count: int,
    previous_detection_time_ns: int | None,
    previous_ego_position: dict[str, float],
    tick: dict[str, Any],
) -> dict[str, float]:
    objects = detection.get("objects", [])
    labels_and_probabilities = [primary_class(detected_object) for detected_object in objects]
    existence = [float(item.get("existence_probability", 0.0)) for item in objects]
    classification = [probability for _, probability in labels_and_probabilities]
    ego_position = (
        tick["points"][0]["position"] if tick.get("points") else {"x": 0.0, "y": 0.0, "z": 0.0}
    )
    distances = [vector_distance(item["position"], ego_position) for item in objects]
    displacements, unmatched_previous = match_object_changes(objects, previous_objects)
    relative_displacements = match_displacements(
        relative_objects(objects, ego_position),
        relative_objects(previous_objects, previous_ego_position),
    )
    current_centroid = centroid(objects)
    previous_centroid = centroid(previous_objects)
    detection_time_ns = event_time_ns(detection)
    source_timestamp_ns = detection.get("source_timestamp_ns", detection["timestamp_ns"])
    tick_time_ns = event_time_ns(tick)
    tick_source_ns = tick["timestamp_ns"]
    unexpected_drops = sum(
        vector_distance(previous_objects[index]["position"], previous_ego_position) < 80.0
        for index in unmatched_previous
    )

    return {
        "object_count": float(len(objects)),
        "car_count": float(sum(label == 1 for label, _ in labels_and_probabilities)),
        "pedestrian_count": float(sum(label == 7 for label, _ in labels_and_probabilities)),
        "unknown_count": float(sum(label == 0 for label, _ in labels_and_probabilities)),
        "mean_existence_probability": fmean(existence) if existence else 0.0,
        "min_existence_probability": min(existence, default=0.0),
        "mean_classification_probability": fmean(classification) if classification else 0.0,
        "min_classification_probability": min(classification, default=0.0),
        "mean_object_distance_m": fmean(distances) if distances else 0.0,
        "min_object_distance_m": min(distances, default=0.0),
        "mean_object_displacement_m": fmean(displacements) if displacements else 0.0,
        "max_object_displacement_m": max(displacements, default=0.0),
        "mean_relative_object_displacement_m": (
            fmean(relative_displacements) if relative_displacements else 0.0
        ),
        "max_relative_object_displacement_m": max(relative_displacements, default=0.0),
        "unmatched_previous_object_count": float(len(unmatched_previous)),
        "unexpected_object_drop_count": float(unexpected_drops),
        "object_count_delta": float(len(objects) - previous_count),
        "centroid_shift_m": (
            vector_distance(current_centroid, previous_centroid)
            if current_centroid is not None and previous_centroid is not None
            else 0.0
        ),
        "detection_age_ms": max(0.0, (tick_time_ns - detection_time_ns) / 1_000_000),
        "source_age_ms": max(0.0, (tick_source_ns - source_timestamp_ns) / 1_000_000),
        "detection_gap_ms": (
            (detection_time_ns - previous_detection_time_ns) / 1_000_000
            if previous_detection_time_ns is not None
            else 0.0
        ),
    }


@dataclass
class ObjectTrack:
    label: int
    position: dict[str, float]
    missing_ticks: int = 0


class FeatureExtractor:
    """Stateful event-to-feature converter shared by replay and live nodes."""

    def __init__(self) -> None:
        self.latest_detection: dict[str, Any] | None = None
        self.previous_tick_objects: list[dict[str, Any]] = []
        self.previous_count = 0
        self.previous_detection_time_ns: int | None = None
        self.last_used_detection_time_ns: int | None = None
        self.previous_tick_ego_position: dict[str, float] | None = None
        self.latest_ego_position: dict[str, float] | None = None
        self.tracks: list[ObjectTrack] = []
        self.tick_count = 0

    def update_tracks(self, objects: list[dict[str, Any]]) -> None:
        unmatched_tracks = set(range(len(self.tracks)))
        for detected_object in objects:
            label, _ = primary_class(detected_object)
            candidates = [index for index in unmatched_tracks if self.tracks[index].label == label]
            match = None
            if candidates:
                nearest = min(
                    candidates,
                    key=lambda index: vector_distance(
                        detected_object["position"], self.tracks[index].position
                    ),
                )
                if vector_distance(detected_object["position"], self.tracks[nearest].position) < 10:
                    match = nearest
            if match is None:
                self.tracks.append(
                    ObjectTrack(label=label, position=dict(detected_object["position"]))
                )
            else:
                unmatched_tracks.remove(match)
                self.tracks[match].position = dict(detected_object["position"])
                self.tracks[match].missing_ticks = 0

        retained_tracks = []
        for index, track in enumerate(self.tracks):
            if index in unmatched_tracks:
                track.missing_ticks += 1
            distance_from_ego = (
                vector_distance(track.position, self.latest_ego_position)
                if self.latest_ego_position is not None
                else 0.0
            )
            if track.missing_ticks == 0 or (track.missing_ticks <= 50 and distance_from_ego < 80):
                retained_tracks.append(track)
        self.tracks = retained_tracks

    def process_event(self, event: dict[str, Any]) -> dict[str, float | int] | None:
        if event["kind"] == "detections":
            self.latest_detection = event
            self.update_tracks(event.get("objects", []))
            return None
        if self.latest_detection is None:
            return None

        detection_time_ns = event_time_ns(self.latest_detection)
        current_objects = self.latest_detection.get("objects", [])
        current_ego_position = (
            event["points"][0]["position"]
            if event.get("points")
            else {"x": 0.0, "y": 0.0, "z": 0.0}
        )
        self.latest_ego_position = current_ego_position
        baseline_objects = self.previous_tick_objects if self.tick_count else current_objects
        baseline_count = self.previous_count if self.tick_count else len(current_objects)
        baseline_ego_position = self.previous_tick_ego_position or current_ego_position
        missing_near_tracks = [
            track
            for track in self.tracks
            if track.missing_ticks > 0
            and vector_distance(track.position, current_ego_position) < 80
        ]
        row: dict[str, float | int] = {
            "timestamp_ns": event_time_ns(event),
            **detection_features(
                self.latest_detection,
                baseline_objects,
                baseline_count,
                self.previous_detection_time_ns,
                baseline_ego_position,
                event,
            ),
            "missing_near_object_count": float(len(missing_near_tracks)),
            "max_missing_near_object_ticks": float(
                max((track.missing_ticks for track in missing_near_tracks), default=0)
            ),
            **trajectory_features(event.get("points", [])),
        }
        self.previous_tick_objects = current_objects
        self.previous_count = len(current_objects)
        self.previous_tick_ego_position = current_ego_position
        if detection_time_ns != self.last_used_detection_time_ns:
            self.previous_detection_time_ns = detection_time_ns
            self.last_used_detection_time_ns = detection_time_ns
        self.tick_count += 1
        return row


def extract_features(events: Iterable[dict[str, Any]]) -> list[dict[str, float | int]]:
    extractor = FeatureExtractor()
    rows = []
    for event in events:
        row = extractor.process_event(event)
        if row is not None:
            rows.append(row)

    return rows


def write_feature_csv(path: Path, rows: list[dict[str, float | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("timestamp_ns", *FEATURE_NAMES))
        writer.writeheader()
        writer.writerows(rows)


def read_feature_csv(path: Path) -> tuple[list[int], list[list[float]]]:
    timestamps = []
    values = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["timestamp_ns", *FEATURE_NAMES]:
            raise ValueError(f"{path} does not match feature schema")
        for row in reader:
            timestamps.append(int(row["timestamp_ns"]))
            values.append([float(row[name]) for name in FEATURE_NAMES])
    if not values:
        raise ValueError(f"{path} contains no feature rows")
    return timestamps, values


def valid_feature_csv(path: Path) -> bool:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            return next(csv.reader(stream), None) == ["timestamp_ns", *FEATURE_NAMES]
    except OSError:
        return False
