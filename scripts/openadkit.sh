#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENADKIT_DIR="${OPENADKIT_DIR:-$ROOT_DIR/.cache/openadkit_demo.autoware}"
OPENADKIT_REPO="https://github.com/odincodeshen/openadkit_demo.autoware.git"
OPENADKIT_REF="f00cc16ff3d70771e07202a8158997c12e3e4b6d"
COMPOSE_PROJECT_NAME="second-sight-openadkit"

usage() {
  cat <<'EOF'
Usage: ./scripts/openadkit.sh COMMAND

Commands:
  setup    Clone the pinned Open AD Kit demo
  generate-routes  Generate Second Sight route variants in the pinned demo cache
  pull     Clone the demo and download its container images
  start    Start one long-running passing scenario in the background
  run      Run one passing scenario in the foreground
  status   Show the demo containers
  topics   List visible ROS 2 topics and message types
  record   Record a clean bag (optional duration in seconds, default: 45)
  integrated-start  Start Open AD Kit with injector and second-sight in dry-run mode
  integrated-status Show the integrated stack containers
  integrated-stop   Stop the integrated stack
  dashboard-start   Start the lightweight looping dashboard demo
  dashboard-status  Show the dashboard demo containers
  dashboard-stop    Stop the dashboard demo
  logs     Follow logs from all demo containers
  stop     Stop and remove the demo containers
EOF
}

require_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "Docker Desktop is not running." >&2
    exit 1
  fi

  if [[ "$(docker info --format '{{.Architecture}}')" != "aarch64" ]]; then
    echo "The local demo expects Docker Desktop using aarch64 Linux containers." >&2
    exit 1
  fi
}

setup() {
  if [[ ! -d "$OPENADKIT_DIR/.git" ]]; then
    mkdir -p "$(dirname "$OPENADKIT_DIR")"
    git init --quiet "$OPENADKIT_DIR"
    git -C "$OPENADKIT_DIR" remote add origin "$OPENADKIT_REPO"
  fi

  if [[ "$(git -C "$OPENADKIT_DIR" rev-parse HEAD 2>/dev/null || true)" != "$OPENADKIT_REF" ]]; then
    git -C "$OPENADKIT_DIR" fetch --depth 1 origin "$OPENADKIT_REF"
    git -C "$OPENADKIT_DIR" checkout --quiet --detach FETCH_HEAD
  fi
}

