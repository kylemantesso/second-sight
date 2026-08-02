# Arm Guardrail Fast-Path Optimization

This report records a native-Arm A/B scoring benchmark for Second Sight's
**perception guardrail fast path**. It is a scoring microbenchmark, not an
end-to-end fault-to-safe-stop latency result.

## Change

The perception fast path makes a guardrail-only decision. Before this change,
it nevertheless evaluated the full Isolation Forest for every tick, then
discarded the forest result. The optimized implementation skips that unused
forest evaluation and calculates only the selected guardrails. Hybrid and
Isolation Forest detector modes retain their existing scoring path.

This target was selected from the initial Arm Performix Code Hotspots profile:
the Python process and temporary-object handling dominated the sampled work,
while the tree extension itself was only 0.73% of function self samples. See
[`arm-performix-initial-profile.md`](arm-performix-initial-profile.md) for the
profiling evidence.

## Native Arm result

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), Arm Neoverse-V2,
  `aarch64`
- OS: Ubuntu 22.04.5, Linux `6.8.0-1061-aws`, glibc 2.35
- Python: 3.12.13
- Revision: `6ad6e45aa93d88d9891cc4e4fd2f380f5f0089a9`
- Model: 25-tree bundle, 253,011 bytes; SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Input: frozen 347-row clean stream; SHA-256
  `2e3ef61ee3a248bad6fb5d16427f46a07441ec7622d7a59a69a1c53bb4946bff`
- Protocol: 10,000 warm-up ticks, then 100,000 measured ticks; the frozen rows
  repeat after exhaustion. Percentiles are per-tick wall-clock scoring time.

| Metric | Reference: forest unnecessarily evaluated | Optimized: guardrails only | Faster |
| --- | ---: | ---: | ---: |
| Mean | 821.373 µs | 9.912 µs | 82.86× |
| p50 | 813.350 µs | 9.831 µs | 82.73× |
| p95 | 851.143 µs | 10.100 µs | 84.27× |
| p99 | 1,013.747 µs | 14.843 µs | 68.30× |
| Maximum | 21,320.945 µs | 31.409 µs | — |

Both runs reported 578 anomalous samples over the repeated input. The headline
result is therefore an **82.7× lower p50 guardrail-only scoring time** for the
opt-in perception path on this Arm host.

## Decision-equivalence checks

The reference and optimized implementations were compared field-for-field for
the values that drive the fast-path response: anomaly decision, guardrail
score, and triggering guardrail features.

- Clean stream: all 347 feature rows were equivalent.
- Injected-fault stream: all 347 feature rows were equivalent on the same
  `aarch64` host; 137 rows were anomalous. Its SHA-256 is
  `b93e1bc76435d0b37990b4ec60bd2c8651b19df0f097d07032b96bce00ca358d`.

`forest_score` is intentionally absent (`None`) from the optimized result: no
forest work occurs. The perception ROS node neither publishes nor relies on
that field. This validation does not change hybrid trajectory scoring, or
assert equivalence for modes that are intentionally outside this optimization.

## Reproducibility and artifacts

The benchmark harness supports both implementations explicitly:

```bash
uv run second-sight benchmark .benchmark-artifacts/clean-stream.jsonl \
  --model models/hybrid-25tree.joblib \
  --output reports/benchmarks/guardrails.json \
  --mode guardrails \
  --implementation optimized \
  --warmup 10000 \
  --samples 100000 \
  --host-label aws-c8g.4xlarge-ap-southeast-2a
```

Use `--implementation reference` for the comparison arm. The raw JSON outputs,
host metadata, and SHA-256 manifest are retained unchanged in private artifact
storage:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-guardrail-optimization-20260803/
```

## Limits

This is one microbenchmark on a frozen replay. It excludes ROS/DDS transport,
feature extraction, scheduling contention, cross-instance isolation, anomaly
to-stop-request time, stop-service response, and vehicle braking. It must not
be presented as an 82× improvement to hybrid scoring or to end-to-end safe-stop
latency. The previous Arm Performix run identified the optimization direction;
this A/B latency comparison is a separate native-host benchmark rather than a
Performix latency measurement.
