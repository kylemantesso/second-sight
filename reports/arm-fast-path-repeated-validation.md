# Arm Fast-Path Repeated Validation

This is a five-run-per-fault development validation of the opt-in Second Sight
fast watchdog on Arm Linux. It provides sample percentiles, but five
deterministic runs per fault are not a final confidence or field-safety claim.

## Environment and integrity

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), `aarch64`
- OS: Ubuntu 22.04, Linux `6.8.0-1061-aws`
- Source revision: `c74e08e` (Python 3.10-compatible latency monitor)
- Model: 25-tree hybrid bundle, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Stop mode: dry run; timing ends at request issuance, not service
  acknowledgement or vehicle deceleration
- Statistics: NumPy linear-interpolated percentiles over five completed,
  fresh-stack traces per fault

The fast guardrails plus 300 ms liveness timer had already passed a 29-second,
10 Hz clean-stream smoke replay. Raw JSONL, resource TSVs, and provenance are
private artifacts. The machine-readable 25-trace summary rejects a file that
does not contain exactly one stop request.

## Valid repeated results

| Fault / first decision path | n | Fault → anomaly p50 / p95 / p99 | Fault → stop request p50 / p95 / p99 |
| --- | ---: | ---: | ---: |
| Vanish / `perception_guardrails` | 5 | 2.596 / 2.654 / 2.661 ms | 102.929 / 103.014 / 103.023 ms |
| Phantom / `perception_guardrails` | 5 | 2.974 / 3.016 / 3.022 ms | 103.019 / 103.309 / 103.364 ms |
| Freeze / `perception_guardrails` | 5 | 2.761 / 2.804 / 2.808 ms | 102.844 / 103.279 / 103.351 ms |
| Confidence collapse / `perception_guardrails` | 5 | 2.821 / 2.862 / 2.868 ms | 102.871 / 102.918 / 102.925 ms |
| Perception hang / `perception_liveness_timeout` | 5 | 251.963 / 268.067 / 269.733 ms | 252.475 / 268.587 / 270.252 ms |

The roughly 100 ms difference between fast anomaly and stop request is the
configured two-consecutive-anomaly policy at a source rate of about 10 Hz.
The liveness timer is configured from the last successful detection; its
interval starts at the first suppressed scheduled detection, so the observed
values are lower than the nominal 300 ms timeout.

## Explicit exclusion: teleport

Five teleport trial files were retained privately but excluded from the table.
Their first associated decision occurred about 13.5–14.5 seconds after the
fault timestamp, near the simulator's normal end-of-stream. One trace was
attributed to the liveness timer. That makes them unsuitable evidence for
teleport latency, even when a stop request exists. The repeat harness now
excludes teleport until the simulation is extended or a replay source can keep
the perception stream alive long enough to causally validate the slower
trajectory-hybrid path.

## Limits and next work

These results cover deterministic fixed-route faults and stop-request issuance
on one Arm host. They do not measure vehicle response, cross-machine isolation
latency, or false-positive rate on held-out routes. Next, collect varied clean
routes, repeat with a longer-running teleport source, and run Arm Performix on
the watchdog workload.

## Private artifacts

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-fast-repeated-validation-20260802/
```

The prefix contains 90 objects: 30 JSONL traces, 30 resource TSVs, and 30
provenance files. The valid public summary uses 25 traces; the five excluded
teleport traces remain available for audit.
