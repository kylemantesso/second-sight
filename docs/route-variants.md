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
| `north-approach-right-turn` | Starts on the approximately 230 m predecessor lane, then uses the original right-turn goal. | Not simulator-validated |
| `extended-right-turn` | Uses the original start, then continues onto the successor of the original goal lane. | Not simulator-validated |

These are candidate route definitions, not evidence of route diversity. A
candidate becomes usable only after a smoke recording contains both
`/perception/object_recognition/detection/objects` and
`/planning/scenario_planning/trajectory`.

## Repeatable smoke protocol

```bash
./scripts/openadkit.sh generate-routes
OPENADKIT_ROUTE_ID=north-approach-right-turn \
OPENADKIT_SCENARIO_PATH=/autoware/scenario-sim/scenario/second-sight-north-approach-right-turn.yaml \
OPENADKIT_TIMEOUT=180 \
OPENADKIT_FRAME_RATE=1 \
./scripts/openadkit.sh record 45
```

`record` omits the visualizer unless `OPENADKIT_WITH_VISUALIZER=1`; that saves
memory during headless validation. Inspect the resulting bag with the existing
exporter before adding it to any data cohort.

## Current blocker (2026-08-03)

The first local smoke attempt loaded the north-approach scenario but did not
produce a valid bag. Docker Desktop's Linux VM was limited to 7.65 GiB while
other Docker workloads were running. Autoware components were OOM-killed, the
scenario runner then failed to set its velocity limit, and no trajectory became
available. Lowering the requested frame rate to 1 Hz did not fix the memory
shortfall.

Before retrying, either give Docker Desktop more memory or stop unrelated
Docker workloads, then run each candidate with the command above. Do not treat
this failed attempt as a route result, use it for training, or count it toward
the required three route families (train, validation, and untouched final
test).
