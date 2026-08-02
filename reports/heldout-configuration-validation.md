# Held-Out Planner-Configuration Validation

This report is a no-leakage quality check of Second Sight's normal-only hybrid
detector. It deliberately withholds one Open AD Kit planner configuration from
training, then tests that configuration both clean and with deterministic
perception faults. It is an offline macOS development result, not an Arm
performance result or varied-route generalization claim.

## What was tested

The bundled Open AD Kit source has one map scenario and two planner
configurations: `pass` and `fail`. The two leave-one-configuration-out splits
were run in both directions with a deterministic 25-tree model and the same
normal-only guardrails:

| Train clean cohort | Held-out clean cohort | Training rows | Eligible hold-out runs / ticks | Clean false-positive rate |
| --- | --- | ---: | ---: | ---: |
| `pass` | `fail` | 8,349 | 18 / 7,759 | 3.183% (247 ticks) |
| `fail` | `pass` | 8,076 | 20 / 8,349 | 8.300% (693 ticks) |

Six `fail` recordings with only 45–57 complete ticks were excluded before fault
injection because the six-fault scenario needs at least 31 seconds of source
data. They are not counted as misses or clean test ticks.

## Injected-fault result

Every fault interval in both eligible hold-out cohorts was detected: 18/18
for each fault in the `pass` → `fail` split and 20/20 in the reverse split.
The model was trained on clean data only; no injected fault stream was used to
fit either model or its guardrails.

| Fault | `pass` → `fail` time-to-detect p50 / p95 | `fail` → `pass` time-to-detect p50 / p95 |
| --- | ---: | ---: |
| Vanish | 180.8 / 744.0 ms | 149.4 / 839.6 ms |
| Phantom | 87.6 / 171.3 ms | 85.9 / 175.7 ms |
| Freeze | 80.3 / 96.4 ms | 83.7 / 134.2 ms |
| Teleport | 77.7 / 177.0 ms | 81.5 / 176.6 ms |
| Confidence collapse | 74.5 / 168.5 ms | 75.4 / 166.4 ms |
| Perception hang | 74.0 / 168.8 ms | 78.6 / 163.7 ms |

These are replay tick intervals, not live inference or fault-to-stop latency.
They must not be compared with the native-Arm live timing reports.

## Critical finding

This test **does not clear the model for deployment**. The 3.183% and 8.300%
held-out clean false-positive rates are too high for a safety watchdog. In the
`pass` → `fail` split, the most frequent normal-stream guardrail trigger was
`max_relative_object_displacement_m` (166 ticks), consistent with the planner
configuration changing the expected motion distribution.

Do not tune thresholds or remove that feature based on these hold-out results:
that would leak test information into training. The correct next experiment is
to add genuinely different normal route/traffic scenarios, reserve a third
scenario family for final testing, and choose any revised model using a separate
validation cohort.

## Reproducibility and artifacts

The reusable harness rejects short recordings and runs either direction:

```bash
./scripts/run-heldout-configuration-validation.sh \
  heldout-pass-train-fail-20260803 pass fail
./scripts/run-heldout-configuration-validation.sh \
  heldout-fail-train-pass-20260803 fail pass
```

It writes model metadata, per-stream clean and fault evaluations, aggregate
JSON, and SHA-256 manifests. The private artifacts contain 88 objects across
the two splits:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/heldout-configuration-validation-20260803/
```

The current local manifests verify. Generated data and models remain ignored;
the public repository contains the harness and the exact scenario configuration.
