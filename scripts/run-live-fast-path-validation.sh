#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-live-fast-path-validation.sh RUN_PREFIX [REPETITIONS]

Run fresh Arm live trials for each deterministic fault scenario. The caller
must archive and inspect raw measurements before publishing a percentile report.
EOF
}

run_prefix="${1:-}"
repetitions="${2:-5}"
if [[ -z "$run_prefix" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$run_prefix" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "RUN_PREFIX may contain only letters, numbers, dots, underscores, and hyphens." >&2
  exit 1
fi
if ! [[ "$repetitions" =~ ^[1-9][0-9]*$ ]]; then
  echo "REPETITIONS must be a positive integer." >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SECOND_SIGHT_NODE_ARGS="${SECOND_SIGHT_NODE_ARGS:---enable-perception-fast-path --enable-perception-liveness}"
# Teleport is deliberately excluded: the current short simulator scenario
# reaches its natural end before the trajectory-hybrid reference path can be
# causally validated. Do not turn end-of-stream liveness into teleport timing.
scenarios=(vanish phantom freeze confidence-collapse liveness)

for scenario in "${scenarios[@]}"; do
  for ((repetition = 1; repetition <= repetitions; repetition++)); do
    printf -v repetition_id '%02d' "$repetition"
    run_id="${run_prefix}-${scenario}-r${repetition_id}"
    "$root_dir/scripts/run-live-latency-trial.sh" \
      "$run_id" "$root_dir/configs/scenarios/latency/${scenario}.yaml" 180
  done
done
