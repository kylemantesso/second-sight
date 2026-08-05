# Foxglove Dashboard

The integrated stack exposes ROS 2 topics through Foxglove Bridge at:

```text
ws://localhost:8765
```

In Foxglove Studio, add a **Foxglove WebSocket** connection and import the
ready-made layout:

```text
configs/foxglove/second-sight-layout.json
```

Use **Layouts > Import from file**, then connect to `ws://localhost:8765`.
The imported layout includes:

- Large green/red Second Sight status indicator
- Clean/fault perception-stream indicator
- Monitoring/safe-stop action indicator
- 30-second heartbeat anomaly-score plot
- Inference-latency plot
- Fault, anomaly, and safe-stop state timeline
- Raw Second Sight status and injection ground truth

For a reliable Mac dashboard preview, use the lightweight looping demo rather
than the resource-heavy full simulator:

```bash
./scripts/openadkit.sh dashboard-start
./scripts/openadkit.sh dashboard-status
./scripts/openadkit.sh dashboard-stop
```

The demo continuously replays the clean recording through the real live fault
injector and Second Sight. Each approximately 38-second cycle applies all six
faults, then resets and repeats. Use `integrated-start` only when you also need
the full Open AD Kit simulator and RViz visualization.

Foxglove currently requires a developer seat to author or import layouts. A
basic seat can view a layout shared by a developer-seat user. Local Mac timing
is for visual development only; latency overlays in submission footage must
come from Arm Linux measurements.

## Browser demo layer

The repository also has a standalone browser visualisation for a polished demo
without a Foxglove account or a running ROS graph:

```bash
./scripts/demo-visualisation.sh
```

Open <http://localhost:4173/demo/>. The page animates the six deterministic
fault scenarios, surfaces their decision paths, and uses the measured held-out
Arm figures from the V2 final report. It is intentionally labelled as a visual
replay: it does not consume live ROS messages and must not be represented as a
vehicle-safety, braking, or end-to-end-latency demonstration.
