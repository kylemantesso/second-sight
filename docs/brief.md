# Second Sight
### Build brief: an isolated safety monitor that catches silent AI perception failures in an autonomous driving simulation — hackathon entry for the Arm Create: AI Optimization Challenge

---

## 1. What this is

You are helping build a hackathon project. The concept: an autonomous driving stack's perception can fail *silently* — no exception, no crash log; the planner just acts on wrong data. We run a tiny, quantized anomaly-detection model (the **Second Sight**) on an isolated compute partition. It subscribes to the main stack's perception/planning message streams, learns what "normal" looks like, and when the stream turns anomalous it publishes a safe-stop command within milliseconds.

One-line pitch: **"Who watches the AI?" — an independent Second Sight on hardware the main AI cannot touch.**

## 2. Competition context

The full challenge requirements, prizes, judging criteria, and official
resources are recorded in
[`arm-ai-optimization-challenge-2026.md`](arm-ai-optimization-challenge-2026.md).

- **Event:** Arm Create: AI Optimization Challenge (Devpost). Submission deadline: 2026-08-14.
- **Track:** Track 1 — Physical AI. The track text explicitly lists "safety monitoring," "anomaly detection," and "alerting" as eligible, allows simulated sensor data, and permits Arm-based edge servers for autonomy workloads.
- **Judging:** 40 pts technical implementation, 25 pts WOW factor, 20 pts potential impact, 15 pts developer experience. Organizers explicitly want measurable optimization work beyond following a learning path, benchmarked with Arm Performix.
- **Critical framing rule:** every performance claim must be *measured on Arm Linux (Neoverse/Graviton)*, never on the x86 dev machine. Never fabricate a statistic — placeholder numbers must be replaced with measured ones before they appear in any submission material.

## 3. Base learning paths (scaffolding, not the project)

1. Deploy Open AD Kit containerized autonomous driving simulation on Arm Neoverse — https://learn.arm.com/learning-paths/automotive/openadkit1_container/ (do first; gets the Autoware-based sim driving)
2. Prototype safety-critical isolation for autonomous driving systems on Arm Neoverse — https://learn.arm.com/learning-paths/automotive/openadkit2_safetyisolation/ (splits the stack into isolated components over DDS/ROS 2)

The paths provide: containerized sim + two-partition isolation plumbing. They provide **no ML component, no fault injection, no measurement harness** — those are the original work and the entire basis of the entry.

## 4. Architecture

Components (each its own Docker container, multi-arch buildable for amd64 + arm64):

1. **Sim stack** — Open AD Kit / Autoware planning simulator. Publishes perception (detected objects) and planning (trajectory) topics over ROS 2/DDS.
2. **Fault injector** — a standalone, *named* ROS 2 middleware node that sits between perception and planning topics and corrupts messages on command. Fault types to implement:
   - vanish: suppress a real object from the object list (false negative)
   - phantom: insert a nonexistent object (false positive)
   - freeze: replay a stale frame repeatedly
   - teleport: discontinuous object position jump
   - confidence collapse: degrade detection confidence scores
   - liveness/hang (stretch): main stack stops publishing entirely
   Ship this as its own repo-quality tool (README, CLI, config file of fault scenarios). It doubles as the training-data grader and as a reusable community artifact (impact points).
3. **Second Sight** — small anomaly model served in an isolated container (later: separate cloud instance), pinned cores, DDS-only interface. Subscribes to perception + planning topics, computes a per-tick anomaly score, publishes safe-stop when score crosses threshold.
4. **Dashboard** — live "heartbeat" visualization of the anomaly score (green normal, red spike on detection, detection-latency stamp). Foxglove Studio over ROS 2 topics is the fastest route. Exists primarily for the demo video.

## 5. Data and training pipeline

No manual data collection or labeling. The sim generates data; the injector labels it.

1. Record hours of clean sim driving with `ros2 bag record` on the perception + planning topics (varied routes, speeds, traffic).
2. Feature-extraction script converts each tick into ~20 numeric features: object count, per-object displacement since last frame, trajectory smoothness/curvature deltas, inter-message timing gaps, confidence statistics, count-drop-without-exit indicators.
3. Train on normal data only. Baseline: isolation forest (scikit-learn). Target: tiny autoencoder. Output = anomaly score.
4. Quantize to INT8 (ONNX Runtime or ExecuTorch), target single-digit-millisecond inference on Arm cores.
5. Evaluate by replaying recordings through the fault injector; injection timestamps are ground truth → detection rate and time-to-detect computed automatically.
6. Headline claim to preserve: **the Second Sight is never trained on the injected faults, yet detects them** — evidence it generalizes to unanticipated failure modes.

