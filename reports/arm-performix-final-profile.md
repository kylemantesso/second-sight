# Final Arm Performix Profile

This is the final official Arm Performix System Utilization profile of the
frozen model used by the three-route held-out evaluation. It profiles a
single-process scoring workload, not ROS/DDS end-to-end latency or vehicle
braking.

## Environment

- Arm Performix engine: 1.20.0; run ID: `2bdb1be309bc`
- Target: AWS `c8g.4xlarge`, Ubuntu 22.04.5, kernel `6.8.0-1061-aws`, 16
  Arm Neoverse-V2 cores (`aarch64`)
- Target revision: `1e638a2`
- Model: frozen 25-tree hybrid bundle, 367,900 bytes, SHA-256
  `2e38c41f12effa198e30a4c34bea99fe81a973fb15c41e2a72148db88ec599fa`
- Stream: held-out `npc3-crossing-route` clean stream, SHA-256
  `13441bfc79645a9d5f457136865404b58e897ec7b9d24e3fa2bea5bce6686394`
- Workload: `scripts/performix-watchdog-workload.py`, hybrid mode, 5,000
  warm-up ticks, 60-second recipe timeout, 0.5-second sample interval
- Transport: authenticated SSH through a loopback AWS Systems Manager tunnel;
  no public inbound SSH rule was opened.

## System Utilization

Performix collected 120 host samples. The recipe stopped the intentionally
continuous workload after 60 seconds; the workload completed 56,699
steady-state scores over 45.211 seconds (1,254.089 ticks/second) and reported
zero anomalous ticks.

| Metric | Observed value | Scope |
| --- | ---: | --- |
| Mean total CPU | 6.335% | Whole 16-core host |
| Highest average core | Core 1: 97.254% | Whole host, per-core |
| Mean memory used | 2.747% | Whole host, not process RSS |
| Mean I/O wait | 0.171% | Whole host |

The expected single-threaded shape is present: one core is nearly saturated
while aggregate host CPU, memory, and I/O wait remain low. Performix could not
create an agent cgroup under the target's current permissions, so these are
host-level measurements and must not be presented as process-only values.

## Artifact integrity and scope

The unmodified Performix export is private and has SHA-256
`4119e205f4a982bd7593e0cb7af7e46341af77fe6cb6d890db5cfb088632f326`:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/final-arm-route-validation-20260804/performix/2bdb1be309bc.zip
```

The run succeeded even though the workload received the expected interrupt at
the recipe timeout. It does not measure inference percentiles, safety latency,
cross-instance isolation, or physical stopping distance; those remain covered
by the separate native benchmark and integrated simulator evidence.
