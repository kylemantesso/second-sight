#!/usr/bin/env python3
"""Live ROS 2 adapter for the portable Second Sight detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import rclpy
from autoware_perception_msgs.msg import DetectedObjects
from autoware_planning_msgs.msg import Trajectory
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool, Float64, String
from tier4_control_msgs.srv import SetStop

from second_sight.features import FeatureExtractor
from second_sight.liveness import DetectionLiveness
from second_sight.model import PERCEPTION_GUARDRAIL_FEATURES, SecondSightScorer
from second_sight.safety_monitors import DetectionSafetyMonitors


def vector(message: Any) -> dict[str, float]:
    return {"x": message.x, "y": message.y, "z": message.z}


def quaternion(message: Any) -> dict[str, float]:
    return {"x": message.x, "y": message.y, "z": message.z, "w": message.w}


def stamp_ns(message: Any) -> int:
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


def trajectory_event(message: Trajectory, recorded_ns: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "trajectory",
        "timestamp_ns": stamp_ns(message) or recorded_ns,
        "recorded_ns": recorded_ns,
        "frame_id": message.header.frame_id,
        "points": [
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
        ],
    }


class SecondSightNode(Node):
    def __init__(
        self,
        model_path: Path,
        mode: str,
        enable_safe_stop: bool,
        stop_after: int,
        reset_gap_seconds: float,
        enable_perception_fast_path: bool,
        fast_stop_after: int,
        enable_perception_liveness: bool,
        liveness_timeout_ms: float | None,
        enable_safety_monitors: bool,
        enable_source_freshness: bool,
        dashboard_reset_control: bool,
    ) -> None:
        super().__init__("second_sight")
        self.model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
        self.extractor = FeatureExtractor()
        self.scorer = SecondSightScorer(model_path, mode)
        self.fast_extractor = FeatureExtractor() if enable_perception_fast_path else None
        self.fast_scorer = (
            SecondSightScorer(
                model_path,
                "guardrails",
                guardrail_features=PERCEPTION_GUARDRAIL_FEATURES,
                implementation="optimized",
            )
            if enable_perception_fast_path
            else None
        )
        self.safety_monitor_config = (
            self.scorer.safety_monitor_config if enable_safety_monitors else None
        )
        self.safety_monitors = DetectionSafetyMonitors(
            self.safety_monitor_config, enable_source_freshness=enable_source_freshness
        )
        self.enable_source_freshness = enable_source_freshness
        self.monitor_extractor = FeatureExtractor() if self.safety_monitors.enabled else None
        self.enable_safe_stop = enable_safe_stop
        self.stop_after = stop_after
        self.consecutive_anomalies = 0
        self.stop_requested = False
        self.was_anomalous = False
        self.fast_consecutive_anomalies = 0
        self.fast_was_anomalous = False
        self.enable_perception_fast_path = enable_perception_fast_path
        self.fast_stop_after = fast_stop_after
        configured_timeout_ms = (
            float(self.safety_monitor_config["perception_liveness"]["timeout_ms"])
            if self.safety_monitor_config is not None
            else None
        )
        active_timeout_ms = liveness_timeout_ms or configured_timeout_ms
        self.active_liveness_timeout_ms = active_timeout_ms
        self.liveness = (
            DetectionLiveness(active_timeout_ms)
            if active_timeout_ms is not None
            and (enable_perception_liveness or self.safety_monitors.enabled)
            else None
        )
        self.reset_gap_ns = round(reset_gap_seconds * 1_000_000_000)
        self.last_trajectory_ns: int | None = None

        self.create_subscription(
            DetectedObjects,
            "/perception/object_recognition/detection/objects",
            self.on_detections,
            10,
        )
        self.create_subscription(
            Trajectory,
            "/planning/scenario_planning/trajectory",
            self.on_trajectory,
            10,
        )
        self.score_publisher = self.create_publisher(Float64, "/second_sight/anomaly_score", 10)
        self.anomaly_publisher = self.create_publisher(Bool, "/second_sight/anomaly", 10)
        self.latency_publisher = self.create_publisher(Float64, "/second_sight/inference_ms", 10)
        self.status_publisher = self.create_publisher(String, "/second_sight/status", 10)
        self.stop_publisher = self.create_publisher(Bool, "/second_sight/safe_stop_requested", 10)
        self.decision_publisher = self.create_publisher(
            String, "/second_sight/latency/decision", 10
        )
        self.stop_event_publisher = self.create_publisher(
            String, "/second_sight/latency/safe_stop_requested", 10
        )
        self.stop_response_event_publisher = self.create_publisher(
            String, "/second_sight/latency/safe_stop_response", 10
        )
        if dashboard_reset_control:
            self.create_subscription(
                String, "/second_sight/dashboard/inject_fault", self.on_dashboard_command, 10
            )
        self.stop_client = self.create_client(SetStop, "/control/vehicle_cmd_gate/set_stop")
        if self.liveness is not None:
            timer_period_seconds = min(max(active_timeout_ms / 4_000, 0.01), 0.1)
            self.create_timer(timer_period_seconds, self.on_liveness_timer)
        self.get_logger().info(
            "Second Sight ready: "
            f"mode={mode}, fast_path={'enabled' if enable_perception_fast_path else 'disabled'}, "
            f"liveness={'enabled' if self.liveness is not None else 'disabled'}, "
            f"safety_monitors={'enabled' if self.safety_monitors.enabled else 'disabled'}, "
            f"source_freshness={'enabled' if enable_source_freshness else 'disabled'}, "
            f"dashboard_reset={'enabled' if dashboard_reset_control else 'disabled'}, "
            f"safe_stop={'enabled' if enable_safe_stop else 'dry-run'}"
        )

    def now_ns(self) -> int:
        return self.get_clock().now().nanoseconds

    def on_dashboard_command(self, message: String) -> None:
        """Reset the dry-run demo only when explicitly requested by the dashboard."""
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict) or payload.get("action") != "reset":
            return
        self.extractor = FeatureExtractor()
        self.monitor_extractor = FeatureExtractor() if self.safety_monitors.enabled else None
        self.safety_monitors = DetectionSafetyMonitors(
            self.safety_monitor_config,
            enable_source_freshness=self.enable_source_freshness,
        )
        self.consecutive_anomalies = 0
        self.stop_requested = False
        self.was_anomalous = False
        self.fast_consecutive_anomalies = 0
        self.fast_was_anomalous = False
        self.last_trajectory_ns = None
        if self.active_liveness_timeout_ms is not None:
            self.liveness = DetectionLiveness(self.active_liveness_timeout_ms)
        self.anomaly_publisher.publish(Bool(data=False))
        self.stop_publisher.publish(Bool(data=False))
        self.status_publisher.publish(String(data=json.dumps({"anomalous": False, "reset": True})))
        self.get_logger().info("reset dry-run dashboard state")

    def on_detections(self, message: DetectedObjects) -> None:
        event = detection_event(message, self.now_ns())
        if self.liveness is not None:
            self.liveness.record_detection(time.monotonic_ns())
        self.extractor.process_event(event)
        if self.monitor_extractor is not None:
            monitor_row = self.monitor_extractor.process_detection_tick(event)
            self.score_detection_safety_monitors(monitor_row)
        if self.fast_extractor is not None and self.fast_scorer is not None:
            row = self.fast_extractor.process_detection_tick(event)
            self.score_perception_guardrails(row)

    def on_liveness_timer(self) -> None:
        if self.liveness is None or not self.liveness.timed_out(time.monotonic_ns()):
            return
        decision_monotonic_ns = time.monotonic_ns()
        self.decision_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "schema_version": 1,
                        "event": "anomaly_decision",
                        "path": "perception_liveness_timeout",
                        "anomalous": True,
                        "monotonic_ns": decision_monotonic_ns,
                        "consecutive_anomalies": 1,
                    },
                    separators=(",", ":"),
                )
            )
        )
        self.get_logger().warning("perception liveness timeout")
        self.request_safe_stop("perception_liveness_timeout")

    def on_trajectory(self, message: Trajectory) -> None:
        now_ns = self.now_ns()
        event = trajectory_event(message, now_ns)
        if (
            self.reset_gap_ns > 0
            and self.last_trajectory_ns is not None
            and now_ns - self.last_trajectory_ns > self.reset_gap_ns
        ):
            self.consecutive_anomalies = 0
            self.stop_requested = False
            self.was_anomalous = False
            self.get_logger().info("reset dry-run state after source-stream gap")
        self.last_trajectory_ns = now_ns
        if self.monitor_extractor is not None:
            self.monitor_extractor.update_trajectory_context(event)
        if self.fast_extractor is not None:
            self.fast_extractor.update_trajectory_context(event)
        row = self.extractor.process_event(event)
        if row is None:
            return
        started_ns = time.perf_counter_ns()
        result = self.scorer.score(row)
        inference_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        decision_monotonic_ns = time.monotonic_ns()
        anomalous = result["anomalous"]
        self.consecutive_anomalies = self.consecutive_anomalies + 1 if anomalous else 0

        self.score_publisher.publish(Float64(data=result["forest_score"]))
        self.anomaly_publisher.publish(Bool(data=anomalous))
        self.latency_publisher.publish(Float64(data=inference_ms))
        self.status_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "anomalous": anomalous,
                        "forest_score": result["forest_score"],
                        "guardrail_score": result["guardrail_score"],
                        "guardrail_features": result["guardrail_features"],
                        "consecutive_anomalies": self.consecutive_anomalies,
                        "model_sha256": self.model_sha256,
                        "mode": "trajectory_hybrid",
                    },
                    separators=(",", ":"),
                )
            )
        )
        self.decision_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "schema_version": 1,
                        "event": "anomaly_decision",
                        "path": "trajectory_hybrid",
                        "anomalous": anomalous,
                        "monotonic_ns": decision_monotonic_ns,
                        "inference_ms": inference_ms,
                        "consecutive_anomalies": self.consecutive_anomalies,
                    },
                    separators=(",", ":"),
                )
            )
        )
        self.stop_publisher.publish(Bool(data=self.stop_requested))
        if anomalous and not self.was_anomalous:
            self.get_logger().warning(
                f"anomaly score={result['forest_score']:.4f} "
                f"guardrails={result['guardrail_features']} inference_ms={inference_ms:.3f}"
            )
        elif not anomalous and self.was_anomalous:
            self.get_logger().info("anomaly cleared")
        self.was_anomalous = anomalous
        if self.consecutive_anomalies >= self.stop_after:
            self.request_safe_stop()

    def score_detection_safety_monitors(self, row: dict[str, float | int]) -> None:
        """Run calibrated direct-perception monitors on every detection frame."""
        for result in self.safety_monitors.observe(row):
            decision_monotonic_ns = time.monotonic_ns()
            anomalous = bool(result["anomalous"])
            self.decision_publisher.publish(
                String(
                    data=json.dumps(
                        {
                            "schema_version": 1,
                            "event": "anomaly_decision",
                            "path": result["path"],
                            "anomalous": anomalous,
                            "monotonic_ns": decision_monotonic_ns,
                            "consecutive_anomalies": result["consecutive_anomalies"],
                        },
                        separators=(",", ":"),
                    )
                )
            )
            if not anomalous:
                continue
            self.anomaly_publisher.publish(Bool(data=True))
            self.status_publisher.publish(
                String(
                    data=json.dumps(
                        {
                            "anomalous": True,
                            "path": result["path"],
                            "consecutive_anomalies": result["consecutive_anomalies"],
                            "monitor": result,
                            "monitor_config": self.safety_monitor_config[result["path"]],
                            "model_sha256": self.model_sha256,
                            "mode": "direct_perception_monitor",
                        },
                        separators=(",", ":"),
                    )
                )
            )
            self.get_logger().warning(
                f"{result['path']} anomaly after "
                f"{result['consecutive_anomalies']} consecutive detection frames"
            )
            self.request_safe_stop(str(result["path"]))

    def score_perception_guardrails(self, row: dict[str, float | int]) -> None:
        """Run the opt-in, perception-only guardrail path on every detection."""
        assert self.fast_scorer is not None
        started_ns = time.perf_counter_ns()
        result = self.fast_scorer.score(row)
        inference_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        decision_monotonic_ns = time.monotonic_ns()
        anomalous = result["anomalous"]
        self.fast_consecutive_anomalies = (
            self.fast_consecutive_anomalies + 1 if anomalous else 0
        )
        self.decision_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "schema_version": 1,
                        "event": "anomaly_decision",
                        "path": "perception_guardrails",
                        "anomalous": anomalous,
                        "monotonic_ns": decision_monotonic_ns,
                        "inference_ms": inference_ms,
                        "consecutive_anomalies": self.fast_consecutive_anomalies,
                    },
                    separators=(",", ":"),
                )
            )
        )
        if anomalous and not self.fast_was_anomalous:
            self.get_logger().warning(
                "perception guardrail anomaly "
                f"features={result['guardrail_features']} inference_ms={inference_ms:.3f}"
            )
        self.fast_was_anomalous = anomalous
        if self.fast_consecutive_anomalies >= self.fast_stop_after:
            self.request_safe_stop("perception_guardrails")

    def request_safe_stop(self, path: str = "trajectory_hybrid") -> None:
        if self.stop_requested:
            return
        self.stop_requested = True
        request_monotonic_ns = time.monotonic_ns()
        self.stop_publisher.publish(Bool(data=True))
        self.stop_event_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "schema_version": 1,
                        "event": "safe_stop_requested",
                        "path": path,
                        "monotonic_ns": request_monotonic_ns,
                        "dry_run": not self.enable_safe_stop,
                    },
                    separators=(",", ":"),
                )
            )
        )
        if not self.enable_safe_stop:
            self.get_logger().warning("safe stop requested in dry-run mode")
            return
        if not self.stop_client.service_is_ready():
            self.get_logger().error("safe-stop service is unavailable")
            self.stop_requested = False
            return
        request = SetStop.Request()
        request.stop = True
        request.request_source = "second_sight"
        future = self.stop_client.call_async(request)
        future.add_done_callback(self.on_stop_response)

    def on_stop_response(self, future: Any) -> None:
        try:
            response = future.result()
            response_monotonic_ns = time.monotonic_ns()
            accepted = bool(response.status.success)
            message = str(response.status.message)
            self.stop_response_event_publisher.publish(
                String(
                    data=json.dumps(
                        {
                            "schema_version": 1,
                            "event": "safe_stop_response",
                            "monotonic_ns": response_monotonic_ns,
                            "accepted": accepted,
                            "message": message,
                        },
                        separators=(",", ":"),
                    )
                )
            )
            if accepted:
                self.get_logger().warning("Autoware accepted the safe-stop request")
            else:
                self.get_logger().error(f"safe-stop rejected: {message}")
                self.stop_requested = False
        except Exception as error:
            self.get_logger().error(f"safe-stop request failed: {error}")
            self.stop_requested = False


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("isolation_forest", "guardrails", "hybrid"), default="hybrid"
    )
    parser.add_argument("--enable-safe-stop", action="store_true")
    parser.add_argument("--stop-after", type=int, default=2)
    parser.add_argument("--enable-perception-fast-path", action="store_true")
    parser.add_argument("--fast-stop-after", type=int, default=2)
    parser.add_argument("--enable-perception-liveness", action="store_true")
    parser.add_argument(
        "--liveness-timeout-ms",
        type=float,
        help="override the frozen model's calibrated liveness timeout",
    )
    parser.add_argument(
        "--disable-safety-monitors",
        action="store_true",
        help="disable the frozen model's confidence, freshness, and liveness paths",
    )
    parser.add_argument(
        "--disable-source-freshness",
        action="store_true",
        help="disable only the source-timestamp monitor for a timing-incompatible replay",
    )
    parser.add_argument(
        "--dashboard-reset-control",
        action="store_true",
        help="allow the dashboard to reset dry-run state after a demonstrated stop",
    )
    parser.add_argument("--reset-gap-seconds", type=float, default=0.0)
    args, ros_args = parser.parse_known_args()
    if args.stop_after <= 0:
        parser.error("--stop-after must be positive")
    if args.fast_stop_after <= 0:
        parser.error("--fast-stop-after must be positive")
    if args.liveness_timeout_ms is not None and args.liveness_timeout_ms <= 0:
        parser.error("--liveness-timeout-ms must be positive")
    if args.reset_gap_seconds < 0:
        parser.error("--reset-gap-seconds must be non-negative")
    return args, ros_args


def main() -> None:
    args, ros_args = parse_args()
    rclpy.init(args=ros_args)
    node = SecondSightNode(
        args.model,
        args.mode,
        args.enable_safe_stop,
        args.stop_after,
        args.reset_gap_seconds,
        args.enable_perception_fast_path,
        args.fast_stop_after,
        args.enable_perception_liveness,
        args.liveness_timeout_ms,
        not args.disable_safety_monitors,
        not args.disable_source_freshness,
        args.dashboard_reset_control,
    )
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
