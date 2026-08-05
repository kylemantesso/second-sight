#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-v2-live-validation.sh RUN_PREFIX FROZEN_V2_MODEL [REPEATS]

Run repeated, native-Arm integrated safe-stop validation for each Second Sight
v2 decision path: trajectory hybrid, confidence health, source freshness, and
perception liveness. The script requires an accepted Autoware SetStop response
for every trial and rejects a trace whose actual stop path differs from the
expected path. It writes only local measurement artifacts; archive them to the
private benchmark bucket after review.
EOF
}

run_prefix="${1:-}"
model_path="${2:-}"
repeats="${3:-3}"
if [[ -z "$run_prefix" || -z "$model_path" || ! -f "$model_path" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$run_prefix" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "RUN_PREFIX may contain only letters, numbers, dots, underscores, and hyphens." >&2
  exit 1
fi
if ! [[ "$repeats" =~ ^[1-9][0-9]*$ ]]; then
  echo "REPEATS must be a positive integer." >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model_path="$(cd "$(dirname "$model_path")" && pwd)/$(basename "$model_path")"
measurement_dir="$root_dir/reports/measurements"
declare -a traces=()

# The scenarios are selected to exercise each v2 decision path. The trace is
# checked after each run so a hybrid/fast-path detection cannot be mislabelled
# as proof of a deterministic v2 monitor.
declare -a labels=(phantom confidence-collapse freeze liveness)
declare -a paths=(trajectory_hybrid confidence_health source_freshness perception_liveness_timeout)

export SECOND_SIGHT_MODEL_PATH="$model_path"
export SECOND_SIGHT_NODE_ARGS="${SECOND_SIGHT_NODE_ARGS:---enable-safe-stop}"
export SECOND_SIGHT_EXPECT_SAFE_STOP_RESPONSE=true

for index in "${!labels[@]}"; do
  label="${labels[$index]}"
  expected_path="${paths[$index]}"
  scenario="$root_dir/configs/scenarios/latency/$label.yaml"
  for repeat in $(seq 1 "$repeats"); do
    run_id="$run_prefix-$label-r$(printf '%02d' "$repeat")"
    "$root_dir/scripts/run-live-latency-trial.sh" "$run_id" "$scenario"
    trace="$measurement_dir/$run_id.jsonl"
    if ! grep -Fq "\"safe_stop_path\":\"$expected_path\"" "$trace"; then
      echo "$run_id did not stop through $expected_path; inspect $trace" >&2
      exit 1
    fi
    traces+=("$trace")
  done
done

summary="$measurement_dir/$run_prefix-summary.json"
uv run --project "$root_dir" second-sight latency-report "${traces[@]}" --output "$summary"
echo "Completed v2 live validation: $summary"
