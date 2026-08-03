"""Small developer CLI for the portable Second Sight package."""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

from second_sight import __version__
from second_sight.benchmark import benchmark_model
from second_sight.cohorts import COHORT_NAMES, select_manifest_cohort_files
from second_sight.faults import inject_file, load_scenario
from second_sight.features import extract_features, valid_feature_csv, write_feature_csv
from second_sight.heldout import aggregate_heldout_evaluations
from second_sight.latency import aggregate_latency_runs
from second_sight.model import calibrate_model, evaluate_model, train_model
from second_sight.stream import iter_events, summarize_stream


def environment_report() -> dict[str, str]:
    """Return the local tools relevant to the development workflow."""
    return {
        "second-sight": __version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "docker": "found" if shutil.which("docker") else "missing",
        "uv": "found" if shutil.which("uv") else "missing",
    }


def doctor() -> int:
    report = environment_report()
    width = max(map(len, report))
    for name, value in report.items():
        print(f"{name:<{width}}  {value}")

    missing = [name for name in ("docker", "uv") if report[name] == "missing"]
    if missing:
        print(f"Missing required tools: {', '.join(missing)}", file=sys.stderr)
        return 1

    if platform.system() == "Darwin":
        print("\nmacOS is for correctness only; benchmark performance on Arm Linux.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="second-sight")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor", help="check the local development environment")
    inspect_parser = subcommands.add_parser("inspect", help="summarize a portable event stream")
    inspect_parser.add_argument("stream", type=Path)
    inject_parser = subcommands.add_parser("inject", help="inject faults into an event stream")
    inject_parser.add_argument("stream", type=Path)
    inject_parser.add_argument("--scenario", type=Path, required=True)
    inject_parser.add_argument("--output", type=Path, required=True)
    inject_parser.add_argument("--ground-truth", type=Path)
    features_parser = subcommands.add_parser("features", help="extract per-tick features")
    features_parser.add_argument("stream", type=Path)
    features_parser.add_argument("--output", type=Path, required=True)
    batch_parser = subcommands.add_parser("features-batch", help="extract multiple streams")
    batch_parser.add_argument("streams", type=Path, nargs="+")
    batch_parser.add_argument("--output-dir", type=Path, required=True)
    batch_parser.add_argument("--skip-existing", action="store_true")
    train_parser = subcommands.add_parser("train", help="train an Isolation Forest on clean data")
    train_parser.add_argument("datasets", type=Path, nargs="+")
    train_parser.add_argument("--output", type=Path, required=True)
    train_parser.add_argument("--trees", type=int, default=300)
    train_parser.add_argument("--threshold-quantile", type=float, default=0.99)
    train_parser.add_argument("--min-rows-per-dataset", type=int, default=1)
    calibrate_parser = subcommands.add_parser(
        "calibrate", help="freeze hybrid thresholds using clean validation data only"
    )
    calibrate_parser.add_argument("datasets", type=Path, nargs="+")
    calibrate_parser.add_argument("--model", type=Path, required=True)
    calibrate_parser.add_argument("--output", type=Path, required=True)
    calibrate_parser.add_argument("--target-clean-fpr", type=float, default=0.01)
    calibrate_parser.add_argument("--min-rows-per-dataset", type=int, default=1)
    evaluate_parser = subcommands.add_parser("evaluate", help="evaluate a model on an event stream")
    evaluate_parser.add_argument("stream", type=Path)
    evaluate_parser.add_argument("--model", type=Path, required=True)
    evaluate_parser.add_argument("--ground-truth", type=Path, required=True)
    evaluate_parser.add_argument("--output", type=Path, required=True)
    evaluate_parser.add_argument(
        "--mode",
        choices=("isolation_forest", "guardrails", "hybrid"),
        default="isolation_forest",
    )
    benchmark_parser = subcommands.add_parser(
        "benchmark", help="measure model inference latency on the current host"
    )
    benchmark_parser.add_argument("stream", type=Path)
    benchmark_parser.add_argument("--model", type=Path, required=True)
    benchmark_parser.add_argument("--output", type=Path, required=True)
    benchmark_parser.add_argument(
        "--mode", choices=("isolation_forest", "guardrails", "hybrid"), default="hybrid"
    )
    benchmark_parser.add_argument("--warmup", type=int, default=1_000)
    benchmark_parser.add_argument("--samples", type=int, default=10_000)
    benchmark_parser.add_argument(
        "--host-label", help="operator-supplied host or instance label recorded in the report"
    )
    benchmark_parser.add_argument(
        "--implementation",
        choices=("reference", "optimized"),
        default="optimized",
        help="use the full reference path or the optimized guardrail-only fast path",
    )
    latency_report_parser = subcommands.add_parser(
        "latency-report", help="aggregate completed live fault-to-stop JSONL traces"
    )
    latency_report_parser.add_argument("traces", type=Path, nargs="+")
    latency_report_parser.add_argument("--output", type=Path, required=True)
    heldout_report_parser = subcommands.add_parser(
        "heldout-report", help="aggregate disjoint clean and injected-fault evaluations"
    )
    heldout_report_parser.add_argument("--clean-reports", type=Path, nargs="+", required=True)
    heldout_report_parser.add_argument("--fault-reports", type=Path, nargs="+", required=True)
    heldout_report_parser.add_argument("--output", type=Path, required=True)
    cohort_files_parser = subcommands.add_parser(
        "cohort-files", help="list one frozen cohort's route-matched artifacts"
    )
    cohort_files_parser.add_argument("--manifest", type=Path, required=True)
    cohort_files_parser.add_argument("--cohort", choices=COHORT_NAMES, required=True)
    cohort_files_parser.add_argument("--directory", type=Path, required=True)
    cohort_files_parser.add_argument("--suffix", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "inspect":
        summary = summarize_stream(args.stream)
        print(f"events       {summary.event_count}")
        print(f"duration     {summary.duration_seconds:.3f} s")
        for kind, count in sorted(summary.counts.items()):
            rate = summary.rates_hz[kind]
            print(f"{kind:<12} {count} ({rate:.3f} Hz)")
        if summary.detection_frames:
            print(f"objects      {summary.object_count} across {summary.detection_frames} frames")
        if summary.fault_event_count:
            print(f"fault events {summary.fault_event_count}")
        return 0
    if args.command == "inject":
        scenario = load_scenario(args.scenario)
        ground_truth = args.ground_truth or args.output.with_suffix(".ground-truth.json")
        report = inject_file(args.stream, args.output, ground_truth, scenario)
        print(f"Injected stream: {args.output}")
        print(f"Ground truth:   {ground_truth}")
        for fault in report["faults"]:
            print(
                f"{fault['id']}: {fault['modified_events']} modified, "
                f"{fault['dropped_events']} dropped"
            )
        return 0
    if args.command == "features":
        rows = extract_features(iter_events(args.stream))
        write_feature_csv(args.output, rows)
        print(f"Extracted {len(rows)} ticks to {args.output}")
        return 0
    if args.command == "features-batch":
        extracted = 0
        skipped = 0
        for stream in args.streams:
            output = args.output_dir / f"{stream.stem}-features.csv"
            if args.skip_existing and valid_feature_csv(output):
                skipped += 1
                continue
            rows = extract_features(iter_events(stream))
            if not rows:
                print(f"Skipping stream without complete ticks: {stream.name}")
                continue
            write_feature_csv(output, rows)
            print(f"Extracted {len(rows)} ticks from {stream.name}")
            extracted += 1
        print(f"Completed: {extracted} extracted, {skipped} skipped")
        return 0
    if args.command == "train":
        metadata = train_model(
            args.datasets,
            args.output,
            trees=args.trees,
            threshold_quantile=args.threshold_quantile,
            min_rows_per_dataset=args.min_rows_per_dataset,
        )
        print(f"Model:       {args.output}")
        print(f"Clean ticks: {metadata['training_rows']}")
        print(
            f"Datasets:    {len(metadata['training_datasets'])} used, "
            f"{len(metadata['skipped_datasets'])} skipped"
        )
        print(f"Features:    {len(metadata['feature_names'])}")
        print(f"Threshold:   {metadata['threshold']:.6f}")
        return 0
    if args.command == "calibrate":
        metadata = calibrate_model(
            args.model,
            args.datasets,
            args.output,
            target_clean_fpr=args.target_clean_fpr,
            min_rows_per_dataset=args.min_rows_per_dataset,
        )
        calibration = metadata["calibration"]
        print(f"Model:       {args.output}")
        print(f"Validation:  {calibration['validation_rows']} clean ticks")
        print(f"Target FPR:  {calibration['target_clean_fpr']:.3%}")
        print(
            "Observed FPR: "
            f"{calibration['observed_validation_false_positive_rate']:.3%}"
        )
        return 0
    if args.command == "evaluate":
        report = evaluate_model(
            args.stream, args.model, args.ground_truth, args.output, mode=args.mode
        )
        print(f"Evaluation:          {args.output}")
        print(f"Detector:            {args.mode}")
        print(f"Ticks:               {report['tick_count']}")
        print(f"False-positive rate: {report['false_positive_rate']:.3%}")
        for fault in report["faults"]:
            latency = fault["time_to_detect_ms"]
            latency_text = f"{latency:.1f} ms" if latency is not None else "missed"
            triggers = ", ".join(fault["guardrail_features"])
            trigger_text = f" [{triggers}]" if triggers else ""
            print(f"{fault['id']:<24} {latency_text}{trigger_text}")
        return 0
    if args.command == "benchmark":
        report = benchmark_model(
            args.model,
            args.stream,
            args.output,
            mode=args.mode,
            warmup=args.warmup,
            samples=args.samples,
            host_label=args.host_label,
            implementation=args.implementation,
        )
        latency = report["inference_us"]
        print(f"Benchmark: {args.output}")
        print(f"Samples:   {report['sample_count']}")
        print(f"p50:       {latency['p50']:.1f} us")
        print(f"p99:       {latency['p99']:.1f} us")
        return 0
    if args.command == "latency-report":
        report = aggregate_latency_runs(args.traces, args.output)
        print(f"Summary: {args.output}")
        print(f"Traces:  {report['trace_count']}")
        for group in report["groups"]:
            latency = group["fault_to_safe_stop_ms"]
            print(
                f"{group['fault_id']:<24} n={group['run_count']} "
                f"p50={latency['p50']:.3f} ms p99={latency['p99']:.3f} ms"
            )
        return 0
    if args.command == "heldout-report":
        report = aggregate_heldout_evaluations(
            args.clean_reports, args.fault_reports, args.output
        )
        clean = report["clean_cohort"]
        print(f"Report:     {args.output}")
        print(f"Clean runs: {clean['report_count']}")
        print(f"Clean FPR:  {clean['false_positive_rate']:.3%}")
        for fault in report["injected_fault_cohort"]["faults"]:
            rate = fault["detection_rate"]
            rate_text = f"{rate:.0%}" if rate is not None else "n/a"
            print(
                f"{fault['id']}: {fault['detected_runs']}/{fault['evaluable_run_count']} "
                f"({rate_text})"
            )
        return 0
    if args.command == "cohort-files":
        for path in select_manifest_cohort_files(
            args.manifest, args.cohort, args.directory, suffix=args.suffix
        ):
            print(path)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
