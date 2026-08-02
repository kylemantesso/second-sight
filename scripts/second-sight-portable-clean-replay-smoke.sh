#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK="second-sight-portable-clean-replay"
NODE_CONTAINER="second-sight-portable-clean-node"
OBSERVER_CONTAINER="second-sight-portable-clean-observer"
STREAM_PATH="${1:-$ROOT_DIR/data/processed/openadkit-clean-20260716T112843Z.jsonl}"
MODEL_PATH="${2:-$ROOT_DIR/models/hybrid-25tree.joblib}"
require_no_fast_anomalies="${SECOND_SIGHT_REQUIRE_NO_FAST_ANOMALIES:-false}"

if [[ ! -f "$STREAM_PATH" ]]; then
  echo "Clean stream does not exist: $STREAM_PATH" >&2
  exit 1
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model does not exist: $MODEL_PATH" >&2
  exit 1
fi
if [[ "$require_no_fast_anomalies" != "true" && "$require_no_fast_anomalies" != "false" ]]; then
  echo "SECOND_SIGHT_REQUIRE_NO_FAST_ANOMALIES must be true or false." >&2
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
  ${SECOND_SIGHT_NODE_ARGS:-} >/dev/null

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
  --volume "$ROOT_DIR:/workspace:ro" \
  --volume "$STREAM_PATH:/clean.jsonl:ro" \
  second-sight-node:dev \
  python3 /workspace/components/fault_injector/replay_node.py /clean.jsonl

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
if [[ "$require_no_fast_anomalies" == "true" && "$node_logs" == *"perception guardrail anomaly"* ]]; then
  echo "Clean replay produced a perception-fast-path anomaly." >&2
  exit 1
fi
