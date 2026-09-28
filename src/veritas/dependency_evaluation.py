"""Freeze confirmation tasks and evaluate complete method-by-task ledgers."""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .dependency_cohort import verify_cohort
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl

REQUIRED_METRICS = (
    "success", "continuation_cost", "deployment_cost", "tokens", "latency_seconds",
    "model_calls", "verifier_errors", "missing_triggers", "intervention_regressions",
)


def freeze_evaluation(cohort, methods_file, output, seed=42):
    """Freeze independent confirmation tasks and method identities before evaluation."""
    output = Path(output)
    if output.exists():
        raise ValueError("Evaluation output already exists; use a new directory")
    verify_cohort(cohort)
    cohort = Path(cohort)
    protocol = json.loads((cohort / "protocol.json").read_text())
    if not protocol.get("outcome_blind_freeze"):
        raise ValueError("Confirmation evaluation requires an outcome-blind frozen protocol")
    methods_spec = json.loads(Path(methods_file).read_text())
    if not isinstance(methods_spec, dict):
        raise ValueError("Methods file must be an object with methods, baseline, and primary_method")
    methods = methods_spec.get("methods")
    if not isinstance(methods, list) or len(methods) < 2:
        raise ValueError("Methods file must list at least two evaluation methods")
    method_ids = [row.get("method_id") for row in methods]
    if any(not isinstance(value, str) or not value for value in method_ids):
        raise ValueError("Every method requires a nonempty method_id")
    if len(method_ids) != len(set(method_ids)):
        raise ValueError("Method identifiers must be unique")
    if methods_spec.get("baseline") not in method_ids or methods_spec.get("primary_method") not in method_ids:
        raise ValueError("baseline and primary_method must name listed methods")
    if methods_spec["baseline"] == methods_spec["primary_method"]:
        raise ValueError("Primary method must differ from baseline")
    selected = [row for row in read_jsonl(cohort / "cohort.jsonl")
                if row["research_partition"] == "confirmation"]
    selected.sort(key=lambda row: digest([seed, row["task_id"]]))
    if not selected:
        raise ValueError("Frozen cohort has no confirmation tasks")
    jobs = [{"task_id": row["task_id"], "group_id": row["group_id"],
             "source": row["source"], "method_id": method}
            for row in selected for method in method_ids]
    plan = {
        "version": 1,
        "cohort_manifest_sha256": file_hash(cohort / "manifest.json"),
        "cohort_protocol_sha256": file_hash(cohort / "protocol.json"),
        "methods_file_sha256": file_hash(Path(methods_file)),
        "cohort_directory": str(cohort.resolve()),
        "methods_file": str(Path(methods_file).resolve()),
        "methods": methods,
        "baseline": methods_spec["baseline"],
        "primary_method": methods_spec["primary_method"],
        "multiplicity_plan": "primary comparison designated before evaluation; other comparisons descriptive",
        "tasks": [{"task_id": row["task_id"], "group_id": row["group_id"],
                   "source": row["source"]} for row in selected],
        "jobs": jobs,
        "task_count": len(selected),
        "method_count": len(methods),
        "job_count": len(jobs),
        "seed": seed,
        "partition": "confirmation",
        "metrics": list(REQUIRED_METRICS),
        "outcome_blind_frozen": True,
        "status": "frozen_pending_execution",
    }
    plan["evaluation_id"] = digest(plan)
    output.mkdir(parents=True)
    write_json(output / "evaluation.json", plan)
    write_jsonl(output / "results.jsonl", [])
    return plan


def _read_plan(directory):
    directory = Path(directory)
    plan = json.loads((directory / "evaluation.json").read_text())
    expected = dict(plan)
    identity = expected.pop("evaluation_id")
    if digest(expected) != identity:
        raise ValueError("Evaluation plan changed")
    cohort = Path(plan["cohort_directory"])
    if file_hash(cohort / "manifest.json") != plan["cohort_manifest_sha256"]:
        raise ValueError("Frozen cohort manifest changed")
    if file_hash(cohort / "protocol.json") != plan["cohort_protocol_sha256"]:
        raise ValueError("Frozen cohort protocol changed")
    if file_hash(Path(plan["methods_file"])) != plan["methods_file_sha256"]:
        raise ValueError("Frozen evaluation methods changed")
    return plan


