# Arm Live Latency Validation

> Superseded for timing interpretation: the later repeated validation found
> that the short simulator can naturally end before a delayed trajectory-gated
> decision, allowing end-of-stream behavior to be associated with the pending
> fault. Preserve this report as historical instrumentation evidence only; do
> not cite its latency table. The valid repeated fast-path results are in
> [`arm-fast-path-repeated-validation.md`](arm-fast-path-repeated-validation.md).

This is an initial native-Arm validation of the live Second Sight path. Every
one-fault scenario produced a fault timestamp, anomaly decision, and dry-run
safe-stop request. It is **not** a statistical latency benchmark: there is one
fresh-stack run per fault type, no p50/p95/p99, and no Arm Performix result.

## Environment and protocol

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), `aarch64`
- OS: Ubuntu 22.04, Linux `6.8.0-1061-aws`
- Source revision: `e92ba2f562e29c297c994f12c578c035ee5c7c86`
- Detector: 25-tree hybrid candidate, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Stack: Open AD Kit simulator, fault injector, planning control, Second Sight,
  and latency monitor on the same Arm host
- Stop mode: dry run; the measurement ends when Second Sight issues its
  safe-stop request, not at an Autoware service response or vehicle stop

Each trial used a fresh stack and one scenario from
[`configs/scenarios/latency/`](../configs/scenarios/latency/). The latency
monitor uses the shared host's `time.monotonic_ns()` clock. It records the
interval immediately before the first modified or suppressed detection through
the first anomalous decision and latched safe-stop request.

## One-run validation results

| Fault | Fault → anomaly | Fault → stop request | Scoring time at decision |
| --- | ---: | ---: | ---: |
| Vanish | 13,690.191 ms | 13,789.862 ms | 1.567 ms |
| Phantom | 15,688.031 ms | 15,793.576 ms | 1.568 ms |
| Freeze | 16,489.574 ms | 16,590.961 ms | 1.567 ms |
| Teleport | 14,490.138 ms | 15,397.001 ms | 1.572 ms |
| Confidence collapse | 10,495.767 ms | 10,593.587 ms | 1.597 ms |
| Perception hang | 15,788.530 ms | 16,690.304 ms | 1.562 ms |

The roughly 10–16 second end-to-end values include the configured simulator,
ROS/DDS, planning-trajectory, feature-extraction, and two-consecutive-anomaly
path. They are not comparable to the sub-millisecond scoring microbenchmark in
[`arm-25tree-optimization.md`](arm-25tree-optimization.md). They also require
repeat trials and latency-stage investigation before appearing in submission
material.

## Resource observations

Docker stats sampled the watchdog, injector, simulator, and planning-control
containers throughout the six trials. Across 49 timestamped snapshots, the
watchdog used 6.25% mean Docker CPU (23.65% maximum) and 107.6 MiB mean memory
(114.3 MiB maximum). Its mean share of the four-container CPU sum was 1.45%
(3.95% maximum).

These are diagnostic observations, not a full-stack overhead claim. Docker CPU
percentages can exceed 100% on a multicore machine; the stated share uses only
the four named containers, excludes dashboard/visualizer and host processes,
and includes simulator startup work. The raw TSV timestamps, not a nominal
sampling interval, define the actual sampling cadence.

## Artifact integrity and limits

The private artifact set is retained at:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-live-validation-20260802/
```

It contains six JSONL timing traces, six resource TSVs, six provenance files,
and `SHA256SUMS`. It is intentionally not public because benchmark artifacts
may contain generated simulation data. The public report preserves the host,
revision, model hash, method, and observed values needed to audit this stage.

Next, repeat each scenario sufficiently for percentile estimates, measure the
individual simulator/DDS/planning stages that dominate the observed latency,
record the Autoware stop-service response, and run Arm Performix before making
a final end-to-end performance claim.
