#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-live-latency-trial.sh RUN_ID SCENARIO_PATH [TIMEOUT_SECONDS]

Run one fresh Open AD Kit fault-to-safe-stop-request trial on one Linux host.
The run writes latency JSONL, Docker resource TSV, and provenance text under
reports/measurements/. It does not upload artifacts or publish a result.
EOF
}

run_id="${1:-}"
scenario_path="${2:-}"
timeout_seconds="${3:-180}"

if [[ -z "$run_id" || -z "$scenario_path" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$run_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "RUN_ID may contain only letters, numbers, dots, underscores, and hyphens." >&2
  exit 1
fi
if [[ ! -f "$scenario_path" ]]; then
  echo "Scenario is missing: $scenario_path" >&2
  exit 1
fi
if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "TIMEOUT_SECONDS must be a positive integer." >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scenario_path="$(cd "$(dirname "$scenario_path")" && pwd)/$(basename "$scenario_path")"
export SECOND_SIGHT_MODEL_PATH="${SECOND_SIGHT_MODEL_PATH:-$root_dir/models/hybrid-25tree.joblib}"
export SECOND_SIGHT_SCENARIO_PATH="$scenario_path"
export SECOND_SIGHT_LATENCY_OUTPUT="$run_id.jsonl"
export OPENADKIT_TIMEOUT="${OPENADKIT_TIMEOUT:-300}"

if [[ ! -f "$SECOND_SIGHT_MODEL_PATH" ]]; then
  echo "Model is missing: $SECOND_SIGHT_MODEL_PATH" >&2
  exit 1
fi

measurement_dir="$root_dir/reports/measurements"
latency_path="$measurement_dir/$SECOND_SIGHT_LATENCY_OUTPUT"
resource_path="$measurement_dir/$run_id-resources.tsv"
metadata_path="$measurement_dir/$run_id-metadata.txt"
mkdir -p "$measurement_dir"
rm -f "$latency_path" "$resource_path" "$metadata_path"

sampler_pid=""
started=false

cleanup() {
  if [[ -n "$sampler_pid" ]] && kill -0 "$sampler_pid" 2>/dev/null; then
    kill "$sampler_pid" 2>/dev/null || true
    wait "$sampler_pid" 2>/dev/null || true
  fi
  if [[ "$started" == true ]]; then
    "$root_dir/scripts/openadkit.sh" integrated-stop >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"$root_dir/scripts/openadkit.sh" integrated-start
started=true

"$root_dir/scripts/capture-container-resources.sh" \
  "$resource_path" "$timeout_seconds" 1 &
sampler_pid=$!

deadline=$(( $(date +%s) + timeout_seconds ))
while (( $(date +%s) < deadline )); do
  if [[ -s "$latency_path" ]] && grep -q '"event":"safe_stop_requested"' "$latency_path"; then
    break
  fi
  sleep 1
done

if [[ -z "$sampler_pid" ]] || ! kill -0 "$sampler_pid" 2>/dev/null; then
  echo "Resource sampler stopped before the trial completed." >&2
  exit 1
fi
kill "$sampler_pid"
wait "$sampler_pid" 2>/dev/null || true
sampler_pid=""

if [[ ! -s "$latency_path" ]] || ! grep -q '"event":"safe_stop_requested"' "$latency_path"; then
  echo "Trial timed out without a safe-stop-request timing record: $latency_path" >&2
  exit 1
fi

{
  echo "run_id=$run_id"
  echo "scenario_path=$SECOND_SIGHT_SCENARIO_PATH"
  echo "model_path=$SECOND_SIGHT_MODEL_PATH"
  echo "git_revision=$(git -C "$root_dir" rev-parse HEAD)"
  echo "model_sha256=$(sha256sum "$SECOND_SIGHT_MODEL_PATH" | cut -d ' ' -f1)"
  echo "host=$(hostname)"
  uname -a
  docker image inspect \
    second-sight-simulator:dev \
    second-sight-fault-injector:dev \
    second-sight-node:dev \
    second-sight-latency-monitor:dev \
    --format '{{.RepoTags}} {{.Id}}'
} >"$metadata_path"

echo "Completed $run_id"
echo "Latency: $latency_path"
echo "Resources: $resource_path"
echo "Metadata: $metadata_path"
