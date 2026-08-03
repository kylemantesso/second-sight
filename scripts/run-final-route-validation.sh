#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-final-route-validation.sh RUN_ID COHORT_MANIFEST

Train on the manifest's train route family, calibrate thresholds only on its
validation route family, then evaluate the untouched final-test route clean and
with deterministic injected faults. RUN_ID is immutable: an existing output is
refused rather than overwritten.
EOF
}

run_id="${1:-}"
manifest_path="${2:-}"
if [[ -z "$run_id" || -z "$manifest_path" || ! -f "$manifest_path" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$run_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "RUN_ID may contain only letters, numbers, dots, underscores, and hyphens." >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
feature_dir="$root_dir/data/processed/clean-features"
stream_dir="$root_dir/data/processed/clean-streams"
report_dir="$root_dir/reports/measurements/$run_id"
work_dir="$root_dir/data/processed/final-route-validation/$run_id"
unfrozen_model="$root_dir/models/$run_id-uncalibrated-25tree.joblib"
frozen_model="$root_dir/models/$run_id-frozen-25tree.joblib"
scenario_path="$root_dir/configs/scenarios/all-faults.yaml"
no_faults_path="$root_dir/configs/ground_truth/no-faults.json"

if [[ -e "$report_dir" || -e "$work_dir" || -e "$unfrozen_model" || -e "$frozen_model" ]]; then
  echo "Refusing to overwrite an existing final-validation artifact for $run_id." >&2
  exit 1
fi

get_files() {
  local cohort="$1"
  local directory="$2"
  local suffix="$3"
  uv run --project "$root_dir" second-sight cohort-files \
    --manifest "$manifest_path" --cohort "$cohort" --directory "$directory" --suffix "$suffix"
}

mapfile -t train_features < <(get_files train "$feature_dir" .csv)
mapfile -t validation_features < <(get_files validation "$feature_dir" .csv)
mapfile -t final_streams < <(get_files final_test "$stream_dir" .jsonl)
if (( ${#train_features[@]} == 0 || ${#validation_features[@]} == 0 || ${#final_streams[@]} == 0 )); then
  echo "Each frozen cohort needs exported streams and feature CSVs before final validation." >&2
  exit 1
fi

mkdir -p "$report_dir" "$work_dir"
uv run --project "$root_dir" second-sight train "${train_features[@]}" \
  --output "$unfrozen_model" --trees 25 --min-rows-per-dataset 300
uv run --project "$root_dir" second-sight calibrate "${validation_features[@]}" \
  --model "$unfrozen_model" --output "$frozen_model" --target-clean-fpr 0.01 \
  --min-rows-per-dataset 300

clean_reports=()
fault_reports=()
for stream_path in "${final_streams[@]}"; do
  stem="$(basename "${stream_path%.jsonl}")"
  feature_path="$feature_dir/$stem-features.csv"
  if [[ ! -f "$feature_path" || $(( $(wc -l < "$feature_path") - 1 )) -lt 300 ]]; then
    echo "Skipping final-test stream without 300 complete feature ticks: $stem" >&2
    continue
  fi
  clean_report="$report_dir/$stem-clean-evaluation.json"
  fault_stream="$work_dir/$stem-all-faults.jsonl"
  ground_truth="$work_dir/$stem-all-faults.ground-truth.json"
  fault_report="$report_dir/$stem-fault-evaluation.json"
  uv run --project "$root_dir" second-sight evaluate "$stream_path" \
    --model "$frozen_model" --ground-truth "$no_faults_path" --mode hybrid --output "$clean_report"
  uv run --project "$root_dir" second-sight inject "$stream_path" \
    --scenario "$scenario_path" --output "$fault_stream" --ground-truth "$ground_truth"
  uv run --project "$root_dir" second-sight evaluate "$fault_stream" \
    --model "$frozen_model" --ground-truth "$ground_truth" --mode hybrid --output "$fault_report"
  clean_reports+=("$clean_report")
  fault_reports+=("$fault_report")
done
if (( ${#clean_reports[@]} == 0 )); then
  echo "No final-test stream met the minimum tick count." >&2
  exit 1
fi

summary_path="$report_dir/$run_id-summary.json"
uv run --project "$root_dir" second-sight heldout-report --clean-reports "${clean_reports[@]}" \
  --fault-reports "${fault_reports[@]}" --output "$summary_path"
sha256sum "$manifest_path" "$unfrozen_model" "${unfrozen_model%.joblib}.metadata.json" \
  "$frozen_model" "${frozen_model%.joblib}.metadata.json" "$scenario_path" "$no_faults_path" \
  "$summary_path" "${clean_reports[@]}" "${fault_reports[@]}" >"$report_dir/$run_id-SHA256SUMS"

echo "Frozen model: $frozen_model"
echo "Final report: $summary_path"
