#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK="second-sight-live-chain"
SECOND_SIGHT_CONTAINER="second-sight-chain-node"
INJECTOR_CONTAINER="second-sight-chain-injector"
STOP_OBSERVER="second-sight-chain-stop-observer"
FAULT_OBSERVER="second-sight-chain-fault-observer"
STREAM_PATH="${1:-$ROOT_DIR/data/processed/openadkit-clean-20260716T112843Z.jsonl}"
MODEL_PATH="$ROOT_DIR/models/hybrid-overnight.joblib"
SCENARIO_PATH="$ROOT_DIR/configs/scenarios/all-faults.yaml"

cleanup() {
  docker rm --force \
    "$STOP_OBSERVER" "$FAULT_OBSERVER" "$INJECTOR_CONTAINER" "$SECOND_SIGHT_CONTAINER" \
    >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker network create "$NETWORK" >/dev/null
docker run --detach --rm \
  --name "$SECOND_SIGHT_CONTAINER" \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$MODEL_PATH:/model.joblib:ro" \
  second-sight-node:dev \
  python3 /opt/second-sight/second_sight_node.py --model /model.joblib --mode hybrid >/dev/null

docker run --detach --rm \
  --name "$INJECTOR_CONTAINER" \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$SCENARIO_PATH:/scenario.yaml:ro" \
  second-sight-fault-injector:dev \
  python3 /opt/second-sight/fault_injector_node.py --scenario /scenario.yaml >/dev/null

for observer in "$STOP_OBSERVER" "$FAULT_OBSERVER"; do
  topic="/second_sight/safe_stop_requested"
  if [[ "$observer" == "$FAULT_OBSERVER" ]]; then
    topic="/second_sight/fault/event"
  fi
  docker run --detach \
    --name "$observer" \
    --network "$NETWORK" \
    --env ROS_DOMAIN_ID=88 \
    --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    odinlmshen/autoware-planning-control:v1.0 \
    bash -lc "source /opt/ros/humble/setup.bash && timeout 60 ros2 topic echo --once $topic" \
    >/dev/null
done

sleep 3
docker run --rm \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$ROOT_DIR:/workspace:ro" \
  --volume "$STREAM_PATH:/clean.jsonl:ro" \
  second-sight-node:dev \
  python3 /workspace/components/fault_injector/replay_node.py \
  /clean.jsonl --rate 2 --detection-topic /second_sight/perception/raw

stop_status="$(docker wait "$STOP_OBSERVER")"
fault_status="$(docker wait "$FAULT_OBSERVER")"
stop_logs="$(docker logs "$STOP_OBSERVER" 2>&1)"
fault_logs="$(docker logs "$FAULT_OBSERVER" 2>&1)"
echo "$stop_logs"
echo "$fault_logs"
docker logs "$INJECTOR_CONTAINER"
docker logs "$SECOND_SIGHT_CONTAINER"

if [[ "$stop_status" != "0" || "$stop_logs" != *"data: true"* ]]; then
  echo "Live chain did not request a dry-run safe stop." >&2
  exit 1
fi
if [[ "$fault_status" != "0" || "$fault_logs" != *"fault_ids"* ]]; then
  echo "Live chain did not publish fault ground truth." >&2
  exit 1
fi
