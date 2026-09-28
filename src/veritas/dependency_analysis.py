"""Cluster-aware analysis for completed dependency pilots."""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .dependency_pilot import ARMS, _run_result_path, read_pilot
from .io import write_json


def _bootstrap(values, seed, repetitions=4000):
    """Return percentile intervals by resampling independent task/repository clusters."""
    matrix = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(matrix), size=(repetitions, len(matrix)))
    return matrix[indexes].mean(axis=1)


def analyze_pilot(output, seed=42):
    output = Path(output)
    plan = read_pilot(output)
    results = {}
    for job in plan["jobs"]:
        path = _run_result_path(output, job)
        result = json.loads(path.read_text()) if path.exists() else None
        if result is None or result.get("status") != "done" or result.get("success") is None:
            continue
        key = (job["task_id"], job["group_id"], job["source"], job["arm"])
        results.setdefault(key, []).append(float(result["success"]))

    execution_modes = {plan.get("opportunity_policy_execution", "unknown")}
    active = execution_modes == {"active_optional_check_intervention"}
    assignments = defaultdict(dict)
    for (task_id, group_id, source, arm), outcomes in results.items():
        assignments[(task_id, group_id, source)][arm] = float(np.mean(outcomes))
    groups = defaultdict(list)
    for (task_id, group_id, source), arms in assignments.items():
        if set(arms) == set(ARMS):
            groups[source].append((group_id, arms))

    meaningful = plan["protocol"].get("meaningful_effect")
    if not isinstance(meaningful, (int, float)) or meaningful <= 0:
        raise ValueError("Frozen protocol must define a positive meaningful_effect")
    reports = []
    expected_by_source = defaultdict(list)
    for task in plan["selected_tasks"]:
        expected_by_source[task["source"]].append((task["task_id"], task["group_id"]))
    for source, expected_tasks in sorted(expected_by_source.items()):
        blocks = groups.get(source, [])
        # Repetitions are averaged within task before bootstrap; group IDs are clusters.
        by_group = defaultdict(lambda: defaultdict(list))
        for group_id, arms in blocks:
            for arm, outcome in arms.items():
                by_group[group_id][arm].append(outcome)
        clusters = [
            [float(np.mean(by_group[group][arm])) for arm in ARMS]
            for group in sorted(by_group)
            if set(by_group[group]) == set(ARMS)
        ]
        repetitions = sum(
            job["task_id"] == expected_tasks[0][0] and job["arm"] == ARMS[0]
            for job in plan["jobs"]
        )
        task_complete = all(
            all(len(results.get((task_id, group_id, source, arm), [])) == repetitions for arm in ARMS)
            for task_id, group_id in expected_tasks
        )
        if not clusters or not task_complete:
            reports.append({
                "source": source,
                "clusters": len(clusters),
                "expected_tasks": len(expected_tasks),
                "classification": "incomplete_pilot",
                "interaction": None,
                "interaction_ci95": None,
            })
            continue
        matrix = np.asarray(clusters)
        interaction = matrix[:, 3] - matrix[:, 1] - matrix[:, 2] + matrix[:, 0]
        interaction_draws = _bootstrap(interaction[:, None], seed + 1).reshape(-1)
        values = matrix.mean(axis=0)
        interval = np.quantile(interaction_draws, [0.025, 0.975]).tolist()
        ci_width = interval[1] - interval[0]
        if not active:
            classification = "not_estimable_shadow_only"
        elif interval[0] > 0 and values[3] - values[1] - values[2] + values[0] >= meaningful:
            classification = "synergy"
        elif interval[1] < 0:
            classification = "harmful_interaction"
        elif ci_width <= meaningful:
            classification = "no_decision_relevant_interaction_detected"
        else:
            classification = "inconclusive"
        reports.append({
            "source": source,
            "clusters": len(clusters),
            "complete_clusters": len(clusters),
            "arm_values": dict(zip(ARMS, values.tolist())),
            "interaction": float(interaction.mean()),
            "interaction_ci95": interval,
            "meaningful_effect": float(meaningful),
            "interval_width": float(ci_width),
            "classification": classification,
            "next_stage_clusters_for_80pct_power": _power_draw_summary(interaction, meaningful, seed + 2),
        })
    analysis = {
        "pilot_id": plan["pilot_id"],
        "estimand": "task-success probability; interaction = V11 - V10 - V01 + V00",
        "cluster_unit": "group_id",
        "bootstrap_repetitions": 4000,
        "policy_execution": plan.get("opportunity_policy_execution"),
        "causal_estimates_enabled": active,
        "status": "estimated" if active and reports else "shadow_only_or_insufficient_complete_clusters",
        "results": reports,
        "predictive_validation": {
            "status": "pending",
            "reason": "pilot records do not yet freeze pre-decision features or support an independent held-out prediction comparison",
        },
    }
    write_json(output / "dependency-analysis.json", analysis)
    return analysis


def _power_draw_summary(cluster_interactions, meaningful, seed):
    """Approximate required cluster count, propagating pilot variance uncertainty."""
    rng = np.random.default_rng(seed)
    values = np.asarray(cluster_interactions, dtype=float)
    if len(values) < 2:
        return {"median": None, "interval90": None, "status": "at_least_two_clusters_required"}
    sigma = np.std(values, ddof=1)
    if sigma == 0:
        return {"median": None, "interval90": None, "status": "zero_pilot_variance_uninformative"}
    estimates = []
    for _ in range(1000):
        sample = rng.choice(values, size=len(values), replace=True)
        sd = np.std(sample, ddof=1)
        estimates.append(max(2, int(np.ceil(((1.96 + 0.84) * sd / meaningful) ** 2))))
    return {
        "median": int(np.median(estimates)),
        "interval90": np.quantile(estimates, [0.05, 0.95]).astype(int).tolist(),
        "status": "approximate_normal_planning_only",
    }
