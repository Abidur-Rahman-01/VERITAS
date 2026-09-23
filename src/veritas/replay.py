import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .calibration import apply_artifact
from .controller import POLICIES, Controller, Risk
from .io import digest, file_hash, read_records, write_json, write_jsonl


def eligible_records(path, artifact, split, scope="semantic"):
    rows, blocked = [], 0
    identifiers, group_splits = set(), defaultdict(set)
    for row in read_records(path):
        group_splits[row["group_id"]].add(row["split"])
        if row["split"] != split:
            continue
        if row["event_id"] in identifiers:
            raise ValueError("Duplicate event IDs in replay")
        identifiers.add(row["event_id"])
        if row.get("blocked"):
            blocked += 1
            continue
        if row["group_id"] in artifact["fit_groups"]:
            raise ValueError("Replay task appears in calibration fit groups")
        if row.get("error_label") is None or row.get("label_scope") != scope:
            raise ValueError(
                "Replay requires independent labels of one scope for EVERY eligible action; adjudicate unknown steps first"
            )
        if not row.get("verification") or row["verification"]["verdict"] == "ERROR":
            raise ValueError(
                "Counterfactual verifier verdict missing; collect audit_all baseline traces"
            )
        if not row.get("audit_only") or row.get("decision") != "skip":
            raise ValueError(
                "Primary replay requires ungated audit_all traces; gated trajectories induce selection bias"
            )
        rows.append(apply_artifact(row, artifact))
    if any(len(values) > 1 for values in group_splits.values()):
        raise ValueError("Task group crosses partitions")
    if not rows:
        raise ValueError(f"No labeled audit records in split {split}")
    if artifact["label_scope"] != scope:
        raise ValueError("Calibration/replay label scopes differ")
    return sorted(rows, key=lambda r: (r["run_id"], r["task_id"], r["step_id"])), blocked


