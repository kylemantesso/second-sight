# Second Sight Latency Monitor

This measurement-only ROS 2 node writes a JSONL timing trace for the live
fault-to-safety path. It correlates these producer timestamps:

- `/second_sight/latency/fault_injected`: immediately before the first
  corrupted message in a fault interval;
- `/second_sight/latency/decision`: immediately after Second Sight scores a
  trajectory tick; and
- `/second_sight/latency/safe_stop_requested`: when Second Sight requests a
  stop, including dry-run requests.

The node publishes its correlated records on `/second_sight/latency/event` and
appends them to an explicitly supplied JSONL output path.

```bash
python3 /opt/second-sight/latency_monitor_node.py \
  --output /measurements/live.jsonl
```

The input timestamps use Python's `time.monotonic_ns()`. They are valid only
when the injector and Second Sight run on the same Linux host. They must not be
used as a cross-machine latency result without a synchronized clock protocol.
See [`docs/latency-instrumentation.md`](../../docs/latency-instrumentation.md)
for the run procedure and reporting rules.
