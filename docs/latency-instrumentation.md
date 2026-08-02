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
| `anomaly_decision` | First anomalous trajectory score after that fault | `fault_to_anomaly_ms` |
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

Run each fault type in a fresh process. The six one-fault scenarios under
[`configs/scenarios/latency/`](../configs/scenarios/latency/) are calibrated to
the same transformations as the frozen combined evaluation. A safe-stop request
is intentionally latched, so a combined scenario can produce only one request
measurement before reset. Preserve the raw JSONL in the private
benchmark-artifact bucket together with the model hash, scenario, host facts,
image digests, and command line.

## Reporting rules

Before publishing a result, repeat enough independent runs to report count,
p50, p95, p99, and worst-case fault-to-anomaly and fault-to-safe-stop-request
latency per fault type. Record CPU and memory in the same run. A public report
must state that this measurement includes the configured ROS path but excludes
any uninstrumented simulator, stop-service, and vehicle-response stages.

The monitor's raw records are not committed. `reports/measurements/` is
ignored so generated data cannot accidentally become a public benchmark
artifact.
