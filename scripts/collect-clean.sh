#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.cache"
PID_FILE="$STATE_DIR/clean-collection.pid"
LOG_FILE="$STATE_DIR/clean-collection.log"
MIN_FREE_KB=$((10 * 1024 * 1024))

usage() {
  cat <<'EOF'
Usage: ./scripts/collect-clean.sh COMMAND [HOURS]

Commands:
  start [HOURS]  Start background collection (default: 8 hours)
  status         Show collector status and bag count
  logs           Follow the collection log
  stop           Stop collection and Open AD Kit containers
EOF
}

read_pid() {
  [[ -f "$PID_FILE" ]] && read -r collector_pid < "$PID_FILE"
  collector_pid="${collector_pid:-}"
}

is_running() {
  read_pid
  [[ "$collector_pid" =~ ^[0-9]+$ ]] && kill -0 "$collector_pid" 2>/dev/null
}

bag_count() {
  shopt -s nullglob
  local bags=("$ROOT_DIR"/data/raw/openadkit-clean-*)
  echo "${#bags[@]}"
}

free_disk_kb() {
  local filesystem blocks used available capacity mounted
  local result=0
  while read -r filesystem blocks used available capacity mounted; do
    if [[ "$available" =~ ^[0-9]+$ ]]; then
      result="$available"
    fi
  done < <(df -Pk "$ROOT_DIR")
  echo "$result"
}

run_collection() {
  local hours="$1"
  local started_at end_at run_number variant caffeinate_pid
  started_at="$(date +%s)"
  end_at=$((started_at + hours * 3600))
  run_number=0
  caffeinate_pid=""

  if command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dimsu -w "$$" &
    caffeinate_pid=$!
  fi

  cleanup() {
    "$ROOT_DIR/scripts/openadkit.sh" stop || true
    if [[ -n "$caffeinate_pid" ]]; then
      kill "$caffeinate_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  }
  stop_collection() {
    exit 0
  }
  trap cleanup EXIT
  trap stop_collection INT TERM

  echo "Starting ${hours}-hour clean-data collection at $(date -u)."
  while (( $(date +%s) < end_at )); do
    if (( $(free_disk_kb) < MIN_FREE_KB )); then
      echo "Stopping because free disk space is below 10 GB."
      break
    fi

    if (( run_number % 2 == 0 )); then
      variant="pass"
    else
      variant="fail"
    fi
    run_number=$((run_number + 1))
    echo "Starting run $run_number with variant '$variant' at $(date -u)."
    if ! OPENADKIT_VARIANT="$variant" "$ROOT_DIR/scripts/openadkit.sh" record 45; then
      echo "Run $run_number failed; waiting 10 seconds before retrying."
      sleep 10
    fi
  done
  echo "Collection finished after $run_number attempted runs at $(date -u)."
}

command="${1:-}"
case "$command" in
  start)
    hours="${2:-8}"
    if [[ ! "$hours" =~ ^[1-9][0-9]*$ ]]; then
      echo "Hours must be a positive integer." >&2
      exit 1
    fi
    if is_running; then
      echo "Collection is already running with PID $collector_pid."
      exit 1
    fi
    mkdir -p "$STATE_DIR"
    : > "$LOG_FILE"
    nohup "$0" run "$hours" >> "$LOG_FILE" 2>&1 &
    collector_pid=$!
    echo "$collector_pid" > "$PID_FILE"
    echo "Started ${hours}-hour collection with PID $collector_pid."
    echo "Log: $LOG_FILE"
    ;;
  run)
    run_collection "${2:-8}"
    ;;
  status)
    if is_running; then
      echo "Collection is running with PID $collector_pid."
    else
      echo "Collection is not running."
    fi
    echo "Recorded bags: $(bag_count)"
    echo "Free disk: $(( $(free_disk_kb) / 1024 / 1024 )) GB"
    ;;
  logs)
    touch "$LOG_FILE"
    tail -n 30 -f "$LOG_FILE"
    ;;
  stop)
    if is_running; then
      kill "$collector_pid"
      echo "Sent stop signal to collector PID $collector_pid."
    else
      echo "Collection is not running."
      rm -f "$PID_FILE"
    fi
    "$ROOT_DIR/scripts/openadkit.sh" stop || true
    ;;
  *)
    usage
    [[ -n "$command" ]] && exit 1
    ;;
esac
