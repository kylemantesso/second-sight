# Arm 25-Tree Optimization Result

This report compares the frozen Second Sight hybrid baseline with a smaller
candidate on the same native Arm Linux host and scoring workload. It is a
model-scoring microbenchmark only, not a measurement of fault-to-stop latency.

## What changed

The candidate reduces the Isolation Forest from 300 to 25 trees. It retains
the same normal-only guardrails, feature set, clean-training rows, and frozen
evaluation protocol as the baseline. No injected fault was used to fit either
model or its guardrails.

## Arm scoring result

- Host: AWS `c8g.4xlarge`, `ap-southeast-2a` (Sydney), `aarch64`
- Platform: Ubuntu 22.04 / Linux `6.8.0-1061-aws`, glibc 2.35
- Python: 3.12.13
- Harness revision: `e7652bb`
- Workload: 347-row clean replay stream, repeated after exhaustion
- Protocol: 1,000 warm-up ticks followed by 10,000 measured ticks
- Aggregation: per-tick wall-clock latency; percentiles are calculated over the
  10,000 measured ticks

| Metric | 300-tree baseline | 25-tree candidate | Reduction |
| --- | ---: | ---: | ---: |
| Model artifact | 3,151,108 bytes (3.0 MiB) | 253,011 bytes (247 KiB) | 92.0% |
| Mean | 6.064 ms | 785.8 µs | 87.0% |
| p50 | 6.051 ms | 778.7 µs | 87.1% |
| p95 | 6.150 ms | 809.3 µs | 86.8% |
| p99 | 6.284 ms | 918.5 µs | 85.4% |
| Maximum | 20.576 ms | 15.887 ms | 22.8% |

The candidate therefore cuts artifact size by 92.0% and median scoring latency
by 87.1% under this controlled Arm workload.

## Frozen quality check

Both variants were evaluated with the same 347-tick, fixed-route replay and
the same six injected fault intervals. The candidate hybrid detected all six
faults. Its false-positive rate was 0.730% (1 of 137 normal ticks), the same
as the frozen baseline result.

| Fault | Candidate detected | Time to first detection |
| --- | ---: | ---: |
| Vanish | Yes | 1,538.6 ms |
| Phantom | Yes | 37.1 ms |
| Freeze | Yes | 38.9 ms |
| Teleport | Yes | 38.9 ms |
| Confidence collapse | Yes | 37.1 ms |
| Perception hang | Yes | 30.0 ms |

The 25-tree forest alone had a 0% false-positive rate on this stream but did
not detect any of these six injected intervals. The hybrid result above is
driven by its normal-only guardrails. This is intentional safety evidence for
the hybrid, but it is not evidence that the reduced forest improves fault
detection quality.

## Reproducibility

The baseline's frozen input manifest is
[`configs/baselines/hybrid-overnight-20260717.yaml`](../configs/baselines/hybrid-overnight-20260717.yaml).
The candidate uses the same clean stream, fault stream, ground truth, and
scenario recorded there. Its artifacts are retained in private benchmark
storage so raw data is not published:

- Candidate model SHA-256:
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Candidate metadata SHA-256:
  `022d97ec6844abf8e63bad051b522e815b073da14e680f1753ef30c2267fe1ce`
- Candidate raw Arm output:
  `runs/arm-candidate-25tree-20260802/arm-inference-25tree.json`

The original Arm baseline is documented in
[`arm-inference-baseline.md`](arm-inference-baseline.md), and the command and
measurement method are documented in [`docs/benchmarking.md`](../docs/benchmarking.md).

## Limits and next validation

This is one native-Arm scoring run over one fixed-route replay. It excludes
ROS/DDS serialization, feature extraction, scheduling contention, anomaly to
safe-stop-request time, and vehicle stopping response. It includes neither CPU
or memory overhead nor Arm Performix output. The six fault results are a
frozen, known-fault test; they are not a held-out or varied-route detection-rate
claim. The next validation is repeated live ROS end-to-end instrumentation,
CPU/memory collection, Arm Performix, and varied-route held-out evaluation.
