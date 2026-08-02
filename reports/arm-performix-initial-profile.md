# Initial Arm Performix Profile

This is the first official Arm Performix profile of Second Sight's steady-state
25-tree watchdog scoring loop. It is a profiling baseline, not a latency or
safety claim.

## Environment

- Arm Performix desktop version 2026.3.1; CLI/engine 1.20.0
- Target: AWS `c8g.4xlarge`, `ap-southeast-2a`, Ubuntu 22.04.5,
  kernel `6.8.0-1061-aws`, 16 Arm Neoverse-V2 cores (`aarch64`)
- Revision: `5b68270`
- Model: 25-tree hybrid bundle, 253,011 bytes, SHA-256
  `7898cf52d8f2c28f65373902b275413690f84ce11b51ec9a5b562523daaf60e4`
- Stream: frozen clean portable stream, SHA-256
  `2e3ef61ee3a248bad6fb5d16427f46a07441ec7622d7a59a69a1c53bb4946bff`
- Workload: `scripts/performix-watchdog-workload.py`, hybrid scoring mode,
  5,000 warm-up ticks, launched by Performix for a 60-second profile window
- Transport: SSH to a loopback AWS Systems Manager tunnel; no public inbound
  SSH rule was opened

## System Utilization

Performix run `2943bef3f2ed` collected 120 samples at a 0.5-second interval.
The workload completed 68,725 steady-state scores over 55.215 seconds
(1,244.672 ticks/second) before the recipe stopped it.

| Metric | Observed value | Scope |
| --- | ---: | --- |
| Mean total CPU | 6.465% | Whole 16-core host |
| Highest average core | Core 6: 99.967% | Whole host, per-core |
| Mean memory used | 2.617% | Whole host, not process RSS |
| Mean I/O wait | 0.003% | Whole host |

This is an expected single-threaded inference shape: one core is saturated,
while the rest of the host, memory subsystem, and storage remain lightly used.
The memory value must not be reported as Second Sight's container or process
memory usage.

## Code Hotspots

Performix run `37557c6e8ed5` sampled the same workload for 60 seconds. It
recorded 62,563 function self samples across 994 functions. The workload
completed 53,493 scoring ticks over 53.844 seconds during profiling
(993.489 ticks/second). Profiling changes execution overhead, so this rate is
for run interpretation only and is not a benchmark comparison.

| Top self-sampled function | Image | Samples | Share of function self samples |
| --- | --- | ---: | ---: |
| `_PyEval_EvalFrameDefault` | `python3.12` | 18,967 | 30.32% |
| `_PyObject_Malloc` | `python3.12` | 2,125 | 3.40% |
| `_PyObject_Free` | `python3.12` | 1,761 | 2.81% |
| `PyDict_GetItemWithError` | `python3.12` | 1,173 | 1.87% |
| `ufunc_generic_fastcall` | NumPy | 1,132 | 1.81% |
| sklearn tree `_apply_dense` | `_tree` extension | 455 | 0.73% |

The current scoring path is therefore dominated by Python frame execution and
temporary-object handling, rather than by the small forest's tree traversal.
This identifies the next legitimate optimization direction: reduce Python
per-tick overhead with a compiled/vectorized scoring path, then re-run the
same Performix recipes and compare exported runs. Do not claim an improvement
until that A/B measurement exists.

## Artifact integrity and limits

Unmodified Performix exports and SHA-256 checksums are private:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/arm-performix-initial-20260803/
```

The profile measures a frozen, single-process scoring workload on one Arm
host. It does not measure ROS/DDS end-to-end latency, cross-instance isolation,
vehicle response, or performance under live simulator contention.
