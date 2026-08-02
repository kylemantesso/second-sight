# Arm Perception Fast-Path Validation

This report records an initial, one-run-per-fault validation of the opt-in
Second Sight fast path. It is diagnostic evidence, **not** a statistical
benchmark or a submission-ready end-to-end safety claim.

## What changed

The reference detector scores only when a new planning trajectory arrives.
The experimental fast path scores a safe subset of normal-only guardrails on
each perception message instead. A separate watchdog timer detects an absence
of perception messages after the stream has started.

The fast guardrails deliberately exclude `max_relative_object_displacement_m`
and `unexpected_object_drop_count`: their values require same-tick ego-pose
context, and using them from a cached trajectory produced clean-stream false
positives. Teleport remains covered by the reference trajectory-hybrid path.

## Environment and validation protocol

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), `aarch64`
- OS: Ubuntu 22.04, Linux `6.8.0-1061-aws`
- Model: 25-tree hybrid bundle, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Stack: Open AD Kit simulator, fault injector, planning control, Second
  Sight, and latency monitor on the same host
- Stop mode: dry run; the final timing point is the watchdog's stop-request
  issuance, not service acknowledgement or vehicle deceleration

Before fault injection, the fast guardrails plus 300 ms liveness timer replayed
29 seconds of a clean 10 Hz portable perception stream without a fast-path
anomaly, liveness timeout, or stop request. This is a smoke test only; it is
not a false-positive-rate estimate.

Each row below is one fresh-stack run of the corresponding deterministic
scenario. The monitor uses `time.monotonic_ns()` shared by all containers on
this host. Raw JSONL, Docker resource samples, and provenance files are private
artifacts, not committed to the repository.

## Initial results

| Fault | First decision path | Fault → anomaly | Fault → stop request | Decision scoring time |
| --- | --- | ---: | ---: | ---: |
| Vanish | `perception_guardrails` | 2.610 ms | 102.696 ms | 1.517 ms |
| Phantom | `perception_guardrails` | 3.039 ms | 102.869 ms | 1.492 ms |
| Freeze | `perception_guardrails` | 2.845 ms | 102.810 ms | 1.558 ms |
| Teleport | `trajectory_hybrid` | 14,538.225 ms | 14,637.385 ms | 1.577 ms |
| Confidence collapse | `perception_guardrails` | 2.908 ms | 102.873 ms | 1.574 ms |
| Perception hang | `perception_liveness_timeout` | 238.402 ms | 238.921 ms | n/a (timer) |

The approximately 100 ms anomaly-to-stop interval for the four perception
guardrail rows is intentional: the fast path requires two consecutive anomalous
detections and the source runs at about 10 Hz. The liveness timer is configured
for 300 ms from the last received detection. Its interval starts at the
injector's first suppressed scheduled detection, so the observed 238 ms is not
the timeout setting itself.

The first five rows were recorded at source revision `6f49642`; the liveness
row was recorded at `3496de7`. Both use the same model hash and Arm host. The
legacy decision event did not carry its path in the earlier trace; the
teleport stop event identifies `trajectory_hybrid`. Current instrumentation
records both decision and stop paths.

## Interpretation and limits

The fast path reached the first decision in roughly 3 ms for four injected
perception corruptions and the liveness timer stopped a stream hang in under
239 ms in these single runs. It did **not** accelerate teleport: that fault is
currently detected by the trajectory-hybrid reference path.

Do not turn these values into p50/p95/p99 figures, detection rates, or a
general safety claim. The next validation work is to repeat independent trials
per fault, evaluate broader held-out clean routes for false positives, capture
the stop-service response, and separately develop a held-out-safe teleport
signal before describing the fast path as complete.

## Private artifacts

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-fast-path-validation-20260802/
```

The prefix contains 18 objects: JSONL timing traces, resource TSVs, and
provenance text for six runs.
