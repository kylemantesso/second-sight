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

## Arm Performix

Performix is operated from the macOS host and connects privately to the Arm
target over SSH. The repeatable workload is
[`scripts/performix-watchdog-workload.py`](../scripts/performix-watchdog-workload.py):
it extracts frozen rows once, warms the 25-tree persisted model, then scores
continuously until the recipe ends it. It is suitable for resource and hotspot
profiling, but it is not a latency microbenchmark.

Start with the System Utilization recipe, then use its result to decide whether
Code Hotspots or CPU Microarchitecture is warranted. Preserve the unmodified
Performix run export in private artifact storage and record its run identifier,
recipe parameters, target facts, and workload command in the Arm report. Do
not substitute a local microbenchmark for Performix.

The private target tunnel is started on the Mac in a separate terminal:

```bash
brew install --cask session-manager-plugin
./scripts/start-performix-ssm-tunnel.sh
```

The cask installer asks for the local macOS administrator password. The tunnel
uses AWS Systems Manager and local port 2222; it does not add an EC2 inbound
SSH rule. After adding an authorised public key for the target user, configure
the bundled Performix CLI once:

```bash
APX="/Applications/Arm Performix.app/Contents/assets/apx/apx"
"$APX" target add \
  "ubuntu@127.0.0.1:2222:/absolute/path/to/private-key:auth=key" \
  --name second-sight-graviton --default --host-key-policy accept-new
"$APX" target prepare --target second-sight-graviton
```

Then invoke a recipe with the frozen 25-tree workload:

```bash
"$APX" recipe run system_utilization \
  --target second-sight-graviton \
  --working-dir /home/ubuntu/second-sight \
  --workload "/home/ubuntu/.local/bin/uv run python scripts/performix-watchdog-workload.py .benchmark-artifacts/clean-stream.jsonl --model models/hybrid-25tree.joblib --mode hybrid --warmup 5000" \
  --use-shell --timeout 60 --deploy-tools --param interval=0.5
```

The first System Utilization and Code Hotspots profiles are reported in
[`../reports/arm-performix-initial-profile.md`](../reports/arm-performix-initial-profile.md).

The resulting guardrail-only fast-path optimization is measured separately
with the native benchmark harness, including reference-versus-optimized
methodology and decision-equivalence checks, in
[`../reports/arm-guardrail-fast-path-optimization.md`](../reports/arm-guardrail-fast-path-optimization.md).
Its p50 result applies only to the opt-in perception guardrail path; it is not
an end-to-end or hybrid-detector performance claim.

Store raw benchmark outputs under `reports/benchmarks/` locally or in the
project's private benchmark-artifact storage. Generated reports are excluded
from Git; publish their methodology and relevant measured summary instead.
