#!/usr/bin/env python3
"""Run Second Sight scoring continuously for an Arm Performix recipe.

This is intentionally a workload, not a latency benchmark. It performs feature
extraction once, warms the persisted model, then repeatedly scores frozen
feature rows until Arm Performix stops the process. The final JSON line lets
recipe logs verify that the steady-state loop ran.
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from second_sight.features import extract_features
from second_sight.model import SecondSightScorer
from second_sight.stream import iter_events

stopping = False


def request_stop(_signum: int, _frame: object) -> None:
    """Finish the current score and report the completed workload count."""
    global stopping
    stopping = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stream", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("isolation_forest", "guardrails", "hybrid"), default="hybrid"
    )
    parser.add_argument("--warmup", type=int, default=5_000)
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")

    rows = extract_features(iter_events(args.stream))
    if not rows:
        parser.error("stream contains no complete feature rows")
    scorer = SecondSightScorer(args.model, args.mode)
    for index in range(args.warmup):
        scorer.score(rows[index % len(rows)])

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    started_ns = time.perf_counter_ns()
    completed = 0
    anomalous = 0
    while not stopping:
        result = scorer.score(rows[completed % len(rows)])
        anomalous += int(result["anomalous"])
        completed += 1
    elapsed_seconds = (time.perf_counter_ns() - started_ns) / 1_000_000_000
    print(
        json.dumps(
            {
                "kind": "performix_steady_state_workload",
                "mode": args.mode,
                "warmup_ticks": args.warmup,
                "completed_ticks": completed,
                "anomalous_ticks": anomalous,
                "elapsed_seconds": elapsed_seconds,
                "ticks_per_second": completed / elapsed_seconds if elapsed_seconds else None,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
