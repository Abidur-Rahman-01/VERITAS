"""Leakage-aware benefit models for completed active dependency pilots."""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from .data import load_tasks
from .dependency_pilot import ARMS, _run_result_path, read_pilot
from .io import write_json


def _features(task, selected):
    """Features fixed before treatment: public task text metadata and reviewed code identities."""
    words = task.prompt.split()
    return {
        "source": task.source,
        "kind": task.kind,
        "target_path": selected["target_identity"].split("::", 1)[0],
        "caller_path": selected["caller_identity"].split("::", 1)[0],
        "prompt_words": float(len(words)),
        "prompt_chars": float(len(task.prompt)),
        "prompt_lines": float(task.prompt.count("\n") + 1),
    }


def _design(features, arm, structured):
    a, b = int(arm[0]), int(arm[1])
    row = dict(features)
    row.update({"policy_A": float(a), "policy_B": float(b)})
    for feature in ("prompt_words", "prompt_chars", "prompt_lines"):
        row[f"policy_A_x_{feature}"] = a * features[feature]
        row[f"policy_B_x_{feature}"] = b * features[feature]
    if structured:
        row["policy_A_x_B"] = float(a * b)
        for feature in ("prompt_words", "prompt_chars", "prompt_lines"):
            row[f"policy_A_x_B_x_{feature}"] = a * b * features[feature]
    return row


def _cluster_interval(values, seed, repeats=2000):
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    draws = [float(rng.choice(values, len(values), replace=True).mean()) for _ in range(repeats)]
    return np.quantile(draws, [0.025, 0.975]).tolist()


