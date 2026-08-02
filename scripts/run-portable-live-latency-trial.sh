#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-portable-live-latency-trial.sh RUN_ID SCENARIO_PATH [TIMEOUT_SECONDS]

Run one portable ROS 2 live-latency trial without the finite Open AD Kit
simulator. The publisher loops the clean stream, but a completed trial is
accepted only when the watchdog stops before the first replay cycle ends.

This runner is intended for delayed trajectory-hybrid cases such as teleport.
It writes a timing JSONL, source logs, and provenance under reports/measurements/.
EOF
}

run_id="${1:-}"
scenario_path="${2:-}"
timeout_seconds="${3:-90}"

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
stream_path="${SECOND_SIGHT_STREAM_PATH:-$root_dir/data/processed/openadkit-clean-20260716T112843Z.jsonl}"
model_path="${SECOND_SIGHT_MODEL_PATH:-$root_dir/models/hybrid-25tree.joblib}"
expected_path="${SECOND_SIGHT_EXPECTED_DECISION_PATH:-trajectory_hybrid}"
max_fault_to_stop_ms="${SECOND_SIGHT_MAX_FAULT_TO_STOP_MS:-20000}"
stop_after="${SECOND_SIGHT_STOP_AFTER:-1}"
discovery_delay_seconds="${SECOND_SIGHT_DISCOVERY_DELAY_SECONDS:-10}"
# The raw Open AD Kit capture begins with an isolated track-association jump.
# This fixed clean-only window has no comparable displacement before the fault.
stream_start_seconds="${SECOND_SIGHT_STREAM_START_SECONDS:-6}"
stream_duration_seconds="${SECOND_SIGHT_STREAM_DURATION_SECONDS:-10}"
network="second-sight-portable-live-$run_id"
node_container="second-sight-portable-node-$run_id"
injector_container="second-sight-portable-injector-$run_id"
monitor_container="second-sight-portable-monitor-$run_id"
publisher_container="second-sight-portable-publisher-$run_id"

if [[ ! -f "$stream_path" ]]; then
  echo "Portable clean stream is missing: $stream_path" >&2
  exit 1
fi
if [[ ! -f "$model_path" ]]; then
  echo "Model is missing: $model_path" >&2
  exit 1
