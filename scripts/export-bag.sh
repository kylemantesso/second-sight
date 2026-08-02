#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BAG_PATH="${1:-}"

if [[ -z "$BAG_PATH" ]]; then
  echo "Usage: ./scripts/export-bag.sh BAG_DIRECTORY [OUTPUT_FILE]" >&2
  exit 1
fi

if [[ "$BAG_PATH" != /* ]]; then
  BAG_PATH="$ROOT_DIR/$BAG_PATH"
fi
if [[ ! -d "$BAG_PATH" ]]; then
  echo "Bag directory does not exist: $BAG_PATH" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running." >&2
  exit 1
fi

BAG_PARENT="$(dirname "$BAG_PATH")"
BAG_NAME="$(basename "$BAG_PATH")"
OUTPUT_PATH="${2:-$ROOT_DIR/data/processed/$BAG_NAME.jsonl}"
if [[ "$OUTPUT_PATH" != /* ]]; then
  OUTPUT_PATH="$ROOT_DIR/$OUTPUT_PATH"
fi
mkdir -p "$(dirname "$OUTPUT_PATH")"

docker run --rm --platform linux/arm64 \
  --volume "$ROOT_DIR:/workspace:ro" \
  --volume "$BAG_PARENT:/bags:ro" \
  --volume "$(dirname "$OUTPUT_PATH"):/output" \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && python3 /workspace/components/bag_exporter/export_bag.py "$1" --output "$2"' \
  -- "/bags/$BAG_NAME" "/output/$(basename "$OUTPUT_PATH")"

echo "Portable stream: $OUTPUT_PATH"
