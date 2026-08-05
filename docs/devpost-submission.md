# Devpost submission copy — Second Sight

This page is ready-to-paste submission material for the Arm AI Optimization
Challenge Physical AI track. Keep the limitations below with any shortened
version of the performance claims.

## Project overview

**Who watches the AI?** Second Sight is an independent watchdog for silent
perception failures in autonomous-driving software. A perception stack can
return a plausible but wrong result without throwing an exception. Second
Sight observes the perception and planning streams, learns normal behavior
from clean simulation drives, and asks Autoware for a safe stop when the
stream becomes suspicious.

The project combines a compact normal-only 25-tree Isolation Forest with three
calibrated direct-perception health checks: collapsed confidence, stale source
frames, and a silent perception timeout. It also includes a deterministic ROS
2 fault injector for six failure families—vanish, phantom, freeze, teleport,
confidence collapse, and perception hang—so training data, regression tests,
and demos are repeatable instead of manually labelled.

This is interesting because the watchdog is not trained to recognise the
faults it is judged on. It is trained and calibrated only on normal streams
from separate route families, then tested on an unseen route with injected
faults. The reusable fault injector and timestamped evaluation harness make
the approach useful beyond this simulator.

## Functionality and output

Second Sight provides:

- a ROS 2 middleware fault injector with deterministic scenarios;
- portable feature extraction and a normal-only hybrid anomaly detector;
- a ROS-facing watchdog that publishes anomaly telemetry and requests an
  Autoware safe stop;
- timestamp-driven, per-fault detection and service-response reports; and
- an Arm64 validation and profiling protocol with an Arm Performix export.

On an AWS Graviton `c8g.4xlarge` Arm64 host, the frozen V2 model was tested on
three unseen-route clean recordings. Across 35,913 clean decision
opportunities it produced 0 false positives. Each of six deterministic fault
families was detected in 3/3 replay runs. Native Arm hybrid inference measured
751.116 µs p50 and 914.808 µs p99 for a 368,261-byte model. The matching Arm
Performix workload sustained 1,328.227 ticks/second.

These are simulator and offline-replay measurements. The integrated trials
show accepted Autoware safe-stop service responses, but they do not demonstrate
certified safety, physical braking distance, or a low-latency
trajectory-hybrid path. Full methods, results, and caveats are in
[`reports/v2-final-arm-route-validation.md`](../reports/v2-final-arm-route-validation.md)
and [`reports/arm-performix-v2-final-profile.md`](../reports/arm-performix-v2-final-profile.md).

## Setup and validation

The public repository is MIT licensed:

```text
https://github.com/kylemantesso/second-sight
```

For portable development checks on macOS or Linux, install `uv`, then run:

```bash
uv sync
uv run second-sight doctor
uv run ruff check .
uv run pytest
```

For the ROS 2 transport smoke test, install Docker and run:

```bash
./scripts/ros-smoke.sh
```

For the Open AD Kit simulator setup, route controls, container workflow, and
macOS limitations, follow [`mac-setup.md`](mac-setup.md). For native Arm64
collection and benchmark procedure, use an Arm Linux environment and follow
[`benchmarking.md`](benchmarking.md) plus the executable V2 protocol in
[`v2-validation.md`](v2-validation.md). The route split that produced the
published result is versioned in
[`configs/cohorts/v2-final-arm-route-split-20260805.yaml`](../configs/cohorts/v2-final-arm-route-split-20260805.yaml).

Large raw simulator bags and private Performix exports are not committed to
Git; their integrity and archive locations are documented in the final reports.

## Demonstration video outline

The video should stay under three minutes. Open with a pedestrian visible in
the simulated world while a `vanish` fault removes its detection, then replay
the same scene with Second Sight’s anomaly heartbeat and safe-stop request.
Show one visible terminal fault injection and the Arm64 host identity. Use at
most three full-screen figures: **0 false positives across 35,913 held-out
clean decision opportunities**, **6/6 deterministic fault families detected
in 3/3 runs**, and **751.116 µs Arm p50 inference**. Captions must make clear
that this is a simulator research prototype, not certified vehicle safety.
