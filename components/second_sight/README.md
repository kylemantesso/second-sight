# Second Sight ROS 2 Node

Live ROS 2 adapter around the portable feature extractor and persisted hybrid
detector. It subscribes to Autoware detections and trajectory, publishes
telemetry every trajectory tick, and can request a vehicle-command-gate stop.

## Telemetry

- `/second_sight/anomaly_score` (`std_msgs/msg/Float64`)
- `/second_sight/anomaly` (`std_msgs/msg/Bool`)
- `/second_sight/inference_ms` (`std_msgs/msg/Float64`)
- `/second_sight/status` (`std_msgs/msg/String`, JSON details and trigger features)
- `/second_sight/safe_stop_requested` (`std_msgs/msg/Bool`)
- `/second_sight/latency/decision` (`std_msgs/msg/String`, JSON)
- `/second_sight/latency/safe_stop_requested` (`std_msgs/msg/String`, JSON)

## Safe Stop

The node defaults to dry-run mode. After two consecutive anomalous ticks it
publishes `safe_stop_requested` but does not command Autoware. Pass
`--enable-safe-stop` to call:

```text
/control/vehicle_cmd_gate/set_stop
tier4_control_msgs/srv/SetStop
```

The request uses `stop: true` and `request_source: second_sight`. Stop requests
are latched so a persistent anomaly cannot flood the service.

The two latency topics are measurement side channels. They carry a
same-host monotonic timestamp at the anomaly decision and stop-request points;
the detector never consumes fault ground-truth timing. Use the latency monitor
to correlate these records with injector timing on Arm Linux.

## Experimental perception fast path

`--enable-perception-fast-path` runs the normal-only, perception-derived
guardrails on every detection message, without waiting for a downstream
trajectory. It intentionally excludes trajectory-dependent relative-motion and
near-object-drop features. It is opt-in: the Isolation Forest remains
trajectory-context dependent, and the fast path must pass clean-stream and Arm
validation before it becomes the default.

When using the integrated compose stack, pass the flag through explicitly:

```bash
SECOND_SIGHT_NODE_ARGS="--enable-perception-fast-path" \
./scripts/run-live-latency-trial.sh arm-phantom-fast-r01 \
  configs/scenarios/latency/phantom.yaml
```

## Container

```bash
docker build -f components/second_sight/Dockerfile -t second-sight-node:dev .
```

The image is based on the pinned Arm64 Autoware planning image and includes
scikit-learn 1.7.2, the same version used to serialize the model. macOS measurements are
development-only; benchmark inference and end-to-end latency on Arm Linux.

Verify live subscriptions and scoring against the clean bag in dry-run mode:

```bash
./scripts/second-sight-replay-smoke.sh
```

The smoke test uses ROS simulated time so historical bag header timestamps are
not incorrectly classified as stale.

To validate the experimental perception fast path against the same clean bag,
enable it explicitly:

```bash
SECOND_SIGHT_NODE_ARGS="--enable-perception-fast-path" \
./scripts/second-sight-replay-smoke.sh \
  data/raw/openadkit-clean-20260716T112843Z \
  models/hybrid-25tree.joblib
```

For a ROS-independent portable clean stream (useful on a benchmark host that
does not retain the bag), run:

```bash
SECOND_SIGHT_NODE_ARGS="--enable-perception-fast-path" \
./scripts/second-sight-portable-clean-replay-smoke.sh \
  data/processed/openadkit-clean-20260716T112843Z.jsonl \
  models/hybrid-25tree.joblib
```

Verify the opposite assertion, that a corrupted stream requests a dry-run
stop, with:

```bash
./scripts/second-sight-fault-replay-smoke.sh
```
