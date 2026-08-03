# Arm traffic-variant validation

This report records native-Arm smoke validation of two clean traffic profiles.
Both use the already validated `north-approach-right-turn` ego route. The
profiles change only the target and controller speeds of Npc1, Npc2, and Npc3;
they do not change the ego route or any NPC route.

This is clean-data coverage evidence, not a varied-route generalization or
safety-performance claim.

## Environment and protocol

- Host: AWS `c8g.4xlarge` Graviton in `ap-southeast-2`
- Source revision: `f363b38` (`Add controlled traffic scenario variants`)
- Simulator: pinned Open AD Kit image, native `linux/arm64`
- Recording: 45 requested seconds of detection objects, predicted objects, and
  planning trajectories
- Acceptance rule: all three requested topics must be present in `ros2 bag
  info`; containers are stopped after each trial.

## Results

| Profile | NPC target speeds (m/s) | Bag duration | Detection objects | Predicted objects | Trajectories | Bag size | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `north-slow-traffic` | 5 / 5 / 4 | 44.081 s | 439 | 1,528 | 9,366 | 128.3 MiB | Pass |
| `north-fast-traffic` | 13 / 13 / 12 | 44.483 s | 444 | 1,569 | 8,328 | 114.1 MiB | Pass |

The different trajectory and predicted-object counts confirm that the profiles
produce distinct clean streams. They do not establish independence from the
underlying north-approach route.

## Reproducibility and artifacts

Generate the scenarios, then record either profile with:

```bash
./scripts/openadkit.sh generate-routes
OPENADKIT_ROUTE_ID=north-slow-traffic \
OPENADKIT_SCENARIO_PATH=/autoware/scenario-sim/scenario/second-sight-north-slow-traffic.yaml \
OPENADKIT_TIMEOUT=300 \
./scripts/openadkit.sh record 45
```

Private raw bags, metadata, and SHA-256 manifests are stored at:

```text
s3://second-sight-benchmark-artifacts-088711593565-ap-southeast-2/
runs/traffic-variant-validation-20260804/
```

SQLite SHA-256 values:

| Profile | SHA-256 |
| --- | --- |
| `north-slow-traffic` | `0844c58d1396c1453e47b7e7db510f147f1ecd55e1c36b809ab07b2bb23a5325` |
| `north-fast-traffic` | `cf1e1a7b6ad76445488ed0d13ab11fd061740a97957803387e9f4efe5a3ba35a` |

## Limitations and next step

These profiles make the model's normal corpus less repetitive, but the upstream
demo still provides one map and one validated ego-route family. Do not split
slow and fast traffic into a final held-out *route* test set or claim
generalization from them. The next step is to obtain or construct at least two
more simulator-validated ego-route families, then reserve one whole route
family as the untouched final test cohort.
