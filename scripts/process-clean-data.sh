#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAM_DIR="$ROOT_DIR/data/processed/clean-streams"
FEATURE_DIR="$ROOT_DIR/data/processed/clean-features"
MODEL_PATH="$ROOT_DIR/models/isolation-forest-overnight.joblib"

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running." >&2
  exit 1
fi

mkdir -p "$STREAM_DIR" "$FEATURE_DIR"

docker run --rm --platform linux/arm64 \
  --volume "$ROOT_DIR:/workspace:ro" \
  --volume "$ROOT_DIR/data/raw:/bags:ro" \
  --volume "$STREAM_DIR:/output" \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && python3 /workspace/components/bag_exporter/export_bag.py /bags/openadkit-clean-pass-* /bags/openadkit-clean-fail-* --output-dir /output --skip-existing --skip-invalid'

streams=("$STREAM_DIR"/*.jsonl)
uv run --project "$ROOT_DIR" second-sight features-batch "${streams[@]}" \
  --output-dir "$FEATURE_DIR" \
  --skip-existing

features=("$FEATURE_DIR"/*.csv)
uv run --project "$ROOT_DIR" second-sight train "${features[@]}" \
  --output "$MODEL_PATH" \
  --min-rows-per-dataset 300

echo "Processed ${#streams[@]} streams and ${#features[@]} feature datasets."
echo "Model: $MODEL_PATH"
