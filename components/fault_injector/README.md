# Second Sight Fault Injector

A deterministic corruption engine for autonomous-driving perception streams.
The portable engine runs against exported JSONL recordings on macOS; a thin ROS
2 adapter will apply the same transformations to live
`autoware_perception_msgs/msg/DetectedObjects` messages.

## Usage

```bash
uv run second-sight inject \
  data/processed/openadkit-clean-20260716T112843Z.jsonl \
  --scenario configs/scenarios/all-faults.yaml \
  --output data/processed/openadkit-all-faults.jsonl

uv run second-sight inspect data/processed/openadkit-all-faults.jsonl
```

Injection produces both the corrupted stream and a `.ground-truth.json` report
containing exact fault intervals and modified/dropped message counts.

## Faults

| Type | Behavior |
| --- | --- |
| `vanish` | Removes one class-matched object and tracks it by nearest position |
| `phantom` | Inserts a configured nonexistent object |
| `freeze` | Repeats the last clean payload with its stale source timestamp |
| `teleport` | Applies a discontinuous position offset to one tracked object |
| `confidence_collapse` | Scales existence and classification confidence |
| `liveness` | Drops every targeted event during the configured interval |

Intervals use the bag-recorded timeline and are start-inclusive/end-exclusive.
Faults execute in listed order, making overlapping scenarios deterministic.

## Scenario Format

```yaml
schema_version: 1
name: example
seed: 2026
faults:
  - id: vanish-car
    type: vanish
    start_seconds: 3
    duration_seconds: 2
    target: detections
    parameters:
      class_label: 1
      object_index: 0
```

Autoware classification labels include `0` unknown, `1` car, and `7`
pedestrian. See [`configs/scenarios/all-faults.yaml`](../../configs/scenarios/all-faults.yaml)
for every supported fault.

## Live Replay

`replay_node.py` converts the corrupted portable stream back into real
Autoware ROS messages. Verify that the live Second Sight publishes a dry-run stop:

```bash
./scripts/second-sight-fault-replay-smoke.sh
```

The live injector subscribes to `/second_sight/perception/raw`, publishes corrupted
detections on Autoware's canonical detection topic, and publishes ground truth
under `/second_sight/fault/*`. Verify the complete raw replay to injector to
Second Sight chain with:

```bash
./scripts/live-chain-smoke.sh
```

## Simulator Boundary

The full simulator must publish its original detection output on
`/second_sight/perception/raw`; the injector is then the only publisher on
`/perception/object_recognition/detection/objects`. Apply this remap in the
simulator launch scope, not globally across planning nodes:

```text
/perception/object_recognition/detection/objects
  -> /second_sight/perception/raw
```

Before driving, verify the boundary with `ros2 topic info --verbose`: raw must
have the simulator publisher and canonical detections must have only the fault
injector publisher. Running both original and injected canonical publishers
would race clean and corrupted messages and invalidate the experiment.

The repository includes this simulator-scoped remap in a derived simulator
image. Start the complete stack in dry-run mode with:

```bash
./scripts/openadkit.sh integrated-start
./scripts/openadkit.sh integrated-status
./scripts/openadkit.sh integrated-stop
```

## Ground Truth Telemetry

- `/second_sight/fault/active` (`std_msgs/msg/Bool`)
- `/second_sight/fault/type` (`std_msgs/msg/String`)
- `/second_sight/fault/event` (`std_msgs/msg/String`, JSON)
- `/second_sight/fault/timestamp_ns` (`std_msgs/msg/Int64`)
- `/second_sight/latency/fault_injected` (`std_msgs/msg/String`, JSON)

These topics are directly visible in Foxglove and provide injection timestamps
for automated time-to-detect evaluation. The latency topic is emitted only once
per fault interval, immediately before the first modified or suppressed output,
and carries a same-host monotonic timestamp for the measurement harness.
