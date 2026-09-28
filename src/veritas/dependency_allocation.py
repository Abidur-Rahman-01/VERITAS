"""Sequential, propensity-recording allocation for dependency experiments."""

import json
from pathlib import Path

import numpy as np

from .dependency_pilot import ARMS
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl


def create_allocation(candidates_file, output, rollout_budget, rollout_cost=1.0,
                      exploration=0.2, graph_weight=0.5, seed=42):
    output = Path(output)
    if output.exists():
        raise ValueError("Allocation output already exists; choose a new directory")
    if rollout_budget <= 0 or rollout_cost <= 0:
        raise ValueError("Rollout budget and cost must be positive")
    if not 0 < exploration <= 1 or graph_weight < 0:
        raise ValueError("Exploration must be in (0, 1] and graph_weight nonnegative")
    candidates = json.loads(Path(candidates_file).read_text())
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Candidate file must contain a nonempty JSON list")
    ids = [row.get("candidate_id") for row in candidates]
    if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Candidates require unique nonempty candidate_id values")
    if any(not isinstance(row.get("graph_edge"), bool) for row in candidates):
        raise ValueError("Each candidate must declare graph_edge as a boolean")
    output.mkdir(parents=True)
    plan = {
        "version": 1,
        "candidate_file_sha256": file_hash(Path(candidates_file)),
        "candidates": candidates,
        "rollout_budget": float(rollout_budget),
        "rollout_cost": float(rollout_cost),
        "exploration": float(exploration),
        "graph_weight": float(graph_weight),
        "seed": int(seed),
        "arms": list(ARMS),
        "status": "collecting",
        "scope_note": "adaptive discovery only; freeze independent confirmation before outcome inspection",
    }
    plan["allocation_id"] = digest(plan)
    write_json(output / "allocation.json", plan)
    write_jsonl(output / "observations.jsonl", [])
    return plan


def _read_plan(output):
    output = Path(output)
    plan = json.loads((output / "allocation.json").read_text())
    expected = dict(plan)
    identity = expected.pop("allocation_id")
    if digest(expected) != identity:
        raise ValueError("Allocation plan changed")
    return plan


def _posterior(observations, candidate_id, arm):
    rows = [row for row in observations
            if row["candidate_id"] == candidate_id and row["arm"] == arm]
    successes = sum(row["success"] for row in rows)
    failures = len(rows) - successes
    return 1 + successes, 1 + failures


def _voi(alpha, beta):
    """Expected one-step improvement in the best arm's posterior mean."""
    means = np.asarray([a / (a + b) for a, b in zip(alpha, beta)])
    current = float(means.max())
    scores = []
    for index, (a, b) in enumerate(zip(alpha, beta)):
        p = a / (a + b)
        success = means.copy()
        failure = means.copy()
        success[index] = (a + 1) / (a + b + 1)
        failure[index] = a / (a + b + 1)
        scores.append(max(0.0, p * max(success) + (1 - p) * max(failure) - current))
    return scores


