#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run-heldout-configuration-validation.sh RUN_ID [TRAIN_COHORT] [HOLDOUT_COHORT]

Train the 25-tree hybrid model on one Open AD Kit planner cohort, then score a
different cohort clean and after deterministic fault injection. Cohorts are
`pass` and `fail`; defaults are `pass` for training and `fail` for hold-out.
This is a no-leakage held-out *configuration* validation, not evidence of
varied-route generalization.
EOF
}

run_id="${1:-}"
training_cohort="${2:-pass}"
holdout_cohort="${3:-fail}"
if [[ -z "$run_id" ]]; then
  usage >&2
  exit 1
fi
if ! [[ "$run_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "RUN_ID may contain only letters, numbers, dots, underscores, and hyphens." >&2
  exit 1
fi
if [[ "$training_cohort" != pass && "$training_cohort" != fail ]]; then
  echo "TRAIN_COHORT must be pass or fail." >&2
  exit 1
fi
if [[ "$holdout_cohort" != pass && "$holdout_cohort" != fail ]]; then
  echo "HOLDOUT_COHORT must be pass or fail." >&2
  exit 1
fi
if [[ "$training_cohort" == "$holdout_cohort" ]]; then
  echo "Training and hold-out cohorts must be different." >&2
  exit 1
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
feature_dir="$root_dir/data/processed/clean-features"
stream_dir="$root_dir/data/processed/clean-streams"
work_dir="$root_dir/data/processed/heldout-configuration/$run_id"
report_dir="$root_dir/reports/measurements/$run_id"
model_path="$root_dir/models/$run_id-25tree.joblib"
scenario_path="$root_dir/configs/scenarios/all-faults.yaml"
no_faults_path="$root_dir/configs/ground_truth/no-faults.json"

shopt -s nullglob
training_features=("$feature_dir"/openadkit-clean-"$training_cohort"-*-features.csv)
holdout_streams=("$stream_dir"/openadkit-clean-"$holdout_cohort"-*.jsonl)
if (( ${#training_features[@]} == 0 )); then
  echo "No $training_cohort-cohort feature datasets found in $feature_dir" >&2
  exit 1
fi
if (( ${#holdout_streams[@]} == 0 )); then
  echo "No $holdout_cohort-cohort streams found in $stream_dir" >&2
  exit 1
fi

mkdir -p "$work_dir" "$report_dir"
rm -f "$model_path" "${model_path%.joblib}.metadata.json"

uv run --project "$root_dir" second-sight train "${training_features[@]}" \
  --output "$model_path" --trees 25 --min-rows-per-dataset 300

clean_reports=()
fault_reports=()
skipped_short_streams=0
for stream_path in "${holdout_streams[@]}"; do
  stem="$(basename "${stream_path%.jsonl}")"
  feature_path="$feature_dir/$stem-features.csv"
  if [[ ! -f "$feature_path" ]]; then
    echo "Skipping $stem: no corresponding feature dataset." >&2
    skipped_short_streams=$((skipped_short_streams + 1))
    continue
  fi
  feature_rows=$(( $(wc -l < "$feature_path") - 1 ))
  if (( feature_rows < 300 )); then
    echo "Skipping $stem: only $feature_rows complete ticks (minimum 300)." >&2
    skipped_short_streams=$((skipped_short_streams + 1))
    continue
  fi
  clean_report="$report_dir/$stem-clean-evaluation.json"
  fault_stream="$work_dir/$stem-all-faults.jsonl"
  ground_truth="$work_dir/$stem-all-faults.ground-truth.json"
  fault_report="$report_dir/$stem-fault-evaluation.json"

  uv run --project "$root_dir" second-sight evaluate "$stream_path" \
    --model "$model_path" --ground-truth "$no_faults_path" --mode hybrid \
    --output "$clean_report"
  uv run --project "$root_dir" second-sight inject "$stream_path" \
    --scenario "$scenario_path" --output "$fault_stream" --ground-truth "$ground_truth"
  uv run --project "$root_dir" second-sight evaluate "$fault_stream" \
    --model "$model_path" --ground-truth "$ground_truth" --mode hybrid \
    --output "$fault_report"

  clean_reports+=("$clean_report")
  fault_reports+=("$fault_report")
done

if (( ${#clean_reports[@]} == 0 )); then
  echo "No hold-out streams met the 300-tick minimum." >&2
  exit 1
fi

summary_path="$report_dir/$run_id-summary.json"
uv run --project "$root_dir" second-sight heldout-report \
  --clean-reports "${clean_reports[@]}" \
  --fault-reports "${fault_reports[@]}" \
  --output "$summary_path"

sha256sum "$model_path" "${model_path%.joblib}.metadata.json" "$summary_path" \
  "$scenario_path" "$no_faults_path" "${clean_reports[@]}" "${fault_reports[@]}" \
  >"$report_dir/$run_id-SHA256SUMS"

echo "Model:   $model_path"
echo "Summary: $summary_path"
echo "Training cohort: $training_cohort"
echo "Hold-out cohort: $holdout_cohort"
echo "Eligible hold-out streams: ${#clean_reports[@]}"
echo "Skipped short streams: $skipped_short_streams"
