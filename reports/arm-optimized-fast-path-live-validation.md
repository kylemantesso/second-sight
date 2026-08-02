# Arm Optimized Fast-Path Live Validation

This is a post-optimization, repeated live validation of Second Sight's
opt-in perception watchdog on native Arm Linux. It confirms that the optimized
guardrail-only implementation continues to issue the expected safe-stop
request in the integrated simulator path. It is not a vehicle-braking,
cross-machine-isolation, or field-safety result.

The scoring optimization itself is measured separately in
[`arm-guardrail-fast-path-optimization.md`](arm-guardrail-fast-path-optimization.md):
it removes an unused Isolation Forest calculation from this guardrail-only
path. The live numbers below include ROS 2/DDS and scheduling, so they must
not be used to attribute an end-to-end speedup solely to that code change.

## Protocol

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), Arm Neoverse-V2,
  `aarch64`
- OS: Ubuntu 22.04, Linux `6.8.0-1061-aws`
- Source revision: `6ad6e45aa93d88d9891cc4e4fd2f380f5f0089a9`
- Model: 25-tree bundle, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Configuration: perception guardrails and the 300 ms perception-liveness
  timer enabled; dry-run safe-stop mode
- Measurement: a common-host `time.monotonic_ns()` timestamp at the injector's
  first faulty/suppressed detection, first watchdog decision, and safe-stop
  request issuance
- Sample: five fresh-container trials per fault, 25 complete traces total;
  NumPy linear-interpolated percentiles per five-run group

Every raw trace contained exactly one safe-stop request before it was admitted
to the aggregate. Teleport is deliberately excluded: the short Open AD Kit
scenario can end before its trajectory-hybrid decision is causally observed.

## Results

| Fault / first decision path | n | Fault → anomaly p50 / p95 / p99 | Fault → safe-stop request p50 / p95 / p99 |
| --- | ---: | ---: | ---: |
| Vanish / `perception_guardrails` | 5 | 1.093 / 1.188 / 1.206 ms | 101.151 / 101.602 / 101.662 ms |
| Phantom / `perception_guardrails` | 5 | 1.530 / 1.639 / 1.646 ms | 101.463 / 101.647 / 101.675 ms |
| Freeze / `perception_guardrails` | 5 | 1.253 / 1.346 / 1.361 ms | 101.293 / 101.377 / 101.385 ms |
| Confidence collapse / `perception_guardrails` | 5 | 1.337 / 1.344 / 1.344 ms | 101.405 / 101.831 / 101.910 ms |
| Perception hang / `perception_liveness_timeout` | 5 | 213.830 / 259.620 / 268.642 ms | 214.336 / 260.131 / 269.151 ms |

For the four perception corruptions, the roughly 100 ms interval from anomaly
to request is deliberate: the policy requires two consecutive anomalous
detections and the source is approximately 10 Hz. The liveness interval starts
at the first suppressed scheduled detection, so it is appropriately below the
nominal 300 ms timer value.

## Artifacts and reproducibility

The validation runner is:

```bash
./scripts/run-live-fast-path-validation.sh arm-fast-optimized-20260803 5
```

It rebuilds the integrated stack and records Docker image digests for the four
measured containers in each run's metadata. The checked private artifact prefix
contains 25 JSONL traces, 25 resource TSVs, 25 provenance files, a
machine-readable summary, and a SHA-256 manifest (77 objects, 85,077 bytes):

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-fast-optimized-validation-20260803/
```

The local download independently verified every manifest checksum and recreated
the same latency values. The only expected differences in the regenerated JSON
are the summary creation time and local source-path prefixes.

## Scope and limits

These deterministic fixed-route runs measure only fault injection through
watchdog safe-stop *request issuance* on one Arm host. They exclude physical
braking, planning-service acknowledgement, ROS/DDS transport between separate
machines, and clean-route false-positive-rate estimation. The Docker resource
TSVs include short container start-up and teardown periods, so they are retained
for audit but are not a stable watchdog CPU-overhead claim. A longer steady-state
resource run and varied held-out routes remain necessary before using this as a
submission-wide safety or resource metric.
