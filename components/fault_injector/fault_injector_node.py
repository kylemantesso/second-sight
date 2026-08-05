#!/usr/bin/env python3
"""Live deterministic fault injector for Autoware detection messages."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import rclpy
from autoware_perception_msgs.msg import DetectedObject, DetectedObjects, ObjectClassification
from geometry_msgs.msg import Point32
from rclpy.node import Node
from std_msgs.msg import Bool, Int64, String

from second_sight.faults import FaultSpec, Scenario, StreamingFaultInjector, load_scenario


def vector(message: Any) -> dict[str, float]:
    return {"x": message.x, "y": message.y, "z": message.z}


def quaternion(message: Any) -> dict[str, float]:
    return {"x": message.x, "y": message.y, "z": message.z, "w": message.w}


def assign_vector(message: Any, values: dict[str, float]) -> None:
    message.x = values["x"]
    message.y = values["y"]
    message.z = values["z"]


def assign_quaternion(message: Any, values: dict[str, float]) -> None:
    assign_vector(message, values)
    message.w = values["w"]


def stamp_ns(message: DetectedObjects) -> int:
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec


def detection_event(message: DetectedObjects, recorded_ns: int) -> dict[str, Any]:
    objects = []
    for detected_object in message.objects:
        kinematics = detected_object.kinematics
        pose = kinematics.pose_with_covariance.pose
        twist = kinematics.twist_with_covariance.twist if kinematics.has_twist else None
        objects.append(
            {
                "existence_probability": detected_object.existence_probability,
                "classification": [
                    {"label": item.label, "probability": item.probability}
                    for item in detected_object.classification
                ],
                "position": vector(pose.position),
                "orientation": quaternion(pose.orientation),
                "orientation_availability": kinematics.orientation_availability,
                "linear_velocity": vector(twist.linear) if twist else None,
                "angular_velocity": vector(twist.angular) if twist else None,
                "shape": {
                    "type": detected_object.shape.type,
                    "dimensions": vector(detected_object.shape.dimensions),
                    "footprint": [
                        vector(point) for point in detected_object.shape.footprint.points
                    ],
                },
            }
        )
    return {
        "schema_version": 1,
        "kind": "detections",
        "timestamp_ns": stamp_ns(message) or recorded_ns,
        "recorded_ns": recorded_ns,
        "frame_id": message.header.frame_id,
        "objects": objects,
    }


def detection_message(event: dict[str, Any]) -> DetectedObjects:
    message = DetectedObjects()
    source_timestamp_ns = event.get("source_timestamp_ns", event["timestamp_ns"])
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(
        source_timestamp_ns, 1_000_000_000
    )
    message.header.frame_id = event.get("frame_id", "map")
    for source in event.get("objects", []):
        detected_object = DetectedObject()
        detected_object.existence_probability = source["existence_probability"]
        for source_classification in source.get("classification", []):
            classification = ObjectClassification()
            classification.label = source_classification["label"]
            classification.probability = source_classification["probability"]
            detected_object.classification.append(classification)
        kinematics = detected_object.kinematics
        assign_vector(kinematics.pose_with_covariance.pose.position, source["position"])
        assign_quaternion(kinematics.pose_with_covariance.pose.orientation, source["orientation"])
        kinematics.orientation_availability = source["orientation_availability"]
        if source.get("linear_velocity") is not None:
            kinematics.has_twist = True
            assign_vector(
                kinematics.twist_with_covariance.twist.linear, source["linear_velocity"]
            )
            assign_vector(
                kinematics.twist_with_covariance.twist.angular, source["angular_velocity"]
            )
        detected_object.shape.type = source["shape"]["type"]
        assign_vector(detected_object.shape.dimensions, source["shape"]["dimensions"])
        for source_point in source["shape"].get("footprint", []):
            point = Point32()
            assign_vector(point, source_point)
            detected_object.shape.footprint.points.append(point)
        message.objects.append(detected_object)
    return message


class FaultInjectorNode(Node):
    def __init__(
        self,
        scenario_path: Path,
        input_topic: str,
        output_topic: str,
        reset_gap_seconds: float,
        manual_control: bool,
        control_topic: str,
        manual_duration_ms: int,
    ) -> None:
        super().__init__("second_sight_fault_injector")
        self.engine = StreamingFaultInjector(load_scenario(scenario_path))
        self.reset_gap_ns = round(reset_gap_seconds * 1_000_000_000)
        self.last_detection_ns: int | None = None
        self.manual_control = manual_control
        self.control_topic = control_topic
        self.manual_duration_ms = manual_duration_ms
        self.manual_templates = {fault.type: fault for fault in self.engine.scenario.faults}
        self.manual_engine: StreamingFaultInjector | None = None
        self.manual_fault: FaultSpec | None = None
        self.manual_expires_monotonic_ns: int | None = None
        self.pending_manual_fault_type: str | None = None
        self.pending_manual_duration_ms: int | None = None
        self.publisher = self.create_publisher(DetectedObjects, output_topic, 10)
        self.active_publisher = self.create_publisher(Bool, "/second_sight/fault/active", 10)
        self.type_publisher = self.create_publisher(String, "/second_sight/fault/type", 10)
        self.event_publisher = self.create_publisher(String, "/second_sight/fault/event", 10)
        self.measurement_publisher = self.create_publisher(
            String, "/second_sight/latency/fault_injected", 10
        )
        self.timestamp_publisher = self.create_publisher(
            Int64, "/second_sight/fault/timestamp_ns", 10
        )
        self.create_subscription(DetectedObjects, input_topic, self.on_detection, 10)
        if manual_control:
            self.create_subscription(String, control_topic, self.on_manual_command, 10)
        self.get_logger().info(
            f"fault injector ready: scenario={self.engine.scenario.name}, "
            f"input={input_topic}, output={output_topic}, "
            f"manual_control={'enabled' if manual_control else 'disabled'}"
        )

    def on_manual_command(self, message: String) -> None:
        """Handle a dashboard fault request or an explicit demo reset."""
        try:
            payload = json.loads(message.data)
            if not isinstance(payload, dict):
                raise ValueError("command must be a JSON object")
            if payload.get("action") == "reset":
                self.engine.reset()
                self.clear_manual_fault()
                self.pending_manual_fault_type = None
                self.pending_manual_duration_ms = None
                self.publish_active_faults([], self.get_clock().now().nanoseconds)
                self.get_logger().info("reset manual dashboard fault state")
                return
            if self.manual_engine is not None or self.pending_manual_fault_type is not None:
                self.get_logger().warning(
                    "ignoring dashboard fault command while another fault is active"
                )
                return
            fault_type = str(payload["fault_type"])
            duration_ms = int(payload.get("duration_ms", self.manual_duration_ms))
            if fault_type not in self.manual_templates:
                raise ValueError(f"unsupported fault_type {fault_type!r}")
            if not 100 <= duration_ms <= 10_000:
                raise ValueError("duration_ms must be between 100 and 10000")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().warning(f"ignoring invalid dashboard fault command: {error}")
            return
        self.pending_manual_fault_type = fault_type
        self.pending_manual_duration_ms = duration_ms
        self.get_logger().info(
            f"queued manual {fault_type} fault for {duration_ms}ms from {self.control_topic}"
        )

    def start_manual_fault(self) -> None:
        """Create a single-fault engine with dashboard-controlled wall-clock duration."""
        assert self.pending_manual_fault_type is not None
        assert self.pending_manual_duration_ms is not None
        template = self.manual_templates[self.pending_manual_fault_type]
        self.manual_fault = replace(
            template,
            id=f"manual-{template.id}",
            start_seconds=0.0,
            duration_seconds=3600.0,
        )
        self.manual_engine = StreamingFaultInjector(
            Scenario(
                name=f"manual-{self.engine.scenario.name}",
                seed=self.engine.scenario.seed,
                faults=(self.manual_fault,),
            )
        )
        self.manual_expires_monotonic_ns = (
            time.monotonic_ns() + self.pending_manual_duration_ms * 1_000_000
        )
        self.pending_manual_fault_type = None
        self.pending_manual_duration_ms = None

    def clear_manual_fault(self) -> None:
        self.manual_engine = None
        self.manual_fault = None
        self.manual_expires_monotonic_ns = None

    def publish_active_faults(self, active_faults: list[FaultSpec], now_ns: int) -> None:
        self.active_publisher.publish(Bool(data=bool(active_faults)))
        if not active_faults:
            return
        fault_types = [fault.type for fault in active_faults]
        telemetry = {
            "scenario": self.engine.scenario.name,
            "fault_ids": [fault.id for fault in active_faults],
            "fault_types": fault_types,
            "timestamp_ns": now_ns,
            "dropped": "liveness" in fault_types,
            "manual": self.manual_control,
        }
        self.type_publisher.publish(String(data=",".join(fault_types)))
        self.timestamp_publisher.publish(Int64(data=now_ns))
        self.event_publisher.publish(String(data=json.dumps(telemetry, separators=(",", ":"))))

    def publish_started_faults(self, started_faults: list[FaultSpec], now_ns: int) -> None:
        for fault in started_faults:
            self.measurement_publisher.publish(
                String(
                    data=json.dumps(
                        {
                            "schema_version": 1,
                            "event": "fault_injected",
                            "fault_id": fault.id,
                            "fault_type": fault.type,
                            "monotonic_ns": time.monotonic_ns(),
                            "ros_time_ns": now_ns,
                            "manual": self.manual_control,
                        },
                        separators=(",", ":"),
                    )
                )
            )

    def on_detection(self, message: DetectedObjects) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if (
            self.last_detection_ns is not None
            and now_ns - self.last_detection_ns > self.reset_gap_ns
        ):
            self.engine.reset()
            self.clear_manual_fault()
            self.get_logger().info("reset fault scenario after source-stream gap")
        self.last_detection_ns = now_ns
        event = detection_event(message, now_ns)
        if self.manual_control:
            if self.manual_engine is None and self.pending_manual_fault_type is not None:
                self.start_manual_fault()
            if (
                self.manual_engine is not None
                and self.manual_expires_monotonic_ns is not None
                and time.monotonic_ns() >= self.manual_expires_monotonic_ns
            ):
                self.clear_manual_fault()
            if self.manual_engine is not None and self.manual_fault is not None:
                output = self.manual_engine.process(event)
                active_faults = [self.manual_fault]
                self.publish_active_faults(active_faults, now_ns)
                if self.manual_engine.stats[self.manual_fault.id].active_events == 1:
                    self.publish_started_faults(active_faults, now_ns)
            else:
                output = event
                self.publish_active_faults([], now_ns)
            if output is not None:
                self.publisher.publish(detection_message(output))
            return

        before = {
            fault_id: stats.active_events for fault_id, stats in self.engine.stats.items()
        }
        output = self.engine.process(event)
        active_faults = [
            fault
            for fault in self.engine.scenario.faults
            if self.engine.stats[fault.id].active_events > before[fault.id]
        ]
        started_faults = [fault for fault in active_faults if before[fault.id] == 0]
        self.publish_active_faults(active_faults, now_ns)
        # This is a measurement side channel only. It is emitted immediately
        # before the first corrupted output for a fault interval and is never
        # subscribed to by the detector.
        self.publish_started_faults(started_faults, now_ns)
        if output is not None:
            self.publisher.publish(detection_message(output))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--input-topic", default="/second_sight/perception/raw")
    parser.add_argument(
        "--output-topic", default="/perception/object_recognition/detection/objects"
    )
    parser.add_argument("--reset-gap-seconds", type=float, default=2.0)
    parser.add_argument(
        "--manual-control",
        action="store_true",
        help="wait for dashboard commands instead of running the scheduled scenario",
    )
    parser.add_argument("--control-topic", default="/second_sight/dashboard/inject_fault")
    parser.add_argument("--manual-duration-ms", type=int, default=900)
    args, ros_args = parser.parse_known_args()
    if args.reset_gap_seconds <= 0:
        parser.error("--reset-gap-seconds must be positive")
    if not 100 <= args.manual_duration_ms <= 10_000:
        parser.error("--manual-duration-ms must be between 100 and 10000")
    rclpy.init(args=ros_args)
    node = FaultInjectorNode(
        args.scenario,
        args.input_topic,
        args.output_topic,
        args.reset_gap_seconds,
        args.manual_control,
        args.control_topic,
        args.manual_duration_ms,
    )
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
