# Isolation Forest Baseline

This is a development-correctness result measured on macOS. It is not an Arm
Linux performance result and must not be used as a submission performance
claim.

## Dataset

- 110 overnight ROS bags captured: 55 passing and 55 stopping configurations
- 44 bags contained both detections and trajectory messages
- 38 complete bags met the minimum 300-tick requirement
- 16,108 clean ticks used for training
- 30 numeric features per tick
- 300-tree Isolation Forest, deterministic seed 2026

The remaining bags were rejected rather than silently included: 66 lacked a
usable trajectory stream, and 6 complete-stream exports were too short. The
collector now enables Docker's init process to avoid the zombie process seen at
the end of this run.

The extractor also emits two experimental persistent-track features. They are
excluded from the model because object-list rebuilds caused false positives and
did not improve vanish latency without stable detection IDs.

## Results

At a threshold derived from the 99th percentile of clean training scores:

- False-positive rate on normal intervals: 0%
- Vanish: missed
- Phantom: missed
- Freeze: missed
- Teleport: missed
- Confidence collapse: missed
- Perception hang: missed

At the less conservative 95th-percentile threshold:

- False-positive rate on normal intervals: 4.192%
- Vanish: detected after 1,538.6 ms
- Perception hang: detected after 30.0 ms
- Phantom, freeze, teleport, and confidence collapse: missed

## Normal-Only Guardrails

The guardrails learn robust clean ranges for safety-relevant scalar features.
Object count changes and ego-relative displacement use 2nd/98th-percentile
ranges; other features use 0.5th/99.5th-percentile ranges. Callback-arrival age
and gap are excluded from active guardrails because Docker replay scheduling
caused false stops; source timestamp age catches stale perception reliably. No
injected faults are used to fit these bounds.

The hybrid combines the 99th-percentile Isolation Forest with guardrails using
an OR decision:

- False-positive rate on held-out normal intervals: 0.730% (1 of 137 ticks)
- Vanish: detected after 1,538.6 ms
- Phantom: detected after 37.1 ms
- Freeze: detected after 38.9 ms
- Teleport: detected after 38.9 ms
- Confidence collapse: detected after 37.1 ms
- Perception hang: detected after 30.0 ms

False-positive accounting excludes a documented 500 ms recovery window after
each injected interval because restoring vanished or teleported objects creates
a real stream discontinuity caused by the test fault.

## Conclusion

The end-to-end training and evaluation pipeline works, but this multivariate
Isolation Forest baseline is not adequate. Repeating one deterministic route
increased sample count without adding enough behavioral diversity, and the
single aggregate forest score dilutes obvious one-feature failures such as
stale timestamps and collapsed confidence.

The normal-only hybrid detects all six current injected faults, but vanish is
too slow and the evaluation comes from one deterministic route. The Isolation
Forest remains an honest negative baseline rather than being retroactively
presented as successful. Next, compare the hybrid against a tiny autoencoder,
add stable-ID or probabilistic tracking for faster vanish detection, and
evaluate on varied routes and held-out clean runs before making detection
claims.

## Live Adapter

The ROS 2 Second Sight adapter uses the same stateful feature extractor and model
scorer as offline evaluation. A clean bag replay produced normal status,
isolated non-consecutive alerts, and no safe-stop request. The node defaults to
dry-run and requires two consecutive anomalous ticks before publishing a
latched stop request. Calling Autoware's stop service requires the explicit
`--enable-safe-stop` flag.

A complementary 2x functional replay converted the corrupted portable stream
back into real Autoware detection and trajectory messages. The live node
published `/second_sight/safe_stop_requested: true` in dry-run mode. This verifies
message conversion and control flow, not latency; only Arm Linux runs may be
used for performance claims.

The complete live chain has also been verified with clean detections published
to `/second_sight/perception/raw`, the ROS fault injector publishing canonical
Autoware detections plus `/second_sight/fault/*` ground truth, and the Second Sight
publishing a dry-run stop. Full Open AD Kit integration still requires a
simulator-scoped publisher remap to the private raw topic.
