# Baseline Training

The baseline is an Isolation Forest trained only on clean driving features.
Training is bounded work, not an iterative neural-network process: it finishes
after building the configured number of trees and does not improve by being
left running overnight.

## Extract Features

```bash
uv run second-sight features \
  data/processed/openadkit-clean-20260716T112843Z.jsonl \
  --output data/processed/openadkit-clean-features.csv
```

The extractor uses trajectory messages as 10 Hz ticks and carries forward the
latest detection frame. It computes 32 features covering object counts,
confidence, movement, timing/liveness, distance, and trajectory geometry. Two
persistent-track features remain experimental and are excluded from the
30-feature production model because Autoware detections do not provide stable
IDs in this scenario.

## Train

```bash
uv run second-sight train \
  data/processed/openadkit-clean-features.csv \
  --output models/isolation-forest.joblib
```

Multiple clean feature files may be supplied. The saved model includes a
standardizer, a deterministic 300-tree Isolation Forest, a training-derived
99th-percentile threshold, and metadata.

After an overnight collection, batch-export every bag, extract each feature
dataset, and retrain with one resumable command:

```bash
./scripts/process-clean-data.sh
```

Existing streams and feature CSVs are skipped, so rerunning the command safely
continues after an interruption. The batch training command excludes recordings
with fewer than 300 complete ticks, preventing short startup fragments from
dominating the baseline.

## Evaluate

```bash
uv run second-sight evaluate \
  data/processed/openadkit-all-faults.jsonl \
  --model models/hybrid-overnight.joblib \
  --ground-truth data/processed/openadkit-all-faults.ground-truth.json \
  --mode hybrid \
  --output reports/hybrid-evaluation.json
```

Evaluation modes are `isolation_forest`, `guardrails`, and `hybrid`. The
normal-only guardrails persist clean feature ranges in the model artifact; the
hybrid flags a tick when either detector fires. Reports include fault latency,
triggering features, false-positive rate, and a documented 500 ms post-fault
recovery exclusion.

## Overnight Work

Do not loop training on the same data overnight. Instead, collect clean bags
covering different routes, object counts, speeds, and traffic conditions, then
export and extract each recording. Retraining once on the expanded set should
still take seconds or minutes.

The current Open AD Kit scenario can be collected repeatedly while alternating
its passing and stopping planner configurations:

```bash
./scripts/collect-clean.sh start 8
./scripts/collect-clean.sh status
./scripts/collect-clean.sh logs
./scripts/collect-clean.sh stop
```

The job runs in the background, records 45 seconds per iteration, stops after
the requested number of hours, and stops early if free disk falls below 10 GB.
Closing the terminal does not stop it. The laptop must remain powered on with
Docker Desktop running; prevent macOS from sleeping while collecting.

This repeated fixed-route scenario improves sample count and includes two
planner configurations, but it is still less valuable than genuinely varied
routes and traffic. Do not treat repeated runs as independent evidence for a
final detection-rate claim.

The current 35-second recording is enough to validate the pipeline but not to
support a credible detection-rate claim. Final model selection and every
performance claim must use broader clean data and Arm Linux measurements.
