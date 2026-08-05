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

The demo replays a clean final-route fixture through the real ROS 2 fault
injector and the immutable V2 model. It starts clean, loops continuously, and
waits for a command on `/second_sight/dashboard/inject_fault`; it does not
auto-inject faults. Use `integrated-start` only when you also need the full
Open AD Kit simulator and RViz visualization.

Foxglove currently requires a developer seat to author or import layouts. A
basic seat can view a layout shared by a developer-seat user. Local Mac timing
is for visual development only; latency overlays in submission footage must
come from Arm Linux measurements.

## Browser demo layer

The repository also has a browser visualisation that can run in either visual
fallback or live-model mode:

```bash
./scripts/demo-visualisation.sh
```

Open <http://localhost:4173/demo/>. When `dashboard-start` is running, the
page connects to Foxglove Bridge at `ws://localhost:8765` and shows **LIVE MODEL
CONNECTED**. The Inject button then publishes a command to the real ROS 2 fault
injector; the confirmation, decision path, anomaly score, and dry-run
safe-stop state are consumed from real Second Sight topics. The moving road
scene is deliberately labelled **VISUAL DRIVER**: it illustrates the
perception failure but is not a rendered Autoware view. A dry-run stop remains
latched after detection, just as a safety monitor should. Use **Reset live run**
to send an explicit ROS reset command before demonstrating another fault; that
button exists only in the local dashboard-demo configuration and never clears a
real vehicle stop.

The **Model process trace** panel is deliberately separate from the animated
scene. It renders raw, live ROS 2 telemetry: the loaded model SHA-256 prefix,
latest forest score, injector event, anomaly decision, monitor values and
frozen thresholds, and dry-run stop request. For example, a confidence-collapse
run shows the measured mean classification probability, its frozen normal-data
floor, and the two-frame decision count.

If the live stack is unavailable, the same page falls back to a clearly labelled
browser-only visual walkthrough. It retains the held-out Arm result cards but
does not claim live scoring in that mode.

Live mode runs the frozen V2 model bundle used by the final Arm validation. The
local replay is for interaction and video composition only: Mac timing, the
animated road, and the dry-run stop request are not Arm performance evidence,
physical braking, or certification. Cite the final Arm report for all measured
claims. The local compose configuration disables only the V2
`source_freshness` monitor: its frozen 5.227 ms threshold is valid for the
native Arm measurement pipeline but is below the scheduling jitter of a Mac
Docker replay. The learned hybrid model plus confidence-health and liveness
paths still run live. This local compatibility setting is not used for any
reported result.
