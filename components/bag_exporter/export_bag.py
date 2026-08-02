#!/usr/bin/env python3
"""Export selected Autoware bag messages to the portable Second Sight stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

DETECTIONS_TOPIC = "/perception/object_recognition/detection/objects"
TRAJECTORY_TOPIC = "/planning/scenario_planning/trajectory"
SELECTED_TOPICS = {DETECTIONS_TOPIC, TRAJECTORY_TOPIC}
SCHEMA_VERSION = 1


def vector(vector_message: Any) -> dict[str, float]:
    return {"x": vector_message.x, "y": vector_message.y, "z": vector_message.z}


def quaternion(quaternion_message: Any) -> dict[str, float]:
    return {
        "x": quaternion_message.x,
        "y": quaternion_message.y,
        "z": quaternion_message.z,
        "w": quaternion_message.w,
    }


def header_timestamp_ns(message: Any, recorded_ns: int) -> int:
    stamp = message.header.stamp
    timestamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
    return timestamp_ns or recorded_ns


def base_event(message: Any, recorded_ns: int, kind: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "timestamp_ns": header_timestamp_ns(message, recorded_ns),
        "recorded_ns": recorded_ns,
        "frame_id": message.header.frame_id,
    }


def detection_event(message: Any, recorded_ns: int) -> dict[str, Any]:
    event = base_event(message, recorded_ns, "detections")
    event["objects"] = []
    for detected_object in message.objects:
        kinematics = detected_object.kinematics
        pose = kinematics.pose_with_covariance.pose
        linear_velocity = None
        angular_velocity = None
        if kinematics.has_twist:
            twist = kinematics.twist_with_covariance.twist
            linear_velocity = vector(twist.linear)
            angular_velocity = vector(twist.angular)

        event["objects"].append(
            {
                "existence_probability": detected_object.existence_probability,
                "classification": [
                    {"label": classification.label, "probability": classification.probability}
                    for classification in detected_object.classification
                ],
                "position": vector(pose.position),
                "orientation": quaternion(pose.orientation),
                "orientation_availability": kinematics.orientation_availability,
                "linear_velocity": linear_velocity,
                "angular_velocity": angular_velocity,
                "shape": {
                    "type": detected_object.shape.type,
                    "dimensions": vector(detected_object.shape.dimensions),
                    "footprint": [
                        vector(point) for point in detected_object.shape.footprint.points
                    ],
                },
            }
        )
    return event


def trajectory_event(message: Any, recorded_ns: int) -> dict[str, Any]:
    event = base_event(message, recorded_ns, "trajectory")
    event["points"] = [
        {
            "time_from_start_ns": (
                point.time_from_start.sec * 1_000_000_000 + point.time_from_start.nanosec
            ),
            "position": vector(point.pose.position),
            "orientation": quaternion(point.pose.orientation),
            "longitudinal_velocity_mps": point.longitudinal_velocity_mps,
            "lateral_velocity_mps": point.lateral_velocity_mps,
            "acceleration_mps2": point.acceleration_mps2,
            "heading_rate_rps": point.heading_rate_rps,
            "front_wheel_angle_rad": point.front_wheel_angle_rad,
            "rear_wheel_angle_rad": point.rear_wheel_angle_rad,
        }
        for point in message.points
    ]
    return event


def export_bag(bag_path: Path, output_path: Path) -> tuple[int, dict[str, int]]:
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions(
            input_serialization_format="cdr", output_serialization_format="cdr"
        ),
    )
    topic_types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    missing_topics = SELECTED_TOPICS - topic_types.keys()
    if missing_topics:
        missing = ", ".join(sorted(missing_topics))
        raise RuntimeError(f"bag does not contain required topics: {missing}")

    message_types = {topic: get_message(topic_types[topic]) for topic in SELECTED_TOPICS}
    counts = {topic: 0 for topic in SELECTED_TOPICS}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        while reader.has_next():
            topic, serialized, recorded_ns = reader.read_next()
            if topic not in SELECTED_TOPICS:
                continue
            message = deserialize_message(serialized, message_types[topic])
            if topic == DETECTIONS_TOPIC:
                event = detection_event(message, recorded_ns)
            else:
                event = trajectory_event(message, recorded_ns)
            output.write(json.dumps(event, separators=(",", ":")) + "\n")
            counts[topic] += 1

    empty_topics = [topic for topic, count in counts.items() if count == 0]
    if empty_topics:
        output_path.unlink(missing_ok=True)
        missing = ", ".join(sorted(empty_topics))
        raise RuntimeError(f"bag contains no messages for required topics: {missing}")
    return sum(counts.values()), counts


def valid_export(path: Path) -> bool:
    kinds = set()
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                kinds.add(json.loads(line)["kind"])
                if kinds == {"detections", "trajectory"}:
                    return True
    except (OSError, ValueError, KeyError):
        return False
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bags", type=Path, nargs="+")
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument("--output", type=Path)
    output_group.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--skip-invalid", action="store_true")
    args = parser.parse_args()

    if args.output is not None and len(args.bags) != 1:
        parser.error("--output can only be used with one bag")

    exported = 0
    skipped = 0
    invalid = 0
    for bag in args.bags:
        output = args.output or args.output_dir / f"{bag.name}.jsonl"
        if args.skip_existing and output.exists() and valid_export(output):
            print(f"Skipping existing stream: {output}")
            skipped += 1
            continue
        try:
            total, counts = export_bag(bag, output)
        except RuntimeError as error:
            if not args.skip_invalid:
                raise
            output.unlink(missing_ok=True)
            print(f"Skipping invalid bag {bag}: {error}")
            invalid += 1
            continue
        print(f"Exported {total} events to {output}")
        for topic, count in sorted(counts.items()):
            print(f"{topic}: {count}")
        exported += 1
    print(f"Completed: {exported} exported, {skipped} existing, {invalid} invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
