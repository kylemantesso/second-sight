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
  --samples 10000
```

The command records the model and stream SHA-256 hashes, artifact size, host
architecture and software details, run settings, and per-tick inference
latency (minimum, mean, p50, p95, p99, and maximum). It repeats the recorded
feature rows when the requested sample count exceeds the recording length.

This is a microbenchmark of model scoring, not end-to-end safety latency.
End-to-end reports must separately measure the injector timestamp, anomaly
decision, safe-stop request, and stop-service response across repeated runs.

## Required report context

Every published Arm result must identify:

- Arm host and instance type, OS, and architecture;
- source revision, Docker image digests, model hash, and model size;
- stream hash, warm-up count, sample count, and aggregation method;
- CPU/memory measurement method; and
- Arm Performix output where applicable.

Store raw benchmark outputs under `reports/benchmarks/` locally or in the
project's private benchmark-artifact storage. Generated reports are excluded
from Git; publish their methodology and relevant measured summary instead.
