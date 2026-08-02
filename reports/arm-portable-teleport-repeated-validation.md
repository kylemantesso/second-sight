# Arm Portable Teleport Repeated Validation

Five fresh-process native-Arm trials validate the portable trajectory-hybrid
teleport timing path. This is a deterministic development validation set, not
a field-safety result or a general false-positive measurement.

## Results

| Fault / decision path | n | Fault → anomaly p50 / p95 / p99 | Fault → dry-run stop request p50 / p95 / p99 |
| --- | ---: | ---: | ---: |
| Teleport / `trajectory_hybrid` | 5 | 30.568 / 30.634 / 30.642 ms | 31.102 / 31.181 / 31.192 ms |

The observed minimum/maximum fault-to-stop interval was 31.049–31.195 ms. The
median decision-to-request interval was 0.535 ms. Percentiles use NumPy's
linear interpolation over five completed traces.

## Conditions and integrity

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a`, Ubuntu 22.04, `aarch64`
- Revision: `a9c40f8a7b27d1f806634f25025b0336c8ddd00a`
- Model: 25-tree hybrid bundle, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Scenario: `configs/scenarios/latency/teleport.yaml`
- Source: loop-enabled clean 6–16-second window; every trace was rejected if
  its publisher completed a replay cycle before the stop request
- Policy: `trajectory_hybrid`, liveness and perception fast path disabled,
  `--stop-after 1` for this explicit high-severity discontinuity experiment
- Stop mode: dry run; the measured endpoint is request issuance, not service
  acknowledgement or vehicle deceleration

Each run starts fresh fault injector, watchdog, monitor, and replay publisher
containers. The monitor uses producer-side `time.monotonic_ns()` timestamps on
one host and buffers independently delivered telemetry when necessary. Raw
JSONL, publisher logs, provenance, and checksums are private:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-portable-teleport-repeated-validation-20260802/
```

## Limits

The fixed clean window deliberately excludes the original recording's initial
tracking discontinuity, so this validates the controlled teleport experiment
only. It does not measure cross-instance latency, vehicle response, or
false-positive rate on varied held-out routes. Five deterministic repetitions
are not a production confidence interval. Arm Performix output is also still
pending Arm Account access and must remain absent from submission claims.
