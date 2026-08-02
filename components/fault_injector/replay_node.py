#!/usr/bin/env python3
"""Publish a portable Second Sight stream as live Autoware ROS 2 messages."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import rclpy
from autoware_perception_msgs.msg import DetectedObject, DetectedObjects, ObjectClassification
from autoware_planning_msgs.msg import Trajectory, TrajectoryPoint
from builtin_interfaces.msg import Time
from geometry_msgs.msg import Point32
from rclpy.node import Node

from second_sight.stream import event_time_ns, iter_events


def ros_time(timestamp_ns: int) -> Time:
    message = Time()
    message.sec, message.nanosec = divmod(timestamp_ns, 1_000_000_000)
    return message


def assign_vector(message: Any, values: dict[str, float]) -> None:
    message.x = values["x"]
    message.y = values["y"]
    message.z = values["z"]


def assign_quaternion(message: Any, values: dict[str, float]) -> None:
    assign_vector(message, values)
    message.w = values["w"]


class PortableReplayNode(Node):
    def __init__(self, detection_topic: str) -> None:
        super().__init__("second_sight_portable_replay")
        self.detection_publisher = self.create_publisher(
            DetectedObjects, detection_topic, 10
        )
        self.trajectory_publisher = self.create_publisher(
            Trajectory, "/planning/scenario_planning/trajectory", 10
        )

    def publish_detection(self, event: dict[str, Any], timestamp_ns: int) -> None:
        message = DetectedObjects()
        message.header.stamp = ros_time(timestamp_ns)
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
            assign_quaternion(
                kinematics.pose_with_covariance.pose.orientation, source["orientation"]
            )
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
        self.detection_publisher.publish(message)

    def publish_trajectory(self, event: dict[str, Any], timestamp_ns: int) -> None:
        message = Trajectory()
        message.header.stamp = ros_time(timestamp_ns)
        message.header.frame_id = event.get("frame_id", "map")
        for source in event.get("points", []):
            point = TrajectoryPoint()
            point.time_from_start.sec, point.time_from_start.nanosec = divmod(
                source["time_from_start_ns"], 1_000_000_000
            )
            assign_vector(point.pose.position, source["position"])
            assign_quaternion(point.pose.orientation, source["orientation"])
            point.longitudinal_velocity_mps = source["longitudinal_velocity_mps"]
            point.lateral_velocity_mps = source["lateral_velocity_mps"]
            point.acceleration_mps2 = source["acceleration_mps2"]
            point.heading_rate_rps = source["heading_rate_rps"]
            point.front_wheel_angle_rad = source["front_wheel_angle_rad"]
            point.rear_wheel_angle_rad = source["rear_wheel_angle_rad"]
            message.points.append(point)
        self.trajectory_publisher.publish(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stream", type=Path)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument(
        "--detection-topic", default="/perception/object_recognition/detection/objects"
    )
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--loop-delay", type=float, default=3.0)
    parser.add_argument("--shutdown-delay", type=float, default=1.0)
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")
    if args.loop_delay < 0:
        parser.error("--loop-delay must be non-negative")
    if args.shutdown_delay < 0:
        parser.error("--shutdown-delay must be non-negative")

    events = list(iter_events(args.stream))
    if not events:
        parser.error("stream is empty")
    rclpy.init()
    node = PortableReplayNode(args.detection_topic)
    try:
        time.sleep(3)
        while rclpy.ok():
            first_timeline_ns = event_time_ns(events[0])
            first_source_ns = events[0]["timestamp_ns"]
            start_wall_ns = time.monotonic_ns()
            start_ros_ns = node.get_clock().now().nanoseconds
            for event in events:
                timeline_offset_ns = int(
                    (event_time_ns(event) - first_timeline_ns) / args.rate
                )
                target_wall_ns = start_wall_ns + timeline_offset_ns
                remaining_seconds = (target_wall_ns - time.monotonic_ns()) / 1_000_000_000
                if remaining_seconds > 0:
                    time.sleep(remaining_seconds)
                source_ns = event.get("source_timestamp_ns", event["timestamp_ns"])
                mapped_source_ns = start_ros_ns + int(
                    (source_ns - first_source_ns) / args.rate
                )
                if event["kind"] == "detections":
                    node.publish_detection(event, mapped_source_ns)
                else:
                    node.publish_trajectory(event, mapped_source_ns)
                rclpy.spin_once(node, timeout_sec=0)
            if not args.loop:
                time.sleep(args.shutdown_delay)
                break
            node.get_logger().info(f"restarting stream in {args.loop_delay:.1f} seconds")
            time.sleep(args.loop_delay)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
