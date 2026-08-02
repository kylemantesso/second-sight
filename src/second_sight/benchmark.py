"""Reproducible native-host inference benchmarking for Second Sight."""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from second_sight.features import extract_features
from second_sight.model import SecondSightScorer
from second_sight.stream import iter_events


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a benchmark input."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q))


def benchmark_model(
    model_path: Path,
    stream_path: Path,
    output_path: Path,
    *,
    mode: str = "hybrid",
    warmup: int = 1_000,
    samples: int = 10_000,
) -> dict[str, Any]:
    """Measure one model score per tick on a native host and write a report."""
    if warmup < 0:
        raise ValueError("warmup must be non-negative")
    if samples <= 0:
        raise ValueError("samples must be positive")

    rows = extract_features(iter_events(stream_path))
    if not rows:
        raise ValueError("stream contains no complete feature rows")
    scorer = SecondSightScorer(model_path, mode)

    for index in range(warmup):
        scorer.score(rows[index % len(rows)])

    latencies_ns = np.empty(samples, dtype=np.int64)
    anomaly_count = 0
    for index in range(samples):
        started_ns = time.perf_counter_ns()
        result = scorer.score(rows[index % len(rows)])
        latencies_ns[index] = time.perf_counter_ns() - started_ns
        anomaly_count += int(result["anomalous"])

    report = {
        "schema_version": 1,
        "kind": "inference_microbenchmark",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "host": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "model": {
            "path": str(model_path),
            "sha256": sha256(model_path),
            "bytes": model_path.stat().st_size,
        },
        "stream": {
            "path": str(stream_path),
            "sha256": sha256(stream_path),
            "feature_rows": len(rows),
        },
        "detector_mode": mode,
        "warmup_ticks": warmup,
        "sample_count": samples,
        "anomalous_samples": anomaly_count,
        "inference_us": {
            "min": float(latencies_ns.min() / 1_000),
            "mean": float(statistics.fmean(latencies_ns) / 1_000),
            "p50": percentile(latencies_ns, 50) / 1_000,
            "p95": percentile(latencies_ns, 95) / 1_000,
            "p99": percentile(latencies_ns, 99) / 1_000,
            "max": float(latencies_ns.max() / 1_000),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
