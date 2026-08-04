# Reports

Benchmark methodology and final measured results belong here. Every published
performance result must identify the Arm Linux machine, software versions,
workload, warmup, sample count, and aggregation method.

The Arm Performix hotspot profile is in
[`arm-performix-initial-profile.md`](arm-performix-initial-profile.md); its
guardrail-only fast-path A/B follow-up is in
[`arm-guardrail-fast-path-optimization.md`](arm-guardrail-fast-path-optimization.md).
The post-optimization, repeated live Arm validation is in
[`arm-optimized-fast-path-live-validation.md`](arm-optimized-fast-path-live-validation.md).
The no-leakage planner-configuration quality check is in
[`heldout-configuration-validation.md`](heldout-configuration-validation.md).
The Arm validation of controlled normal-traffic profiles is in
[`traffic-variant-validation.md`](traffic-variant-validation.md); it is not a
varied-route generalization result.

The frozen three-route Arm evaluation, including its clean false-positive rate,
per-fault held-out results, accepted Autoware stop-service response, benchmark,
and remaining limitations, is in
[`final-arm-route-validation.md`](final-arm-route-validation.md).
Its matching final Arm Performix System Utilization profile is in
[`arm-performix-final-profile.md`](arm-performix-final-profile.md).