configure() {
  setup
  export COMMON_FILE="$OPENADKIT_DIR/docker/etc/simulation/config/common.param.yaml"
  variant="${OPENADKIT_VARIANT:-pass}"
  case "$variant" in
    pass|fail)
      export CONF_FILE="$OPENADKIT_DIR/docker/etc/simulation/config/${variant}_static_obstacle_avoidance.param.yaml"
      ;;
    *)
      echo "OPENADKIT_VARIANT must be 'pass' or 'fail'." >&2
      exit 1
      ;;
  esac
  export NGROK_AUTHTOKEN="${NGROK_AUTHTOKEN:-}"
  export NGROK_URL="${NGROK_URL:-}"
  export TIMEOUT="${OPENADKIT_TIMEOUT:-3600}"
  export OPENADKIT_FRAME_RATE="${OPENADKIT_FRAME_RATE:-20}"
  if [[ ! "$OPENADKIT_FRAME_RATE" =~ ^[1-9][0-9]*$ ]]; then
    echo "OPENADKIT_FRAME_RATE must be a positive integer." >&2
    exit 1
  fi
  export SECOND_SIGHT_ROOT="$ROOT_DIR"
  export SECOND_SIGHT_MODEL_PATH="${SECOND_SIGHT_MODEL_PATH:-$ROOT_DIR/models/hybrid-25tree.joblib}"
  export SECOND_SIGHT_SCENARIO_PATH="${SECOND_SIGHT_SCENARIO_PATH:-$ROOT_DIR/configs/scenarios/all-faults.yaml}"
  export SECOND_SIGHT_LATENCY_OUTPUT="${SECOND_SIGHT_LATENCY_OUTPUT:-live.jsonl}"
  export OPENADKIT_SCENARIO_PATH="${OPENADKIT_SCENARIO_PATH:-/autoware/scenario-sim/scenario/yield_maneuver_demo.yaml}"
  export OPENADKIT_ROUTE_ID="${OPENADKIT_ROUTE_ID:-yield-maneuver}"
  if [[ ! "$OPENADKIT_ROUTE_ID" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "OPENADKIT_ROUTE_ID must contain lowercase letters, digits, and hyphens." >&2
    exit 1
  fi
  export SECOND_SIGHT_UID="${SECOND_SIGHT_UID:-$(id -u)}"
  export SECOND_SIGHT_GID="${SECOND_SIGHT_GID:-$(id -g)}"
  COMPOSE=(
    docker compose
    --project-name "$COMPOSE_PROJECT_NAME"
    --file "$OPENADKIT_DIR/docker/docker-compose.yml"
    --file "$ROOT_DIR/configs/openadkit-compose.override.yaml"
  )
}

command="${1:-}"
case "$command" in
  setup)
    require_docker
    setup
    echo "Open AD Kit is pinned at $OPENADKIT_REF"
    ;;
  generate-routes)
    setup
    uv run --project "$ROOT_DIR" python "$ROOT_DIR/scripts/generate-route-variants.py" \
      --base "$OPENADKIT_DIR/docker/etc/simulation/scenario/yield_maneuver_demo.yaml" \
      --variants "$ROOT_DIR/configs/scenarios/route-variants.yaml" \
      --output-dir "$OPENADKIT_DIR/docker/etc/simulation/scenario"
    ;;
  pull)
    require_docker
    configure
    "${COMPOSE[@]}" pull
    ;;
  start)
    require_docker
    configure
    "${COMPOSE[@]}" up --detach --no-deps visualizer planning-control
    "${COMPOSE[@]}" up --detach --force-recreate simulator
    echo "Open AD Kit is starting at http://localhost:6080/vnc.html"
    echo "VNC password: openadkit"
    ;;
  run)
    require_docker
    configure
    export TIMEOUT="${OPENADKIT_TIMEOUT:-120}"
    "${COMPOSE[@]}" up --detach visualizer
    "${COMPOSE[@]}" up --abort-on-container-exit simulator planning-control
    ;;
  status)
    require_docker
    configure
    "${COMPOSE[@]}" ps
    ;;
  topics)
    require_docker
    configure
    "${COMPOSE[@]}" exec -T planning-control bash -lc \
      "source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && ros2 topic list --show-types"
    ;;
  record)
    require_docker
    configure
    duration="${2:-45}"
    if [[ ! "$duration" =~ ^[1-9][0-9]*$ ]]; then
      echo "Record duration must be a positive number of seconds." >&2
      exit 1
    fi

    "${COMPOSE[@]}" up --detach --no-deps planning-control
    if [[ "${OPENADKIT_WITH_VISUALIZER:-0}" == "1" ]]; then
      "${COMPOSE[@]}" up --detach --no-deps visualizer
    fi
    "${COMPOSE[@]}" up --detach --force-recreate simulator
    echo "Waiting for the trajectory stream..."
    "${COMPOSE[@]}" exec -T planning-control bash -lc \
      "source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && timeout 120 ros2 topic echo --once /planning/scenario_planning/trajectory >/dev/null"

    bag_name="openadkit-clean-${OPENADKIT_ROUTE_ID}-${variant}-$(date -u +%Y%m%dT%H%M%SZ)"
    container_bag="/tmp/$bag_name"
    host_bag="$ROOT_DIR/data/raw/$bag_name"
    docker exec planning-control bash -lc \
      "source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && timeout --signal=INT $duration ros2 bag record --output $container_bag /perception/object_recognition/detection/objects /perception/object_recognition/objects /planning/scenario_planning/trajectory || test \$? -eq 124"
    mkdir -p "$ROOT_DIR/data/raw"
    docker cp "planning-control:$container_bag" "$host_bag"
    echo "Recorded clean bag: $host_bag"
    ;;
  integrated-start)
    require_docker
    configure
    if [[ ! -f "$SECOND_SIGHT_MODEL_PATH" ]]; then
      echo "Second Sight model is missing: $SECOND_SIGHT_MODEL_PATH" >&2
      exit 1
    fi
    if [[ ! -f "$SECOND_SIGHT_SCENARIO_PATH" ]]; then
      echo "Second Sight scenario is missing: $SECOND_SIGHT_SCENARIO_PATH" >&2
      exit 1
    fi
    docker build --file "$ROOT_DIR/components/simulator/Dockerfile" \
      --tag second-sight-simulator:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/fault_injector/Dockerfile" \
      --tag second-sight-fault-injector:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/second_sight/Dockerfile" \
      --tag second-sight-node:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/latency_monitor/Dockerfile" \
      --tag second-sight-latency-monitor:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/dashboard/Dockerfile" \
      --tag second-sight-dashboard:dev "$ROOT_DIR"
    "${COMPOSE[@]}" --file "$ROOT_DIR/configs/openadkit-second-sight.override.yaml" \
      up --detach visualizer fault-injector second-sight latency-monitor dashboard
    echo "Integrated Open AD Kit is starting in Second Sight dry-run mode."
    echo "Visualizer: http://localhost:6080/vnc.html"
    echo "Foxglove: ws://localhost:8765"
    echo "Latency JSONL: reports/measurements/$SECOND_SIGHT_LATENCY_OUTPUT"
    ;;
  integrated-status)
    require_docker
    configure
    "${COMPOSE[@]}" --file "$ROOT_DIR/configs/openadkit-second-sight.override.yaml" ps
    ;;
  integrated-stop)
    require_docker
    configure
    "${COMPOSE[@]}" --file "$ROOT_DIR/configs/openadkit-second-sight.override.yaml" \
      down --remove-orphans
    ;;
  dashboard-start)
    require_docker
    configure
    "${COMPOSE[@]}" --file "$ROOT_DIR/configs/openadkit-second-sight.override.yaml" \
      down --remove-orphans
    docker build --file "$ROOT_DIR/components/fault_injector/Dockerfile" \
      --tag second-sight-fault-injector:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/second_sight/Dockerfile" \
      --tag second-sight-node:dev "$ROOT_DIR"
    docker build --file "$ROOT_DIR/components/dashboard/Dockerfile" \
      --tag second-sight-dashboard:dev "$ROOT_DIR"
    docker compose --file "$ROOT_DIR/configs/dashboard-demo.compose.yaml" up --detach
    echo "Looping second-sight dashboard demo started."
    echo "Foxglove: ws://localhost:8765"
    ;;
  dashboard-status)
    require_docker
    export SECOND_SIGHT_ROOT="$ROOT_DIR"
    docker compose --file "$ROOT_DIR/configs/dashboard-demo.compose.yaml" ps
    ;;
  dashboard-stop)
    require_docker
    export SECOND_SIGHT_ROOT="$ROOT_DIR"
    docker compose --file "$ROOT_DIR/configs/dashboard-demo.compose.yaml" \
      down --remove-orphans
    ;;
  logs)
    require_docker
    configure
    "${COMPOSE[@]}" logs --follow
    ;;
  stop)
    require_docker
    configure
    "${COMPOSE[@]}" down --remove-orphans
    ;;
  *)
    usage
    [[ -n "$command" ]] && exit 1
    ;;
esac