def select_next(output):
    output = Path(output)
    plan = _read_plan(output)
    observations = list(read_jsonl(output / "observations.jsonl"))
    pending_path = output / "pending-selection.json"
    if pending_path.exists():
        return json.loads(pending_path.read_text())
    spent = len(observations) * plan["rollout_cost"]
    if spent + plan["rollout_cost"] > plan["rollout_budget"] + 1e-12:
        return {"status": "budget_exhausted", "spent": spent, "budget": plan["rollout_budget"]}
    candidate_arms = [(row, arm) for row in plan["candidates"] for arm in ARMS]
    raw = []
    for index, (candidate, arm) in enumerate(candidate_arms):
        arm_index = ARMS.index(arm)
        arm_alphas = [_posterior(observations, candidate["candidate_id"], value)[0] for value in ARMS]
        arm_betas = [_posterior(observations, candidate["candidate_id"], value)[1] for value in ARMS]
        value = _voi(arm_alphas, arm_betas)[arm_index]
        weight = 1 + plan["graph_weight"] if candidate["graph_edge"] else 1.0
        raw.append(value * weight / plan["rollout_cost"])
    scores = np.asarray(raw, dtype=float)
    # Softmax acquisition plus a uniform floor guarantees exploration off graph and on graph.
    shifted = scores - scores.max()
    soft = np.exp(np.clip(shifted, -60, 0))
    adaptive = soft / soft.sum()
    uniform = np.full(len(candidate_arms), 1 / len(candidate_arms))
    probabilities = plan["exploration"] * uniform + (1 - plan["exploration"]) * adaptive
    rng = np.random.default_rng(plan["seed"] + len(observations))
    selected = int(rng.choice(len(candidate_arms), p=probabilities))
    candidate, arm = candidate_arms[selected]
    allocation = {
        "status": "selected",
        "sequence": len(observations),
        "candidate_id": candidate["candidate_id"],
        "arm": arm,
        "selection_probability": float(probabilities[selected]),
        "uniform_probability": float(uniform[selected]),
        "graph_edge": candidate["graph_edge"],
        "acquisition_score": float(scores[selected]),
        "spent_before": spent,
        "budget_remaining_after_reservation": plan["rollout_budget"] - spent - plan["rollout_cost"],
        "candidate_probabilities": [
            {"candidate_id": row["candidate_id"], "arm": arm_name,
             "probability": float(probabilities[i]), "uniform_probability": float(uniform[i])}
            for i, (row, arm_name) in enumerate(candidate_arms)
        ],
    }
    write_json(pending_path, allocation)
    return allocation


def record_result(output, candidate_id, arm, success, selection_probability):
    output = Path(output)
    plan = _read_plan(output)
    if candidate_id not in {row["candidate_id"] for row in plan["candidates"]} or arm not in ARMS:
        raise ValueError("Observation is outside the frozen candidate-arm set")
    if success not in (0, 1, False, True):
        raise ValueError("success must be binary")
    if not 0 < selection_probability <= 1:
        raise ValueError("selection_probability must be in (0, 1]")
    observations = list(read_jsonl(output / "observations.jsonl"))
    pending_path = output / "pending-selection.json"
    if not pending_path.exists():
        raise ValueError("Select a rollout before recording its outcome")
    pending = json.loads(pending_path.read_text())
    if (pending["candidate_id"], pending["arm"], pending["selection_probability"]) != (
        candidate_id, arm, float(selection_probability)
    ):
        raise ValueError("Recorded outcome does not match the selected candidate, arm, and propensity")
    if len(observations) * plan["rollout_cost"] + plan["rollout_cost"] > plan["rollout_budget"] + 1e-12:
        raise ValueError("Frozen rollout budget is exhausted")
    event = {
        "sequence": len(observations),
        "candidate_id": candidate_id,
        "arm": arm,
        "success": int(success),
        "selection_probability": float(selection_probability),
        "uniform_probability": 1 / (len(plan["candidates"]) * len(ARMS)),
        "cost": plan["rollout_cost"],
    }
    observations.append(event)
    write_jsonl(output / "observations.jsonl", observations)
    pending_path.unlink()
    return event


def allocation_report(output):
    output = Path(output)
    plan = _read_plan(output)
    rows = list(read_jsonl(output / "observations.jsonl"))
    report = {
        "allocation_id": plan["allocation_id"],
        "budget": plan["rollout_budget"],
        "spent": sum(row["cost"] for row in rows),
        "rollouts": len(rows),
        "remaining": max(0.0, plan["rollout_budget"] - sum(row["cost"] for row in rows)),
        "candidates": len(plan["candidates"]),
        "recorded_selection_probabilities": all(0 < row["selection_probability"] <= 1 for row in rows),
        "nonzero_off_graph_exploration": plan["exploration"] > 0,
        "uniform_baseline_probability": 1 / (len(plan["candidates"]) * len(ARMS)),
        "adaptive_estimates": "pending; use recorded propensities or independent confirmation",
        "evidence_status": "allocation_ledger_only",
    }
    write_json(output / "allocation-report.json", report)
    return report
