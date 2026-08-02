#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/capture-container-resources.sh OUTPUT.tsv DURATION_SECONDS [INTERVAL_SECONDS]

Poll Docker's one-shot stats for the Second Sight watchdog and the core
simulator/injector/planning path. Run this alongside an integrated Arm test.
EOF
}

output_path="${1:-}"
duration_seconds="${2:-}"
interval_seconds="${3:-1}"

if [[ -z "$output_path" || -z "$duration_seconds" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$duration_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "DURATION_SECONDS must be a positive integer." >&2
  exit 1
fi
if ! [[ "$interval_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]] || [[ "$interval_seconds" == "0" ]]; then
  echo "INTERVAL_SECONDS must be a positive number." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running." >&2
  exit 1
fi

containers=(
  second-sight-openadkit-second-sight-1
  second-sight-openadkit-fault-injector-1
  simulator
  planning-control
)

mkdir -p "$(dirname "$output_path")"
printf 'timestamp_utc\tcontainer\tcpu_percent\tmemory_usage_limit\tmemory_percent\n' \
  >"$output_path"

end_epoch=$(( $(date +%s) + duration_seconds ))
while (( $(date +%s) < end_epoch )); do
  active=()
  for container in "${containers[@]}"; do
    if docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null \
      | grep -qx true; then
      active+=("$container")
    fi
  done
  if (( ${#active[@]} == 0 )); then
    echo "No core Second Sight containers are running." >&2
    exit 1
  fi

  timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
  docker stats --no-stream \
    --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' \
    "${active[@]}" \
    | while IFS= read -r row; do
        printf '%s\t%s\n' "$timestamp" "$row" >>"$output_path"
      done
  sleep "$interval_seconds"
done

echo "Wrote resource samples to $output_path"