fi
if ! [[ "$max_fault_to_stop_ms" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
  echo "SECOND_SIGHT_MAX_FAULT_TO_STOP_MS must be a positive number." >&2
  exit 1
fi
if ! [[ "$stop_after" =~ ^[1-9][0-9]*$ ]]; then
  echo "SECOND_SIGHT_STOP_AFTER must be a positive integer." >&2
  exit 1
fi
if ! [[ "$discovery_delay_seconds" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
  echo "SECOND_SIGHT_DISCOVERY_DELAY_SECONDS must be a positive number." >&2
  exit 1
fi
if ! [[ "$stream_start_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "SECOND_SIGHT_STREAM_START_SECONDS must be a non-negative number." >&2
  exit 1
fi
if ! [[ "$stream_duration_seconds" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
  echo "SECOND_SIGHT_STREAM_DURATION_SECONDS must be a positive number." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running." >&2
  exit 1
fi

measurement_dir="$root_dir/reports/measurements"
latency_path="$measurement_dir/$run_id.jsonl"
metadata_path="$measurement_dir/$run_id-metadata.txt"
publisher_log_path="$measurement_dir/$run_id-publisher.log"
mkdir -p "$measurement_dir"
rm -f "$latency_path" "$metadata_path" "$publisher_log_path"

cleanup() {
  docker rm --force "$publisher_container" "$monitor_container" "$injector_container" \
    "$node_container" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

# Rebuild the three runtime images so this run is tied to the checked-out
# revision rather than a potentially stale local image.
if [[ "${SECOND_SIGHT_BUILD_IMAGES:-true}" == "true" ]]; then
  docker build --file "$root_dir/components/fault_injector/Dockerfile" \
    --tag second-sight-fault-injector:dev "$root_dir"
  docker build --file "$root_dir/components/second_sight/Dockerfile" \
    --tag second-sight-node:dev "$root_dir"
  docker build --file "$root_dir/components/latency_monitor/Dockerfile" \
    --tag second-sight-latency-monitor:dev "$root_dir"
elif [[ "${SECOND_SIGHT_BUILD_IMAGES}" != "false" ]]; then
  echo "SECOND_SIGHT_BUILD_IMAGES must be true or false." >&2
  exit 1
fi

docker network create "$network" >/dev/null
common_ros_args=(
  --network "$network"
  --env ROS_DOMAIN_ID=88
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
)

docker run --detach --rm --name "$node_container" "${common_ros_args[@]}" \
  --volume "$model_path:/model.joblib:ro" \
  second-sight-node:dev \
  python3 /opt/second-sight/second_sight_node.py \
  --model /model.joblib --mode hybrid --stop-after "$stop_after" \
  --reset-gap-seconds 2 >/dev/null

docker run --detach --rm --name "$injector_container" "${common_ros_args[@]}" \
  --volume "$scenario_path:/scenario.yaml:ro" \
  second-sight-fault-injector:dev \
  python3 /opt/second-sight/fault_injector_node.py --scenario /scenario.yaml >/dev/null

docker run --detach --rm --name "$monitor_container" "${common_ros_args[@]}" \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --env ROS_LOG_DIR=/tmp/ros-log \
  --volume "$measurement_dir:/measurements" \
  second-sight-latency-monitor:dev \
  python3 /opt/second-sight/latency_monitor_node.py \
  --output "/measurements/$run_id.jsonl" >/dev/null

# Let DDS discovery complete before the replay node begins its own three-second
# readiness delay. The initial telemetry is itself the timing source, so it
# must not begin before every subscriber has discovered its publisher. Liveness
# is intentionally not enabled: this experiment must demonstrate the
# trajectory-hybrid decision, not a missing-message timeout.
sleep "$discovery_delay_seconds"
docker run --detach --rm --name "$publisher_container" "${common_ros_args[@]}" \
  --volume "$root_dir:/workspace:ro" \
  --volume "$stream_path:/clean.jsonl:ro" \
  second-sight-node:dev \
  python3 /workspace/components/fault_injector/replay_node.py /clean.jsonl \
  --detection-topic /second_sight/perception/raw \
  --start-seconds "$stream_start_seconds" \
  --duration-seconds "$stream_duration_seconds" \
  --loop --loop-delay 0 >/dev/null

deadline=$(( $(date +%s) + timeout_seconds ))
while (( $(date +%s) < deadline )); do
  if [[ -s "$latency_path" ]] && grep -q '"event":"safe_stop_requested"' "$latency_path"; then
    break
  fi
  sleep 1
done

publisher_running="$(docker inspect --format '{{.State.Running}}' "$publisher_container" 2>/dev/null || true)"
docker logs "$publisher_container" >"$publisher_log_path" 2>&1 || true

if [[ "$publisher_running" != "true" ]]; then
  echo "Replay publisher exited before the trial completed." >&2
  exit 1
fi
if grep -q 'restarting stream' "$publisher_log_path"; then
  echo "Replay reached its first end-of-stream before the decision; rejecting timing." >&2
  exit 1
fi
if [[ ! -s "$latency_path" ]] || ! grep -q '"event":"safe_stop_requested"' "$latency_path"; then
  echo "Trial timed out without a safe-stop timing record: $latency_path" >&2
  exit 1
fi

python3 - "$latency_path" "$expected_path" "$max_fault_to_stop_ms" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_path = sys.argv[2]
max_fault_to_stop_ms = float(sys.argv[3])
records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
stops = [record for record in records if record.get("event") == "safe_stop_requested"]
if len(stops) != 1:
    raise SystemExit(f"expected exactly one safe-stop record, found {len(stops)}")
stop = stops[0]
if stop.get("decision_path") != expected_path:
    raise SystemExit(
        f"expected decision path {expected_path!r}, got {stop.get('decision_path')!r}"
    )
if stop.get("safe_stop_path") != expected_path:
    raise SystemExit(
        f"expected safe-stop path {expected_path!r}, got {stop.get('safe_stop_path')!r}"
    )
if float(stop["fault_to_safe_stop_ms"]) > max_fault_to_stop_ms:
    raise SystemExit(
        "fault-to-stop interval exceeds the causal bound: "
        f"{stop['fault_to_safe_stop_ms']} ms > {max_fault_to_stop_ms} ms"
    )
print(json.dumps(stop, sort_keys=True))
PY

{
  echo "run_id=$run_id"
  echo "scenario_path=$scenario_path"
  echo "stream_path=$stream_path"
  echo "model_path=$model_path"
  echo "expected_decision_path=$expected_path"
  echo "max_fault_to_stop_ms=$max_fault_to_stop_ms"
  echo "stop_after=$stop_after"
  echo "discovery_delay_seconds=$discovery_delay_seconds"
  echo "stream_start_seconds=$stream_start_seconds"
  echo "stream_duration_seconds=$stream_duration_seconds"
  echo "source_completed_before_decision=false"
  echo "git_revision=$(git -C "$root_dir" rev-parse HEAD)"
  echo "model_sha256=$(sha256sum "$model_path" | cut -d ' ' -f1)"
  echo "host=$(hostname)"
  uname -a
  docker image inspect second-sight-fault-injector:dev second-sight-node:dev \
    second-sight-latency-monitor:dev --format '{{.RepoTags}} {{.Id}}'
} >"$metadata_path"

echo "Completed $run_id"
echo "Latency: $latency_path"
echo "Publisher log: $publisher_log_path"
echo "Metadata: $metadata_path"
