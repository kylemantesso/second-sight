# V2 final Arm Performix profile

This is the official Arm Performix System Utilization profile for the frozen
V2 model and held-out `straight-through-exit` stream. It profiles an offline,
single-process scoring workload; it is not a ROS/DDS end-to-end or
vehicle-braking benchmark.

## Environment and workload

- **Arm Performix run ID:** `bf79c663e38c`
- **Recipe:** System Utilization; 120 samples at 0.5-second intervals
- **Target:** AWS `c8g.4xlarge` (Graviton3E), Ubuntu 22.04, kernel
  `6.8.0-1061-aws`, 16 Arm64 vCPUs (`aarch64`)
- **Model:** frozen V2 25-tree hybrid, 368,261 bytes, SHA-256
  `5918f02f5899b4534fd5f5b06e39b020883419ac6fca3688d355b57e40596f6b`
- **Stream:** held-out
  `openadkit-clean-straight-through-exit-pass-20260805T024355Z.jsonl`
- **Workload:** optimized hybrid scorer, 5,000 warm-up ticks, then a
  continuous steady-state scoring loop

## Result

The workload completed 59,128 steady-state ticks in 44.5165 seconds:
**1,328.227 ticks/second**. It reported zero anomalous ticks on the clean
held-out stream.

| Metric | Observed value | Scope |
| --- | ---: | --- |
| Mean whole-host CPU | 6.399% | All 16 host cores |
| Highest average core | `cpu12`: 100.000% | Whole host, per-core |
| Mean whole-host memory used | 3.159% | Host memory, not process RSS |
| Mean I/O wait | 0.003% | Whole host |

The nearly saturated core with low aggregate CPU is consistent with the
single-threaded scoring loop. Arm Performix could not create its cgroup on the
target under the available permissions, so CPU and memory values are
whole-host values. They must not be represented as watchdog-process-only
resource use.

## Artifact integrity and limits

The unmodified private export has SHA-256
`19715e706687ba4d10986ba7b4a639bd88f9ef80bfe269995c8327db34736c33`:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/v2-final-arm-route-validation-20260805/performix/bf79c663e38c.zip
```

The run measures an optimized offline scorer only. It does not measure the
inference percentiles in the final report, fault detection latency, ROS/DDS
transport, safe-stop service latency, cross-machine isolation, or physical
vehicle response. Those claims have separate evidence and limitations in
[`v2-final-arm-route-validation.md`](v2-final-arm-route-validation.md).
