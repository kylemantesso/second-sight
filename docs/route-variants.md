# Route-variant validation

Second Sight needs genuinely different normal-driving route families before it
can make a varied-route quality claim. The upstream Open AD Kit checkout has a
single scenario map, so this repository generates candidate OpenSCENARIO files
from the pinned base scenario. The generated files are ignored cache artifacts;
the versioned source of truth is
[`../configs/scenarios/route-variants.yaml`](../configs/scenarios/route-variants.yaml).

## Candidates

| ID | Change from upstream route | Status |
| --- | --- | --- |
| `north-approach-right-turn` | Starts on the approximately 230 m predecessor lane, then uses the original right-turn goal. | Validated on Graviton (2026-08-03) |
| `npc1-crossing-route` | Promotes the simulator's first NPC crossing route to ego, moving that NPC clear of its original start. | Validated on Graviton (2026-08-03) |
| `npc3-crossing-route` | Promotes the simulator's third NPC crossing route to ego, moving that NPC behind the new ego start. | Validated on Graviton (2026-08-03) |
| `extended-right-turn` | Uses the original start, then continues onto the successor of the original goal lane. | Rejected: did not reach `WaitingForEngage` |
| `npc2-crossing-route` | Promotes the simulator's second NPC crossing route to ego. | Rejected: Autoware could not establish a route trajectory |

## Traffic variants

The following profiles preserve the validated north-approach ego route and all
NPC paths, changing only NPC target/controller speeds. They are independent
normal-traffic cohorts, not new map routes.

| ID | Npc1 / Npc2 / Npc3 target speed (m/s) | Status |
| --- | ---: | --- |
| `north-slow-traffic` | 5 / 5 / 4 | Validated on Graviton (2026-08-04) |
| `north-fast-traffic` | 13 / 13 / 12 | Validated on Graviton (2026-08-04) |

These definitions are not, by themselves, evidence of route diversity. A
candidate becomes usable only after a smoke recording contains both
`/perception/object_recognition/detection/objects` and
`/planning/scenario_planning/trajectory`.

## Arm validation result

The `north-approach-right-turn` smoke recording passed on native Arm Linux
(`c8g.4xlarge`, Graviton) on 2026-08-03. The 44.427-second recording contained
441 detection-object messages, 1,621 predicted-object messages, and 8,264
planning trajectories. Its 113.2 MiB ROS bag and SHA-256 manifest are private
benchmark artifacts at:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/route-variant-validation-20260803/north-approach-right-turn/
```

The SQLite bag SHA-256 is
`1dc8240599ba04eccfe6b30e26a83c2e653b6f4f666900da7686716cf1582ea3`.

The `extended-right-turn` candidate was tested with the same protocol on the
same host. The scenario runner reached `PLANNING` but failed to transition to
`WaitingForEngage`, so it published no usable route trajectory and was rejected.
It is retained in the versioned configuration only to make that negative result
reproducible; do not collect data from it.

The two validated traffic profiles are detailed in
[`../reports/traffic-variant-validation.md`](../reports/traffic-variant-validation.md).
They expand clean traffic coverage but do not satisfy the remaining requirement
for genuinely distinct route families.

## Repeatable smoke protocol

```bash
./scripts/openadkit.sh generate-routes
OPENADKIT_ROUTE_ID=north-approach-right-turn \
OPENADKIT_SCENARIO_PATH=/autoware/scenario-sim/scenario/second-sight-north-approach-right-turn.yaml \
OPENADKIT_TIMEOUT=180 \
./scripts/openadkit.sh record 45
```

`record` omits the visualizer unless `OPENADKIT_WITH_VISUALIZER=1`; that saves
memory during headless validation. Inspect the resulting bag with the existing
exporter before adding it to any data cohort.

## Local-development limitation (2026-08-03)

The first local smoke attempt loaded the north-approach scenario but did not
produce a valid bag. Docker Desktop's Linux VM was limited to 7.65 GiB while
other Docker workloads were running. Autoware components were OOM-killed, the
scenario runner then failed to set its velocity limit, and no trajectory became
available. After raising the Docker VM to 15.6 GiB, the OOM failure disappeared
but the local simulator still did not finish Autoware service initialization
reliably enough to emit a trajectory. Lowering the requested frame rate to 1 Hz
made initialization slower rather than resolving the issue.

Validate new candidates on the Graviton Linux host instead. Do not treat either
failed local attempt or the rejected extended route as a route result, use it
for training, or count it toward the required three route families (train,
validation, and untouched final test).

## Frozen final split

Three distinct ego-route families now have valid Arm smoke recordings. Their
train/validation/final-test assignment is frozen in
[`../configs/cohorts/final-arm-route-split-20260804.yaml`](../configs/cohorts/final-arm-route-split-20260804.yaml):

| Cohort | Route family | Smoke evidence |
| --- | --- | --- |
| Train | `north-approach-right-turn` | 44.427 s, 441 detection frames, 8,264 trajectories |
| Validation | `npc1-crossing-route` | 44.252 s, 441 detection frames, 8,611 trajectories |
| Final test | `npc3-crossing-route` | 44.534 s, 444 detection frames, 9,121 trajectories |

The final-test route must never be used to choose features, tune the model, or
calibrate thresholds. The `npc2-crossing-route` attempt was rejected after
Autoware did not publish a route trajectory. Its failure is retained in the
versioned configuration for reproducibility, but it is not part of the split.
