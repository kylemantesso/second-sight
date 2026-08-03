# Final Arm route validation

This is the final, no-leakage evaluation run for Second Sight on native Arm
Linux. It is deliberately a result record, not a claim that the watchdog is
ready for deployment.

## Protocol

- Host: AWS `c8g.4xlarge` (Graviton), `aarch64`, Ubuntu 22.04 kernel
  `6.8.0-1061-aws`.
- Frozen split: train on `north-approach-right-turn`; calibrate on
  `npc1-crossing-route`; final-test only on `npc3-crossing-route`.
- Three approximately 45-second clean bags were used per route family.
- The 25-tree Isolation Forest was trained on 25,542 train-route ticks.
- Hybrid thresholds were frozen on 24,224 validation-route ticks with a
  predeclared 1% clean-FPR budget. Observed validation FPR was 0.409%.
- The final model and threshold were then fixed. The final route was never an
  input to training or calibration.

The private raw bags, frozen model, JSON reports, benchmark, and SHA-256
manifest are in:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/final-arm-route-validation-20260804/
```

## Held-out final route result

The untouched final cohort contained 27,029 clean feature ticks across three
recordings. It produced **0 false-positive ticks (0.000%)**.

| Injected fault | Detected runs | Detection rate | Time-to-detect (ms) |
| --- | ---: | ---: | --- |
| Vanish | 3 / 3 | 100% | p50 63.4; p99 140.6 |
| Phantom | 3 / 3 | 100% | p50 60.2; p99 97.8 |
| Teleport | 3 / 3 | 100% | p50 62.0; p99 143.5 |
| Freeze | 2 / 3 | 66.7% | p50 660.6; p99 1,256.8 |
| Confidence collapse | 0 / 3 | 0% | not detected |
| Perception hang | 0 / 3 | 0% | not detected |

These are stream-replay measurements, not vehicle stopping distances and not a
claim of safety certification. In particular, the current offline hybrid does
not implement liveness as a model-evaluation feature path; live liveness is a
separate node option.

## Safe-stop service response

One integrated native-Arm phantom trial used the same frozen model and enabled
the actual Autoware `SetStop` service (not dry-run mode). Autoware accepted the
request. The watchdog-to-service-response interval was **11.026 ms** after the
safe-stop request was issued. The observed fault-to-stop interval was 11.300 s
in this simulator trial, so it must not be presented as a millisecond
end-to-end safety latency claim.

## Frozen-model Arm profile

The frozen hybrid model is 367,900 bytes. A 10,000-sample native-Arm scoring
benchmark on a final-route stream measured:

| Metric | Result |
| --- | ---: |
| p50 inference | 805.743 µs |
| p95 inference | 836.956 µs |
| p99 inference | 991.062 µs |
| Mean inference | 812.959 µs |
| Steady-state workload | 1,227.23 ticks/s during 16.86 s of scoring |

The workload was prepared for Arm Performix, but a new Performix export was
not captured in this run: macOS needs the Session Manager plugin installed by
an administrator before its private SSM tunnel can start. Do not substitute the
native benchmark for a Performix report; rerun the documented recipe after
that local prerequisite is installed.
