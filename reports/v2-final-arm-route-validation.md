# V2 final Arm route validation

This is the final no-leakage evaluation of the V2 Second Sight research
prototype. It is evidence from an autonomous-driving simulator, not a safety
certification or a claim about physical braking distance.

## What changed in V2

The frozen 25-tree Isolation Forest remains the learned core. V2 adds three
small, deterministic perception-health monitors, each calibrated only on normal
streams:

- `confidence_health` detects sustained collapsed classification confidence;
- `source_freshness` detects repeated stale source frames; and
- `perception_liveness_timeout` detects a silent perception stream timeout.

This hybrid design covers failure modes that a planning-tick anomaly model
cannot observe reliably by itself. The generic guardrails intentionally use
only route-invariant motion and frame-change signals; absolute object counts,
confidence, and source age are handled by the forest or their dedicated
monitors. This correction matters: an earlier `straight-through-intersection`
route exposed a 95.3% clean false-positive rate from route-specific absolute
count guardrails. That route is retained only as a regression check and is not
used for any headline result.

## Frozen protocol

- **Platform:** AWS `c8g.4xlarge`, Graviton/Arm64, Ubuntu 22.04, kernel
  `6.8.0-1061-aws`, Sydney (`ap-southeast-2`).
- **Frozen manifest:**
  [`v2-final-arm-route-split-20260805.yaml`](../configs/cohorts/v2-final-arm-route-split-20260805.yaml),
  committed before final-cohort collection.
- **Normal-only train route:** `north-approach-right-turn`.
- **Normal-only calibration route:** `npc1-crossing-route`.
- **Untouched final route:** `straight-through-exit`; smoke-tested before the
  manifest was frozen, then recorded three times for this evaluation.
- **Model:** 25-tree hybrid bundle, 368,261 bytes; SHA-256
  `5918f02f5899b4534fd5f5b06e39b020883419ac6fca3688d355b57e40596f6b`.
- **Run ID:** `v2-final-arm-route-validation-20260805`.

The training and calibration data contain normal streams only. The six
injected fault families below were neither training labels nor calibration
examples.

## Held-out route result

Across the three untouched recordings, the final cohort had 35,913 clean
decision opportunities: 34,577 hybrid planning ticks and 1,336 direct-monitor
frames. It produced **zero false positives (0.000%)**. The two denominators are
reported together only as decision opportunities; they are not an unqualified
per-frame rate.

Each deterministic injected fault was replayed once per final recording. All
six fault families were detected in all three runs.

| Fault | Detected | p50 time-to-detect | p99 time-to-detect | First decision path |
| --- | ---: | ---: | ---: | --- |
| Vanish | 3 / 3 | 107.135 ms | 131.858 ms | trajectory hybrid |
| Phantom | 3 / 3 | 104.384 ms | 131.168 ms | trajectory hybrid |
| Teleport | 3 / 3 | 110.611 ms | 132.440 ms | trajectory hybrid |
| Freeze | 3 / 3 | 168.180 ms | 195.799 ms | source freshness (2/3); hybrid (1/3) |
| Confidence collapse | 3 / 3 | 167.807 ms | 195.148 ms | confidence health |
| Perception hang | 3 / 3 | 267.535 ms | 294.845 ms | liveness timeout |

Time-to-detect is timestamp-driven stream replay latency from the injected
fault timestamp to the first anomaly decision. It does not include ROS/DDS
transport, service handling, braking, or a physical vehicle.

## Integrated safe-stop service trials

Twelve separate native-Arm simulator trials exercised four distinct decision
paths: phantom/trajectory hybrid, confidence collapse/confidence health,
freeze/source freshness, and hang/liveness timeout. Every trace contains an
Autoware `safe_stop_response` with `accepted: true`.

| Decision path | Trials | Fault-to-safe-stop-request p50 | p99 |
| --- | ---: | ---: | ---: |
| Confidence health | 3 | 101.738 ms | 101.903 ms |
| Source freshness | 3 | 101.836 ms | 101.897 ms |
| Perception liveness timeout | 3 | 233.077 ms | 251.686 ms |
| Trajectory hybrid (phantom) | 3 | 9,141.416 ms | 13,841.626 ms |

The phantom/trajectory-hybrid trial is deliberately included rather than
hidden: this simulator integration path is currently slow and must **not** be
presented as low-latency safety performance. These trials establish that a
safe-stop request received an accepted service response; they do not prove
end-to-end stopping time, braking distance, independence from the main stack,
or suitability for a safety-critical deployment.

## Native Arm model benchmark

On the frozen model, 10,000 steady-state hybrid scores after 1,000 warm-up
ticks produced the following native Arm microbenchmark result:

| Metric | Result |
| --- | ---: |
| p50 inference | 751.116 µs |
| p95 inference | 777.506 µs |
| p99 inference | 914.808 µs |
| Mean inference | 757.188 µs |

This is a 25-tree scikit-learn/joblib model, not an INT8 model; this report
makes no quantization claim.

## Evidence archive

The private evidence archive contains the frozen model and manifest, route
smoke, raw ROS bags, clean streams, faulted streams, reports, all 12 live
traces, Arm Performix export, and SHA-256 manifests:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/v2-final-arm-route-validation-20260805/
```

At archival completion it contained 75 objects totaling 5,149,577,767 bytes.
The additional archive checksum manifest has SHA-256
`dd321bbb7159c81d423d9dda1009de735de00818f8fca18f3559c5959a25a187`.
The archive is private because it includes large simulator data; the source,
protocol, manifest, and report methodology are public in this repository.

See [`arm-performix-v2-final-profile.md`](arm-performix-v2-final-profile.md)
for the matching official Arm Performix profile.
