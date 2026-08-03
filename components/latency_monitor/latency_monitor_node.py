#!/usr/bin/env python3
"""Persist correlated live timing measurements from Second Sight ROS topics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from second_sight.latency import LatencyTracker


class LatencyMonitorNode(Node):
    """Write one JSONL record per fault, anomaly, and safe-stop timing event."""

    def __init__(self, output_path: Path) -> None:
        super().__init__("second_sight_latency_monitor")
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.tracker = LatencyTracker()
        self.publisher = self.create_publisher(String, "/second_sight/latency/event", 10)
        self.create_subscription(
            String, "/second_sight/latency/fault_injected", self.on_fault, 10
        )
        self.create_subscription(String, "/second_sight/latency/decision", self.on_decision, 10)
        self.create_subscription(
            String, "/second_sight/latency/safe_stop_requested", self.on_safe_stop, 10
        )
        self.create_subscription(
            String, "/second_sight/latency/safe_stop_response", self.on_safe_stop_response, 10
        )
        self.get_logger().info(f"latency monitor writing JSONL to {self.output_path}")

    def payload(self, message: String, topic: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            self.get_logger().warning(f"ignoring invalid JSON from {topic}")
            return None
        if not isinstance(payload, dict):
            self.get_logger().warning(f"ignoring non-object JSON from {topic}")
            return None
        return payload

    def write(self, measurement: dict[str, Any]) -> None:
        line = json.dumps(measurement, separators=(",", ":"), sort_keys=True)
        with self.output_path.open("a", encoding="utf-8") as output:
            output.write(f"{line}\n")
        self.publisher.publish(String(data=line))
        self.get_logger().info(line)

    def on_fault(self, message: String) -> None:
        payload = self.payload(message, "/second_sight/latency/fault_injected")
        if payload is None:
            return
        try:
            measurement = self.tracker.record_fault(
                str(payload["fault_id"]),
                str(payload["fault_type"]),
                int(payload["monotonic_ns"]),
            )
        except (KeyError, TypeError, ValueError):
            self.get_logger().warning("ignoring malformed fault timing payload")
            return
        self.write(measurement)

    def on_decision(self, message: String) -> None:
        payload = self.payload(message, "/second_sight/latency/decision")
        if payload is None or not payload.get("anomalous", False):
            return
        try:
            inference_ms = payload.get("inference_ms")
            measurement = self.tracker.record_anomaly(
                int(payload["monotonic_ns"]),
                float(inference_ms) if inference_ms is not None else None,
                str(payload["path"]) if payload.get("path") is not None else None,
            )
        except (KeyError, TypeError, ValueError):
            self.get_logger().warning("ignoring malformed anomaly timing payload")
            return
        if measurement is not None:
            self.write(measurement)
        completed_stop = self.tracker.completed_safe_stop()
        if completed_stop is not None:
            self.write(completed_stop)

    def on_safe_stop(self, message: String) -> None:
        payload = self.payload(message, "/second_sight/latency/safe_stop_requested")
        if payload is None:
            return
        try:
            measurement = self.tracker.record_safe_stop(
                int(payload["monotonic_ns"]),
                str(payload["path"]) if payload.get("path") is not None else None,
            )
        except (KeyError, TypeError, ValueError):
            self.get_logger().warning("ignoring malformed safe-stop timing payload")
            return
        if measurement is not None:
            self.write(measurement)

    def on_safe_stop_response(self, message: String) -> None:
        payload = self.payload(message, "/second_sight/latency/safe_stop_response")
        if payload is None:
            return
        try:
            measurement = self.tracker.record_safe_stop_response(
                int(payload["monotonic_ns"]),
                bool(payload["accepted"]),
                str(payload["message"]) if payload.get("message") is not None else None,
            )
        except (KeyError, TypeError, ValueError):
            self.get_logger().warning("ignoring malformed safe-stop response timing payload")
            return
        if measurement is not None:
            self.write(measurement)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = LatencyMonitorNode(args.output)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
