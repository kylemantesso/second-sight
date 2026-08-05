# Second Sight v2 validation runbook

V2 adds three deterministic safety paths around the existing 25-tree hybrid
model: perception liveness, confidence health, and source freshness. It is a
research prototype for a simulator; it is not a certified safety system.

V1 evidence remains immutable. The previously held-out `npc3-crossing-route`
may be used only as a known-route regression check. The first v2
`straight-through-intersection` run was observed while correcting a
route-invariance defect, so it is also regression-only. V2's headline final
result uses an unseen `straight-through-exit` cohort. That completed result is
recorded in [`../reports/v2-final-arm-route-validation.md`](../reports/v2-final-arm-route-validation.md).

## Freeze the new cohort

On the Graviton host, generate and smoke-test the candidate before collecting
or tuning anything against it:

```bash
./scripts/openadkit.sh generate-routes
OPENADKIT_ROUTE_ID=straight-through-exit \
OPENADKIT_SCENARIO_PATH=/autoware/scenario-sim/scenario/second-sight-straight-through-exit.yaml \
OPENADKIT_TIMEOUT=180 \
./scripts/openadkit.sh record 45
```

Export the resulting bag and confirm that it has complete detection and
trajectory streams. If that smoke fails, stop the v2 final evaluation; do not
replace it with an existing route or a traffic-only variation. If it passes,
copy `configs/cohorts/v2-arm-route-split.template.yaml` to a dated manifest,
record the evidence, set `frozen: true`, and commit it before collecting the
three final-route clean recordings.

## Train, calibrate, and evaluate

Process all clean bags using the frozen manifest, then run the existing
immutable route pipeline with a new run ID:

```bash
./scripts/process-clean-data.sh configs/cohorts/v2-arm-route-split-YYYYMMDD.yaml
./scripts/run-final-route-validation.sh v2-arm-route-validation-YYYYMMDD \
  configs/cohorts/v2-arm-route-split-YYYYMMDD.yaml
```

The calibration command now receives validation event streams as well as CSV
features. It allocates the 1% clean-FPR budget across the forest, generic
guardrails, confidence monitor, and freshness monitor. Liveness uses 1.5 times
the maximum clean validation detection gap, with a 300 ms minimum. The frozen
metadata records every threshold and its clean-data source.

Generic guardrails deliberately use only frame-to-frame movement and object
change signals. Absolute traffic counts, class mix, confidence, and source age
vary legitimately by route or middleware source; they remain model inputs or
belong to their dedicated monitors rather than hard scene-composition bounds.

The final report distinguishes planning-tick and detection-frame denominators,
and records the first decision path for every injected fault. Do not combine
their raw counts into an unqualified per-frame rate. Report the measured
headline clean-FPR and detection outcomes exactly as written by the final run.

## Integrated Arm validation

With the new frozen model on the Graviton host, run three accepted-service
trials for each unique safety path:

```bash
./scripts/run-v2-live-validation.sh v2-live-YYYYMMDD \
  models/v2-arm-route-validation-YYYYMMDD-frozen-25tree.joblib 3
```

This intentionally stops if a scenario triggers through an unexpected path.
It proves a request and Autoware service response, not braking distance or
end-to-end vehicle safety latency.

Finally re-run the native inference benchmark and a Performix System
Utilization recipe against the frozen v2 model and new final-route stream.
Archive unmodified reports, checksums, Docker image digests, raw bags, and the
Performix export under a new private S3 run prefix. The completed V2 archive
includes the raw and processed streams, model, all live traces, the Performix
export, and checksum manifests.

## Cost guardrail

The `c8g.4xlarge` costs about US$0.01384/minute while running. Stop it between
steps, retain each start/stop record in `docs/aws-costs.md`, and stop v2 work
before additional AWS spend reaches the approved US$30 ceiling.
