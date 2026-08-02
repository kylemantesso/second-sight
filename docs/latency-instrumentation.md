# Live End-to-End Latency Instrumentation

The Arm inference reports measure only model scoring. This harness is the next
measurement layer: it records the live interval from a fault injector emitting
its first modified or suppressed detection to the watchdog's anomaly decision and its
safe-stop request.

It is deliberately an observation path. The fault injector, Second Sight, and
latency monitor publish and subscribe to separate measurement topics; Second
Sight never consumes fault ground truth.

## What is measured

The JSONL output contains three event types for each fault interval:

| Event | Meaning | Derived metric |
| --- | --- | --- |
| `fault_injected` | First modified or suppressed detection is about to be emitted | Measurement start |
| `anomaly_decision` | First anomalous score after that fault, with its path | `fault_to_anomaly_ms` |
| `safe_stop_requested` | Second Sight latches its safe-stop request | `fault_to_safe_stop_ms`, `anomaly_to_safe_stop_ms` |

Timestamps are produced with Python `time.monotonic_ns()`, avoiding errors from
bag header timestamps or ROS simulated time. That makes the protocol valid for
containers on one Linux host only. Do not use this protocol to make a
cross-instance claim: each host has a different monotonic clock. A later
two-machine experiment must use PTP/NTP offset validation or a purpose-built
round-trip protocol and report its clock uncertainty.

The current scope stops at *request issuance*. It does not measure Autoware's
service response or physical vehicle deceleration. It also does not replace
the held-out, varied-route fault-quality evaluation.

The trajectory-context hybrid is the current reference path. An opt-in
perception guardrail path is available for the next A/B experiment; it scores
each detection without waiting for planning, but must not be presented as an
optimization result until it passes clean-stream and Arm validation.

When more than one scoring path is enabled, raw JSONL records carry
`decision_path` and `safe_stop_path`. Use those fields to attribute an
experiment to the fast perception guardrails or the reference trajectory
hybrid; never infer the path from latency alone.

## Run on Arm Linux

Start from a clean output path and use the 25-tree candidate selected in the
Arm scoring comparison:

```bash
output="arm-live-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
mkdir -p reports/measurements
rm -f "reports/measurements/$output"

SECOND_SIGHT_MODEL_PATH="$PWD/models/hybrid-25tree.joblib" \
SECOND_SIGHT_SCENARIO_PATH="$PWD/configs/scenarios/latency/phantom.yaml" \
SECOND_SIGHT_LATENCY_OUTPUT="$output" \
./scripts/openadkit.sh integrated-start
```

The integrated stack runs dry-run safe-stop mode by default. Trigger a single,
deterministic scenario and wait for the monitor to write a complete record:

```bash
tail -f "reports/measurements/$output"
./scripts/openadkit.sh integrated-stop
```

For a repeatable trial that starts the sampler, waits for a safe-stop timing
event, saves provenance, and tears the stack down, use:

```bash
./scripts/run-live-latency-trial.sh \
  arm-phantom-r01 \
  configs/scenarios/latency/phantom.yaml \
  180
```

The runner writes `<run>.jsonl`, `<run>-resources.tsv`, and
`<run>-metadata.txt` under `reports/measurements/`. It deliberately does not
upload or aggregate artifacts; preserve successful runs in private storage only
after inspecting them.

The latency monitor runs as the invoking host user's UID/GID, so these mounted
artifacts remain writable for subsequent trials. Do not start the stack as a
different user between repetitions.

Run each fault type in a fresh process. The six one-fault scenarios under
[`configs/scenarios/latency/`](../configs/scenarios/latency/) are calibrated to
the same transformations as the frozen combined evaluation. A safe-stop request
is intentionally latched, so a combined scenario can produce only one request
measurement before reset. Preserve the raw JSONL in the private
benchmark-artifact bucket together with the model hash, scenario, host facts,
image digests, and command line.

## Capture CPU and memory in the same run

In a second shell on the Arm host, start the sampler after the integrated
containers are healthy and before the fault interval begins:

```bash
./scripts/capture-container-resources.sh \
  "reports/measurements/${output%.jsonl}-resources.tsv" \
  90 1
```

It records Docker's one-shot `cpu_percent`, `memory_usage_limit`, and
`memory_percent` values for `second-sight`, the fault injector, the simulator,
and planning control. The requested interval is applied *after* Docker returns
each snapshot, so use the TSV timestamps to establish actual cadence. The raw
TSV must accompany the latency JSONL in private artifact storage. For each
aligned sample, report watchdog
CPU as its Docker CPU percentage divided by the sum of those four core
containers' CPU percentages. State this denominator explicitly; it is not a
whole-host CPU percentage and it excludes the dashboard and visualizer.

## Reporting rules

Before publishing a result, repeat enough independent runs to report count,
p50, p95, p99, and worst-case fault-to-anomaly and fault-to-safe-stop-request
latency per fault type. Record CPU and memory in the same run. A public report
must state that this measurement includes the configured ROS path but excludes
any uninstrumented simulator, stop-service, and vehicle-response stages.

The monitor's raw records are not committed. `reports/measurements/` is
ignored so generated data cannot accidentally become a public benchmark
artifact.

## Repeat and summarize a validation set

On the Arm host, run a bounded set of fresh trials with both opt-in watchdog
paths enabled. Five repetitions is a development validation set, not a final
confidence demonstration. The harness covers the four validated fast
perception faults and liveness; it deliberately excludes teleport until its
trajectory-hybrid path can be measured before simulator end-of-stream:

```bash
./scripts/run-live-fast-path-validation.sh arm-fast-20260802 5
```

After copying the private JSONL traces to a local ignored measurement directory,
write a machine-readable percentile summary:

```bash
uv run second-sight latency-report reports/measurements/arm-fast-20260802-*.jsonl \
  --output reports/measurements/arm-fast-20260802-summary.json
```

The report groups runs by fault and first decision path, and emits min, p50,
p95, p99, and max for the three live latency intervals. It rejects a trace
without exactly one stop request rather than silently mixing incomplete runs.