def evaluate(rows, policy, budget, threshold=0.0, dynamic_lambda=0.1, seed=42):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["run_id"], row["task_id"])].append(row)
    results = []
    for (run_id, task_id), steps in sorted(groups.items()):
        stable_seed = int(digest([seed, run_id, task_id])[:16], 16)
        controller = Controller(policy, budget, threshold, dynamic_lambda, stable_seed)
        selected, caught, consequential, true_verified, false_rejections, missed, total_errors = (
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        selected_ids, avoided_weight = [], 0.0
        for row in sorted(steps, key=lambda r: r["step_id"]):
            risk = Risk(**{key: row[key] for key in Risk.__dataclass_fields__})
            error = row["error_label"] == 1
            total_errors += error
            if controller.decide(risk):
                controller.reserve(risk)
                selected += 1
                selected_ids.append(row["event_id"])
                true_verified += error
                detected = error and row["verification"]["verdict"] == "FAIL"
                caught += detected
                consequential += detected and row["impact"] >= 0.5
                avoided_weight += detected * row["impact"] * (1 - row["residual_loss"])
                false_rejections += (not error) and row["verification"]["verdict"] == "FAIL"
                missed += error and not detected
            else:
                missed += error
        results.append(
            {
                "run_id": run_id,
                "task_id": task_id,
                "group_id": steps[0]["group_id"],
                "selected": selected,
                "errors_caught": caught,
                "consequential_caught": consequential,
                "true_errors_verified": true_verified,
                "total_errors": total_errors,
                "false_rejections": false_rejections,
                "missed_errors": missed,
                "impact_weight_caught": avoided_weight,
                "spent": float(controller.budget.spent),
                "budget": budget,
                "budget_violation": controller.budget.spent > controller.budget.total,
                "selected_event_ids": selected_ids,
            }
        )
    totals = {
        key: sum(row[key] for row in results)
        for key in (
            "selected",
            "errors_caught",
            "consequential_caught",
            "true_errors_verified",
            "total_errors",
            "false_rejections",
            "missed_errors",
            "impact_weight_caught",
            "spent",
            "budget_violation",
        )
    }
    totals.update(
        {
            "policy": policy,
            "budget_per_trajectory": budget,
            "threshold": threshold,
            "trajectories": len(results),
            "budget_violation_rate": totals["budget_violation"] / len(results),
            "verification_precision": totals["true_errors_verified"] / totals["selected"]
            if totals["selected"]
            else None,
            "verification_recall": totals["true_errors_verified"] / totals["total_errors"]
            if totals["total_errors"]
            else None,
            "detection_recall": totals["errors_caught"] / totals["total_errors"]
            if totals["total_errors"]
            else None,
        }
    )
    return totals, results


def tune(records, artifact_path, output, budgets, scope="semantic", seed=42):
    artifact = json.loads(Path(artifact_path).read_text())
    rows, _ = eligible_records(records, artifact, "val", scope)
    selections = {}
    for budget in budgets:
        for policy in POLICIES:
            if policy in {"never", "always"}:
                candidates = [0.0]
            elif policy == "random":
                candidates = [0.25, 0.5, 0.75, 1.0]
            elif policy in {"rcvov", "bavar_style"}:
                candidates = [-1.0, 0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
            else:
                candidates = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
            scored = [evaluate(rows, policy, budget, threshold=t, seed=seed)[0] for t in candidates]
            best = max(
                scored,
                key=lambda r: (
                    r["consequential_caught"],
                    r["errors_caught"],
                    -r["false_rejections"],
                    -r["spent"],
                ),
            )
            selections[f"{policy}:{budget:g}"] = best["threshold"]
    result = {
        "version": 1,
        "seed": seed,
        "split": "val",
        "label_scope": scope,
        "fit_groups": sorted({r["group_id"] for r in rows}),
        "thresholds": selections,
        "artifact_sha256": file_hash(Path(artifact_path)),
        "records_sha256": file_hash(Path(records)),
    }
    write_json(output, result)
    return result


def paired_bootstrap(a, b, metric="consequential_caught", repetitions=1000, seed=42):
    """Resample tasks, keeping repeated backbone runs for each task in one cluster."""
    grouped = defaultdict(list)
    lookup = {(r["run_id"], r["task_id"]): r for r in b}
    if {(r["run_id"], r["task_id"]) for r in a} != set(lookup):
        raise ValueError("Paired bootstrap requires identical trajectories")
    for row in a:
        other = lookup[(row["run_id"], row["task_id"])]
        grouped[row["group_id"]].append(row[metric] - other[metric])
    differences = np.array([np.mean(v) for v in grouped.values()])
    if not len(differences):
        raise ValueError("No paired tasks")
    rng = np.random.default_rng(seed)
    samples = [
        float(rng.choice(differences, size=len(differences), replace=True).mean())
        for _ in range(repetitions)
    ]
    return {
        "metric": metric,
        "mean_difference_per_task": float(differences.mean()),
        "ci95": np.quantile(samples, [0.025, 0.975]).tolist(),
        "clusters": len(differences),
    }


def sweep(
    records, artifact_path, tuning_path, output, budgets, split="test", scope="semantic", seed=42
):
    artifact = json.loads(Path(artifact_path).read_text())
    tuning = json.loads(Path(tuning_path).read_text())
    if tuning["artifact_sha256"] != file_hash(Path(artifact_path)):
        raise ValueError("Tuning/calibration artifact mismatch")
    rows, blocked = eligible_records(records, artifact, split, scope)
    if split != "val" and any(r["group_id"] in tuning["fit_groups"] for r in rows):
        raise ValueError("Evaluation overlaps threshold tuning groups")
    output = Path(output)
    if (output / "manifest.json").exists():
        raise ValueError("Replay output already frozen; use a new directory")
    output.mkdir(parents=True, exist_ok=True)
    summaries, detail, comparisons = [], [], []
    for budget in budgets:
        per_policy = {}
        for policy in POLICIES:
            key = f"{policy}:{budget:g}"
            if key not in tuning["thresholds"]:
                raise ValueError(f"Budget/policy {key} was not tuned on validation data")
            summary, tasks = evaluate(rows, policy, budget, tuning["thresholds"][key], seed=seed)
            summaries.append(summary)
            detail.extend({**r, "policy": policy} for r in tasks)
            per_policy[policy] = tasks
        for baseline in ("confidence", "risk", "error_impact", "bavar_style"):
            comparisons.append(
                {
                    "budget": budget,
                    "comparison": "rcvov - " + baseline,
                    **paired_bootstrap(per_policy["rcvov"], per_policy[baseline], seed=seed),
                }
            )
    write_jsonl(output / "frontier.jsonl", summaries)
    write_jsonl(output / "per_task.jsonl", detail)
    write_json(output / "paired_bootstrap.json", comparisons)
    manifest = {
        "split": split,
        "label_scope": scope,
        "eligible_actions": len(rows),
        "floor_blocked": blocked,
        "records_sha256": file_hash(Path(records)),
        "artifact_sha256": file_hash(Path(artifact_path)),
        "tuning_sha256": file_hash(Path(tuning_path)),
        "seed": seed,
        "interpretation": "Fixed-trajectory allocation diagnostic; no causal task-success estimates",
    }
    write_json(output / "manifest.json", manifest)
    return summaries
