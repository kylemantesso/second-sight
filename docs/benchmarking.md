# Arm Benchmarking

Second Sight reports performance only from native Arm Linux. macOS is used for
correctness and development; it is not a submission benchmark environment.

## Baseline inference benchmark

Run the persisted model against a frozen portable event stream on the Arm host:

```bash
uv run second-sight benchmark \
  data/processed/openadkit-clean-20260716T112843Z.jsonl \
  --model models/hybrid-overnight.joblib \
  --output reports/benchmarks/baseline-inference.json \
  --mode hybrid \
  --warmup 1000 \
  --samples 10000 \
  --host-label aws-c8g.4xlarge-ap-southeast-2a
```

The command records the model and stream SHA-256 hashes, artifact size, host
architecture and software details, run settings, and per-tick inference
latency (minimum, mean, p50, p95, p99, and maximum). It repeats the recorded
feature rows when the requested sample count exceeds the recording length.

This is a microbenchmark of model scoring, not end-to-end safety latency.
End-to-end reports must separately measure the injector timestamp, anomaly
decision, safe-stop request, and stop-service response across repeated runs.
The implemented same-host live instrumentation and its limits are documented in
[`latency-instrumentation.md`](latency-instrumentation.md).

## Required report context

Every published Arm result must identify:

- Arm host and instance type, OS, and architecture;
- source revision, Docker image digests, model hash, and model size;
- stream hash, warm-up count, sample count, and aggregation method;
- CPU/memory measurement method; and
- Arm Performix output where applicable.

## Arm Performix status

Arm Performix is an Arm Account-gated service. On 2026-08-02, the official
[Performix page](https://www.arm.com/products/development-tools/performix)
redirected an unauthenticated request to Arm Account login, and no `performix`
or `arm-performix` executable was installed on the Arm benchmark host. No
Performix result has therefore been claimed or added to any report.

Once an authorised project account has access, run the official Performix flow
against the documented 25-tree watchdog workload on the same Graviton host,
retain its unmodified output in the private artifact bucket, and add the run
identifier, command/configuration, host facts, and output location to the
relevant Arm report. Do not substitute a local microbenchmark for Performix.

Store raw benchmark outputs under `reports/benchmarks/` locally or in the
project's private benchmark-artifact storage. Generated reports are excluded
from Git; publish their methodology and relevant measured summary instead.
