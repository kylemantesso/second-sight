# Arm Portable Teleport Validation

This is one causal, native-Arm validation of the delayed teleport path. It is
an instrumentation/harness result, not a percentile benchmark or a general
false-positive claim.

## Result

| Fault | First decision path | Fault → anomaly | Fault → dry-run stop request |
| --- | --- | ---: | ---: |
| Teleport | `trajectory_hybrid` | 30.573 ms | 31.134 ms |

The decision-to-request interval was 0.560 ms. The raw trace was accepted
only while the source publisher was still running and before its first replay
cycle completed.

## Environment and protocol

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), Ubuntu 22.04,
  `aarch64`
- Source revision: `3b8f6647536db9bcd0f400b99d2ed01b5f3e0de2`
- Model: 25-tree hybrid bundle, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Scenario: `configs/scenarios/latency/teleport.yaml`
- Source: a deterministic clean 6–16-second replay window, loop-enabled but
  verified not to complete before the stop request
- Decision policy: trajectory-hybrid only, liveness and perception fast path
  disabled, `--stop-after 1` for this high-severity discontinuity experiment
- Stop mode: dry run; timing ends at request issuance, not at service
  acknowledgement or vehicle deceleration

The original raw capture begins with a natural tracking discontinuity. The
selected clean window excludes that known pre-fault artefact; its maximum
relative object displacement is about 1.001 m before injection. This makes
the run suitable for validating the causal measurement path, but it does not
establish a general false-positive rate. Held-out, varied-route clean data and
repeated runs remain required before any safety or production claim.

The latency monitor correlates producer-side `time.monotonic_ns()` timestamps
on one host. The raw JSONL, source log, provenance, and checksums are private:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-portable-teleport-validation-20260802/
```

## Why this replaces the earlier excluded teleport attempts

The first Open AD Kit teleport trials could reach natural end-of-stream before
a delayed hybrid decision. The portable runner rejects any trace whose source
reaches its first end-of-stream, requires `trajectory_hybrid` attribution, and
uses an explicit 20-second causal bound. It also waits for DDS discovery and
correlates telemetry even if fault, decision, and stop topics are delivered in
different orders.

One sample is insufficient for percentiles. The next measurement step is a
fresh-process repeated set using the same source and policy, followed by a
separate varied-route quality evaluation.