def report_evaluation(directory, results_file=None, bootstrap_repetitions=4000):
    directory = Path(directory)
    plan = _read_plan(directory)
    results_path = Path(results_file) if results_file else directory / "results.jsonl"
    rows = list(read_jsonl(results_path))
    required_pairs = {(job["task_id"], job["method_id"]) for job in plan["jobs"]}
    by_pair = {}
    for row in rows:
        key = (row.get("task_id"), row.get("method_id"))
        if key not in required_pairs:
            raise ValueError(f"Result outside frozen task/method set: {key}")
        if key in by_pair:
            raise ValueError(f"Duplicate result for frozen task/method: {key}")
        if any(metric not in row for metric in REQUIRED_METRICS):
            raise ValueError(f"Result missing required metrics for {key}")
        if row["success"] not in (0, 1, False, True):
            raise ValueError("success must be binary")
        for metric in REQUIRED_METRICS[1:]:
            value = row[metric]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Metric {metric} must be a finite number")
            if metric in {"continuation_cost", "deployment_cost", "tokens", "latency_seconds",
                          "model_calls", "verifier_errors", "missing_triggers",
                          "intervention_regressions"} and value < 0:
                raise ValueError(f"Metric {metric} cannot be negative")
        by_pair[key] = row
    missing = sorted(required_pairs - set(by_pair))
    report = {
        "evaluation_id": plan["evaluation_id"],
        "partition": "confirmation",
        "frozen_tasks": plan["task_count"],
        "methods": [method["method_id"] for method in plan["methods"]],
        "baseline": plan["baseline"],
        "primary_method": plan["primary_method"],
        "multiplicity_plan": plan["multiplicity_plan"],
        "results_sha256": file_hash(results_path),
        "completed_pairs": len(by_pair),
        "expected_pairs": len(required_pairs),
        "missing_pairs": [{"task_id": task, "method_id": method} for task, method in missing],
        "complete": not missing,
        "estimates": {},
        "comparisons": [],
        "status": "incomplete_no_confirmatory_estimates" if missing else "complete",
        "note": "Complete task sets required; uncertainty resamples group_id clusters.",
    }
    if not missing:
        groups = {task["task_id"]: task["group_id"] for task in plan["tasks"]}
        rng = np.random.default_rng(plan["seed"])
        method_ids = report["methods"]
        for method in method_ids:
            data = [by_pair[(task["task_id"], method)] for task in plan["tasks"]]
            per_group = defaultdict(list)
            for task, row in zip(plan["tasks"], data):
                per_group[groups[task["task_id"]]].append(row)
            estimate = {}
            for metric in REQUIRED_METRICS:
                cluster_values = [float(np.mean([row[metric] for row in group]))
                                  for group in per_group.values()]
                draws = [float(rng.choice(cluster_values, len(cluster_values), replace=True).mean())
                         for _ in range(bootstrap_repetitions)]
                estimate[metric] = {
                    "mean": float(np.mean(cluster_values)),
                    "ci95": np.quantile(draws, [0.025, 0.975]).tolist(),
                }
            report["estimates"][method] = estimate
        baseline = plan["baseline"]
        for method in method_ids:
            if method == baseline:
                continue
            paired_by_group = defaultdict(lambda: defaultdict(list))
            for task in plan["tasks"]:
                group = groups[task["task_id"]]
                left = by_pair[(task["task_id"], method)]
                right = by_pair[(task["task_id"], baseline)]
                for metric in ("success", "continuation_cost", "deployment_cost"):
                    paired_by_group[group][metric].append(float(left[metric]) - float(right[metric]))
            deltas = {}
            for metric in ("success", "continuation_cost", "deployment_cost"):
                values = [float(np.mean(group[metric])) for group in paired_by_group.values()]
                draws = [float(rng.choice(values, len(values), replace=True).mean())
                         for _ in range(bootstrap_repetitions)]
                deltas[metric] = {"mean_delta": float(np.mean(values)),
                                  "ci95": np.quantile(draws, [0.025, 0.975]).tolist()}
            report["comparisons"].append({
                "method": method,
                "baseline": baseline,
                "primary": method == plan["primary_method"],
                "deltas": deltas,
            })
    write_json(directory / "evaluation-report.json", report)
    with (directory / "evaluation-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["method_id", "metric", "mean", "ci95_low", "ci95_high"])
        for method, metrics in report["estimates"].items():
            for metric, value in metrics.items():
                writer.writerow([method, metric, value["mean"], *value["ci95"]])
    return report