Key insight for the dev loop: the injector and Second Sight only see message streams, so they can be developed entirely against replayed bag files — no live sim needed for most iterations.

## 6. Environments

- **Primary dev machine:** user's PC — AMD Radeon RX 7900 XTX GPU, x86. Run Ubuntu 22.04 (dual-boot preferred over WSL2 for ROS GUI tooling). Full stack runs here: sim, injector, Second Sight, dashboard. GPU is not required (planning simulator is CPU-bound); AWSIM photoreal rendering is an optional stretch and officially targets NVIDIA, so treat AMD support as unverified.
- **Secondary:** user's Mac (Apple Silicon assumed) — model training, analysis, bag-replay development.
- **Benchmark/demo target:** AWS Graviton. Sim node: c8g.4xlarge (16 vCPU / 32 GB, ~100 GB disk). Second Sight node: small instance (e.g. c8g.large) or Oracle always-free Ampere A1 — two physically separate Arm machines make the isolation story strongest. Same region/VPC for low DDS latency. Check current instance pricing; stop instances when idle. New AWS accounts may need a vCPU quota increase to launch 16 vCPUs — request early.
- **Discipline:** no performance tuning on x86. Correctness on the PC; all numbers on Graviton.

## 7. Build steps

1. Register the project on Devpost; create the repo (MIT license, README first).
2. Stand up Ubuntu + Docker on the PC; run Open AD Kit learning path end-to-end until the virtual car drives a route in the visualizer. Start screen-recording sessions from day one (OBS, 1080p).
3. Explore topics (`ros2 topic list`, echo perception messages); record clean-driving bag files.
4. Build the fault injector against bag replays; verify each fault type visibly corrupts the stream.
5. Build feature extraction + train baseline model; iterate features until all fault types spike the score.
6. Quantize the model; wrap it as the Second Sight node with safe-stop publishing; integrate with the live sim.
7. Apply the safety-isolation learning path structure; pin Second Sight to dedicated cores in its own container.
8. Build the Foxglove heartbeat dashboard.
9. Port containers to arm64; deploy two-instance split on Graviton; run Arm Performix benchmarks.
10. Measure and record: detection latency (p50/p99/worst-case), detection rate per fault type, CPU overhead of the Second Sight, model size before/after quantization.
11. Stage and film the demo scenarios; edit video; polish repo (one-command `docker compose up`, architecture diagram); write Devpost submission.

## 8. Metrics the project must produce (measured, on Arm)

- Detection latency: p50, p99, worst-case (ms)
- Detection rate and time-to-detect, per fault type
- Second Sight CPU overhead as % of total stack
- Model size and inference latency before vs. after INT8 quantization
- Arm Performix benchmark output for the Second Sight workload

## 9. Demo video requirements (≤ 3 minutes, captions on, no copyrighted music)

- **Cold open (0:00–0:10):** split screen — left "The world" (pedestrian visible), right "What the AI sees" (bounding box present). Inject the *vanish* fault: box blinks out on the right, pedestrian remains on the left, car doesn't slow. Caption: "Perception failure. No error thrown." Impact. Freeze frame. Title card: "Who watches the AI?"
- **0:10–0:20:** identical scenario replayed with Second Sight: box vanishes, heartbeat graph spikes red, car safe-stops short. One measured stat, huge type (e.g. detection latency).
- **Body:** one live on-camera fault injection typed in a visible terminal; the two-machine isolation shot (labeled terminals, `lscpu` showing Graviton) with the line "the Second Sight runs on hardware the main AI cannot touch"; maximum three full-screen stats.
- **Close:** reuse call-to-action — "fork the fault injector, point it at your own robot."
- Scenarios are deterministic/replayable, so with/without-Second Sight takes cut together as a perfect A/B.

## 10. Deliverables checklist

- [ ] Public repo: MIT license, one-command bring-up, architecture diagram, docs for the fault injector as a standalone tool
- [ ] Measured benchmark report (Performix + metrics in §8)
- [ ] ≤3-minute demo video per §9
- [ ] Devpost submission text framing the Second Sight as running on a vehicle's dedicated safety processor (the Graviton instance stands in for in-vehicle silicon)