def fit_benefit_models(output, seed=42, validation_fraction=0.25, regularization=1.0):
    """Fit baseline and interaction logistic models; refuse shadow or incomplete outcomes."""
    if not 0 < validation_fraction < 0.5:
        raise ValueError("validation_fraction must be between 0 and 0.5")
    if regularization <= 0:
        raise ValueError("regularization must be positive")
    output = Path(output)
    plan = read_pilot(output)
    artifact = {
        "pilot_id": plan["pilot_id"],
        "status": "not_fit",
        "feature_policy": "public prompt metadata and reviewed target/caller identity, fixed before treatment",
        "models": None,
    }
    if plan.get("opportunity_policy_execution") != "active_optional_check_intervention":
        artifact["reason"] = "pilot has shadow trigger observation only; no treatment effects are identified"
        write_json(output / "dependency-models.json", artifact)
        return artifact

    selected = {row["task_id"]: row for row in plan["selected_tasks"]}
    tasks = {task.task_id: task for task, _ in load_tasks(output / "tasks")}
    observations = []
    counts = defaultdict(int)
    for job in plan["jobs"]:
        path = _run_result_path(output, job)
        result = json.loads(path.read_text()) if path.exists() else None
        if result is None or result.get("status") != "done" or result.get("success") is None:
            artifact["reason"] = "complete active four-arm results are required before fitting"
            write_json(output / "dependency-models.json", artifact)
            return artifact
        counts[(job["task_id"], job["arm"])] += 1
        observations.append((job, float(result["success"])))
    expected = defaultdict(int)
    for job in plan["jobs"]:
        expected[(job["task_id"], job["arm"])] += 1
    if any(counts[key] != count for key, count in expected.items()):
        artifact["reason"] = "repetition counts differ from frozen schedule"
        write_json(output / "dependency-models.json", artifact)
        return artifact

    groups = sorted({job["group_id"] for job, _ in observations})
    if len(groups) < 4:
        artifact["reason"] = "at least four independent groups are required for grouped training and validation"
        artifact["groups"] = len(groups)
        write_json(output / "dependency-models.json", artifact)
        return artifact
    rng = np.random.default_rng(seed)
    shuffled = np.asarray(groups, dtype=object)
    rng.shuffle(shuffled)
    validation_count = max(1, min(len(groups) - 2, int(round(len(groups) * validation_fraction))))
    validation_groups = set(shuffled[:validation_count].tolist())
    train_groups = set(groups) - validation_groups

    def rows_for(group_set):
        rows, labels, row_groups = [], [], []
        for job, outcome in observations:
            if job["group_id"] not in group_set:
                continue
            base = _features(tasks[job["task_id"]], selected[job["task_id"]])
            rows.append(base)
            labels.append(outcome)
            row_groups.append(job["group_id"])
        return rows, np.asarray(labels, dtype=int), row_groups

    train_raw, y_train, _ = rows_for(train_groups)
    valid_raw, y_valid, valid_group_rows = rows_for(validation_groups)
    train_jobs = [job for job, _ in observations if job["group_id"] in train_groups]
    valid_jobs = [job for job, _ in observations if job["group_id"] in validation_groups]
    reports = {}
    model_payload = {}
    for name, structured in (("individual_effects", False), ("regularized_interaction", True)):
        train_dicts = [_design(row, job["arm"], structured) for row, job in zip(train_raw, train_jobs)]
        valid_dicts = [_design(row, job["arm"], structured) for row, job in zip(valid_raw, valid_jobs)]
        vectorizer = DictVectorizer(sparse=True)
        x_train = vectorizer.fit_transform(train_dicts)
        x_valid = vectorizer.transform(valid_dicts)
        model = LogisticRegression(C=regularization, max_iter=2000, solver="liblinear", random_state=seed)
        model.fit(x_train, y_train)
        probability = model.predict_proba(x_valid)[:, 1]
        group_scores = defaultdict(lambda: {"brier": [], "log_loss": []})
        for group, label, prediction in zip(valid_group_rows, y_valid, probability):
            group_scores[group]["brier"].append(float((prediction - label) ** 2))
            p = min(1 - 1e-12, max(1e-12, float(prediction)))
            group_scores[group]["log_loss"].append(float(-label * np.log(p) - (1 - label) * np.log(1 - p)))
        cluster_brier = [float(np.mean(score["brier"])) for score in group_scores.values()]
        cluster_log_loss = [float(np.mean(score["log_loss"])) for score in group_scores.values()]
        reports[name] = {
            "validation_groups": len(group_scores),
            "brier": float(np.mean(cluster_brier)),
            "brier_ci95": _cluster_interval(cluster_brier, seed + 11),
            "log_loss": float(np.mean(cluster_log_loss)),
            "log_loss_ci95": _cluster_interval(cluster_log_loss, seed + 12),
            "probability_scale": True,
        }
        validation_tasks = {}
        for job in valid_jobs:
            validation_tasks[(job["task_id"], job["group_id"])] = job
        contrast_by_group = defaultdict(list)
        for (task_id, group_id), job in validation_tasks.items():
            base = _features(tasks[task_id], selected[task_id])
            counterfactuals = vectorizer.transform(
                [_design(base, arm, structured) for arm in ARMS]
            )
            probs = model.predict_proba(counterfactuals)[:, 1]
            contrast_by_group[group_id].append(float(probs[3] - probs[1] - probs[2] + probs[0]))
        group_contrasts = [float(np.mean(v)) for v in contrast_by_group.values()]
        reports[name]["mean_probability_interaction"] = float(np.mean(group_contrasts))
        reports[name]["probability_interaction_ci95"] = _cluster_interval(group_contrasts, seed + 13)
        model_payload[name] = {
            "feature_names": vectorizer.get_feature_names_out().tolist(),
            "coefficients": model.coef_[0].astype(float).tolist(),
            "intercept": float(model.intercept_[0]),
            "regularization_C": regularization,
        }

    artifact.update({
        "status": "fit",
        "reason": None,
        "seed": seed,
        "cluster_unit": "group_id",
        "training_groups": sorted(train_groups),
        "validation_groups": sorted(validation_groups),
        "estimand_scale": "predicted task-success probability",
        "models": reports,
        "fit_artifacts": model_payload,
        "learning_curves": "pending: fixed-budget refits require sequential continuation-budget outcomes",
        "confirmation_assessment": "pending independent confirmation partition",
    })
    write_json(output / "dependency-models.json", artifact)
    return artifact
