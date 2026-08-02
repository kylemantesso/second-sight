#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose --profile ros-smoke down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose --profile ros-smoke up \
  --abort-on-container-exit \
  --exit-code-from ros-subscriber
