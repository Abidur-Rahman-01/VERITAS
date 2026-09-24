import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .calibration import apply_artifact, load_artifact
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


def evaluate(rows, policy, budget, threshold=0.0, dynamic_lambda=0.0, seed=42):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["run_id"], row["task_id"])].append(row)
    results = []
    for (run_id, task_id), steps in sorted(groups.items()):
        stable_seed = int(digest([seed, task_id])[:16], 16)
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
        selected_ids, avoided_weight, false_alarm_loss = [], 0.0, 0.0
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
                false_alarm_loss += (
                    (not error) and row["verification"]["verdict"] == "FAIL"
                ) * row["false_alarm_cost"]
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
                "net_observed_value": avoided_weight
                - float(controller.budget.spent)
                - false_alarm_loss,
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
            "net_observed_value",
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


def _tune(records, artifact_path, budgets, scope="semantic", seed=42, dynamic_lambda=0.0):
    artifact = load_artifact(artifact_path)
    rows, _ = eligible_records(records, artifact, "val", scope)
    selections = {}
    for budget in budgets:
        for policy in POLICIES:
            if policy in {"never", "always"}:
                candidates = [0.0]
            elif policy == "random":
                candidates = [0.25, 0.5, 0.75, 1.0]
            else:
                controller = Controller(policy, budget)
                scores = [
                    controller.score(Risk(**{key: row[key] for key in Risk.__dataclass_fields__}))
                    for row in rows
                ]
                candidates = sorted(
                    set(
                        [
                            float(np.nextafter(min(scores), -np.inf)),
                            0.0,
                            *map(
                                float, np.quantile(scores, np.linspace(0, 1, min(21, len(scores))))
                            ),
                        ]
                    )
                )
            scored = [
                evaluate(
                    rows, policy, budget, threshold=t, seed=seed, dynamic_lambda=dynamic_lambda
                )[0]
                for t in candidates
            ]
            best = max(
                scored,
                key=lambda r: (
                    r["net_observed_value"],
                    r["consequential_caught"],
                    r["errors_caught"],
                    -r["false_rejections"],
                    -r["spent"],
                ),
            )
            selections[f"{policy}:{budget:g}"] = best["threshold"]
    result = {
        "version": 2,
        "seed": seed,
        "dynamic_lambda": dynamic_lambda,
        "budgets": budgets,
        "objective": "net_observed_value_then_consequential_catches",
        "threshold_search": "observed_score_quantiles_21",
        "split": "val",
        "label_scope": scope,
        "fit_groups": sorted({r["group_id"] for r in rows}),
        "thresholds": selections,
        "artifact_sha256": file_hash(Path(artifact_path)),
        "records_sha256": file_hash(Path(records)),
    }
    return result


def tune(records, artifact_path, output, budgets, scope="semantic", seed=42, dynamic_lambda=0.0):
    output = Path(output)
    evidence = output.with_suffix(".evidence.jsonl")
    if output.exists() or evidence.exists():
        raise ValueError("Tuning output already exists; use a new name")
    result = _tune(records, artifact_path, budgets, scope, seed, dynamic_lambda)
    write_jsonl(evidence, read_records(records))
    result["evidence_file"] = evidence.name
    result["evidence_sha256"] = file_hash(evidence)
    write_json(output, result)
    return result


def load_tuning(path, artifact_path):
    path = Path(path)
    tuning = json.loads(path.read_text())
    if tuning.get("version") != 2:
        raise ValueError("Legacy tuning needs to be refitted with current code")
    if tuning["artifact_sha256"] != file_hash(Path(artifact_path)):
        raise ValueError("Tuning/calibration artifact mismatch")
    evidence = path.parent / tuning["evidence_file"]
    if evidence.name != tuning["evidence_file"] or file_hash(evidence) != tuning["evidence_sha256"]:
        raise ValueError("Tuning evidence changed")
    expected = _tune(
        evidence,
        artifact_path,
        tuning["budgets"],
        tuning["label_scope"],
        tuning["seed"],
        tuning["dynamic_lambda"],
    )
    expected.pop(
        "records_sha256"
    )  # Original input may have been Parquet. Evidence is canonical JSONL.
    if any(tuning.get(k) != v for k, v in expected.items()):
        raise ValueError(
            "Thresholds differ from validation evidence; retune instead of editing hashes"
        )
    return tuning


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
    artifact = load_artifact(artifact_path)
    tuning = load_tuning(tuning_path, artifact_path)
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
            summary, tasks = evaluate(
                rows,
                policy,
                budget,
                tuning["thresholds"][key],
                dynamic_lambda=tuning["dynamic_lambda"],
                seed=seed,
            )
            summaries.append(summary)
            detail.extend({**r, "policy": policy} for r in tasks)
            per_policy[policy] = tasks
        for baseline in (
            "never",
            "always",
            "random",
            "confidence",
            "risk",
            "error_impact",
            "bavar_style",
        ):
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
