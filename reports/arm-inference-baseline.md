# Arm Inference Baseline

This is a native Arm Linux scoring microbenchmark for the frozen Second Sight
hybrid baseline. It measures model scoring only; it is not an end-to-end fault
detection or safe-stop latency result.

## Environment

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney)
- Architecture: `aarch64`
- Kernel/platform: `Linux 6.8.0-1061-aws` with glibc 2.35
- Python: 3.12.13
- Harness revision: `6ee8bf9`

## Frozen inputs

- Detector: normal-only hybrid (300-tree Isolation Forest plus guardrails)
- Model size: 3,151,108 bytes (3.0 MiB)
- Model SHA-256:
  `7d32d0b80ee37b26b5c662f9c0957a554a436c89fb317d21976659b1e50f8f32`
- Clean replay stream: 347 feature rows
- Stream SHA-256:
  `2e3ef61ee3a248bad6fb5d16427f46a07441ec7622d7a59a69a1c53bb4946bff`
- Benchmark configuration: 1,000 warm-up ticks and 10,000 measured ticks

The complete frozen-input manifest is
[`configs/baselines/hybrid-overnight-20260717.yaml`](../configs/baselines/hybrid-overnight-20260717.yaml).

## Results

| Metric | Per-tick scoring latency |
| --- | ---: |
| Minimum | 5.971 ms |
| Mean | 6.064 ms |
| p50 | 6.051 ms |
| p95 | 6.150 ms |
| p99 | 6.284 ms |
| Maximum | 20.576 ms |

## Interpretation and limits

The result is a reproducible native-Arm baseline for comparing optimized
candidate models against the same artifact/input protocol. It does not include
ROS serialization, feature extraction, DDS transport, fault-to-alert latency,
safe-stop service latency, CPU overhead, memory use, or Arm Performix output.
Those measurements remain required before making an end-to-end performance
claim.
