#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/process-clean-data.sh COHORT_MANIFEST

Export and extract only the clean bags named by a frozen route-cohort manifest.
The script does not train a model: that separation keeps the final-test route
out of training and validation threshold calibration.
EOF
}

manifest_path="${1:-}"
if [[ -z "$manifest_path" || ! -f "$manifest_path" ]]; then
  usage >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw_dir="$root_dir/data/raw"
stream_dir="$root_dir/data/processed/clean-streams"
feature_dir="$root_dir/data/processed/clean-features"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running." >&2
  exit 1
fi

mapfile -t bag_paths < <(
  for cohort in train validation final_test; do
    uv run --project "$root_dir" second-sight cohort-files \
      --manifest "$manifest_path" --cohort "$cohort" --directory "$raw_dir" --suffix ""
  done
)
if (( ${#bag_paths[@]} == 0 )); then
  echo "No raw bags matched the frozen cohort manifest." >&2
  exit 1
fi

container_bags=()
for bag_path in "${bag_paths[@]}"; do
  if [[ ! -d "$bag_path" ]]; then
    echo "Matched raw artifact is not a ROS bag directory: $bag_path" >&2
    exit 1
  fi
  container_bags+=("/bags/$(basename "$bag_path")")
done

mkdir -p "$stream_dir" "$feature_dir"
docker run --rm --platform linux/arm64 \
  --volume "$root_dir:/workspace:ro" \
  --volume "$raw_dir:/bags:ro" \
  --volume "$stream_dir:/output" \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && python3 /workspace/components/bag_exporter/export_bag.py "$@" --output-dir /output --skip-existing' \
  -- "${container_bags[@]}"

mapfile -t stream_paths < <(
  for cohort in train validation final_test; do
    uv run --project "$root_dir" second-sight cohort-files \
      --manifest "$manifest_path" --cohort "$cohort" --directory "$stream_dir" --suffix .jsonl
  done
)
if (( ${#stream_paths[@]} == 0 )); then
  echo "Bag export did not produce any complete streams." >&2
  exit 1
fi
uv run --project "$root_dir" second-sight features-batch "${stream_paths[@]}" \
  --output-dir "$feature_dir" --skip-existing

echo "Processed ${#bag_paths[@]} raw bags and ${#stream_paths[@]} portable streams."
echo "The frozen cohort manifest, not this script, controls model eligibility."
