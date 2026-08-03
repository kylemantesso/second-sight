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

## No-leakage configuration baseline

The bundled Open AD Kit source contains one map scenario with two planner
configurations (`pass` and `fail`); it does not yet provide genuinely different
routes. The following repeatable baseline trains only on `pass` clean features
and evaluates the disjoint `fail` cohort clean and with deterministic injected
faults. It rejects hold-out recordings with fewer than 300 complete ticks, so
every six-fault scenario has an evaluable interval:

```bash
./scripts/run-heldout-configuration-validation.sh heldout-pass-train-fail-eval pass fail
```

The output explicitly labels itself a held-out *configuration* result. It is
useful leakage-resistant evidence, but it must not be presented as varied-route
generalization. Run the complementary `fail pass` split before drawing even a
configuration-level conclusion. New route/traffic scenarios are still required
for a varied-route claim.

The current two-direction result and its high held-out clean false-positive
rates are documented in
[`../reports/heldout-configuration-validation.md`](../reports/heldout-configuration-validation.md).

## Route-family validation before collection

Before using a candidate as a training, validation, or final-test route family,
generate it and make one 45-second smoke recording. Confirm it contains both
the detection-object and planning-trajectory topics; a successfully created
bag alone is not enough. Preserve the route identifier in the bag name:

```bash
./scripts/openadkit.sh generate-routes
OPENADKIT_ROUTE_ID=north-approach-right-turn \
OPENADKIT_SCENARIO_PATH=/autoware/scenario-sim/scenario/second-sight-north-approach-right-turn.yaml \
OPENADKIT_TIMEOUT=180 \
./scripts/openadkit.sh record 45
```

Do not tune the model or thresholds against the designated final-test route.
Only after at least three simulator-validated route families exist should the
clean corpus be split into train, validation, and untouched final-test cohorts.

The validated slow- and fast-traffic profiles are useful additional normal-data
cohorts on the same north-approach route. They may improve feature coverage,
but they are not separate route families and must not be described as
varied-route test evidence. Their Arm validation record is
[`../reports/traffic-variant-validation.md`](../reports/traffic-variant-validation.md).

## Frozen final Arm route split

The final split is defined by the committed, frozen manifest
[`../configs/cohorts/final-arm-route-split-20260804.yaml`](../configs/cohorts/final-arm-route-split-20260804.yaml).
It assigns one validated ego-route family each to training, validation, and the
untouched final test. Route IDs are matched as complete filename prefixes, so
hyphens cannot cause a final-test recording to leak into an earlier cohort.

After collecting the required clean Arm recordings, export them without
training a model:

```bash
./scripts/process-clean-data.sh configs/cohorts/final-arm-route-split-20260804.yaml
```

Then run the immutable final pipeline once on Arm Linux:

```bash
./scripts/run-final-route-validation.sh final-arm-route-20260804 \
  configs/cohorts/final-arm-route-split-20260804.yaml
```

The runner trains a 25-tree forest on the train route only. It freezes the
forest and guardrail thresholds using only clean validation data, with a
predeclared 1% clean-FPR budget split between the two hybrid branches. Only
then does it score the untouched final-test route clean and after all six
deterministic faults. It refuses to overwrite an existing run ID and writes
SHA-256 hashes for the manifest, models, reports, and scenario definitions.
