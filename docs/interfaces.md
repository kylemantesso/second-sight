# Open AD Kit Interfaces

These interfaces were observed from the pinned Open AD Kit demo on 2026-07-16.
They define the first fault-injector and Second Sight integration contract. Recheck
them when the upstream Autoware revision changes.

## Selected Streams

| Role | ROS 2 name | Type | Observed rate |
| --- | --- | --- | --- |
| Raw detections | `/perception/object_recognition/detection/objects` | `autoware_perception_msgs/msg/DetectedObjects` | 10 Hz |
| Predicted objects | `/perception/object_recognition/objects` | `autoware_perception_msgs/msg/PredictedObjects` | about 10 Hz |
| Final trajectory | `/planning/scenario_planning/trajectory` | `autoware_planning_msgs/msg/Trajectory` | about 10 Hz |

The injector belongs immediately after raw detections so corrupted objects flow
through Autoware tracking, prediction, and planning. During integration, remap
the simulator's raw detection output to a private injector input and let the
injector publish the canonical detection topic. This prevents the original and
corrupted publishers from racing on one topic.

The Second Sight should observe the injector's canonical detection output and the
final planning trajectory. Predicted objects can be recorded for comparison,
but are not required for the first feature schema.

The measured rates above are interface observations, not performance results.
The simulator warned that this Mac could execute the configured scenario at
only about 4.4 frames per second, even though the selected ROS topics continued
to report about 10 Hz.

## Detection Fields

`DetectedObjects` contains a timestamp, frame ID, and object array. Each object
provides the inputs required by the planned faults and features:

- `existence_probability`
- classification labels and probabilities
- pose, orientation, and optional covariance
- linear/angular velocity and availability flags
- shape type, footprint, and dimensions

## Trajectory Fields

`Trajectory` contains a timestamp, frame ID, and trajectory points. Each point
includes:

- time from trajectory start
- pose and orientation
- longitudinal and lateral velocity
- acceleration and heading rate
- front and rear wheel angles

## Safe Stop

Primary integration service:

```text
/control/vehicle_cmd_gate/set_stop
tier4_control_msgs/srv/SetStop
```

The request contains `stop: true` and a `request_source` string. The Second Sight
will use a stable source such as `second_sight` and publish separate Second Sight
telemetry so detection time and stop acceptance remain observable.

Emergency fallback:

```text
/control/vehicle_cmd_gate/external_emergency_stop
std_srvs/srv/Trigger
```

The fallback should be tested separately because an emergency stop has
different comfort and recovery semantics from a requested safe stop.

## Clean Bag

Record all selected streams from a fresh scenario with:

```bash
./scripts/openadkit.sh record 45
```

The resulting bag is stored under `data/raw/`. Generated bags are intentionally
not committed to Git.
