#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK="second-sight-fault-replay"
NODE_CONTAINER="second-sight-fault-node"
OBSERVER_CONTAINER="second-sight-fault-observer"
STREAM_PATH="${1:-$ROOT_DIR/data/processed/openadkit-all-faults.jsonl}"
MODEL_PATH="${2:-$ROOT_DIR/models/hybrid-overnight.joblib}"

if [[ ! -f "$STREAM_PATH" || ! -f "$MODEL_PATH" ]]; then
  echo "Fault stream or model is missing." >&2
  exit 1
fi

cleanup() {
  docker rm --force "$OBSERVER_CONTAINER" "$NODE_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker network create "$NETWORK" >/dev/null
docker run --detach --rm \
  --name "$NODE_CONTAINER" \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$MODEL_PATH:/model.joblib:ro" \
  second-sight-node:dev \
  python3 /opt/second-sight/second_sight_node.py \
  --model /model.joblib --mode hybrid >/dev/null

docker run --detach \
  --name "$OBSERVER_CONTAINER" \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc \
  "source /opt/ros/humble/setup.bash && timeout 60 ros2 topic echo --once /second_sight/safe_stop_requested" \
  >/dev/null

sleep 3
docker run --rm \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$ROOT_DIR:/workspace:ro" \
  --volume "$STREAM_PATH:/faults.jsonl:ro" \
  second-sight-node:dev \
  python3 /workspace/components/fault_injector/replay_node.py /faults.jsonl --rate 2

observer_status="$(docker wait "$OBSERVER_CONTAINER")"
observer_logs="$(docker logs "$OBSERVER_CONTAINER" 2>&1)"
node_logs="$(docker logs "$NODE_CONTAINER" 2>&1)"
echo "$observer_logs"
echo "$node_logs"
if [[ "$observer_status" != "0" || "$observer_logs" != *"data: true"* ]]; then
  echo "Fault replay did not produce a safe-stop request." >&2
  exit 1
fi
