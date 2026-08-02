#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK="second-sight-replay"
NODE_CONTAINER="second-sight-replay-node"
OBSERVER_CONTAINER="second-sight-replay-observer"
BAG_PATH="${1:-$ROOT_DIR/data/raw/openadkit-clean-20260716T112843Z}"
MODEL_PATH="${2:-$ROOT_DIR/models/hybrid-overnight.joblib}"

if [[ ! -d "$BAG_PATH" ]]; then
  echo "Bag directory does not exist: $BAG_PATH" >&2
  exit 1
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model does not exist: $MODEL_PATH" >&2
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
  --model /model.joblib \
  --mode hybrid \
  --ros-args -p use_sim_time:=true >/dev/null

docker run --detach \
  --name "$OBSERVER_CONTAINER" \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc \
  "source /opt/ros/humble/setup.bash && timeout 90 ros2 topic echo --once /second_sight/status" \
  >/dev/null

sleep 3
docker run --rm \
  --network "$NETWORK" \
  --env ROS_DOMAIN_ID=88 \
  --env RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  --volume "$BAG_PATH:/bag:ro" \
  odinlmshen/autoware-planning-control:v1.0 \
  bash -lc \
  "source /opt/ros/humble/setup.bash && ros2 bag play /bag --clock --topics /perception/object_recognition/detection/objects /planning/scenario_planning/trajectory"

observer_status="$(docker wait "$OBSERVER_CONTAINER")"
docker logs "$OBSERVER_CONTAINER"
node_logs="$(docker logs "$NODE_CONTAINER" 2>&1)"
echo "$node_logs"
if [[ "$observer_status" != "0" ]]; then
  echo "Did not receive second-sight status telemetry." >&2
  exit 1
fi
if [[ "$node_logs" == *"safe stop requested"* ]]; then
  echo "Clean replay incorrectly requested a safe stop." >&2
  exit 1
fi
