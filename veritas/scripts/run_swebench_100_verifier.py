"""Synthetic scheduler exercise over SWE-bench task metadata.

Evaluates the VERITAS verification runtime across 100+ real-world SWE-bench Verified tasks.
Benchmarks:
This script does not execute SWE-bench tasks or inject executable faults. It
only synthesizes action contracts and compares scheduler selections. The
synthetic fault labels are retained solely to report how often selected
actions overlap randomly labeled opportunities; that overlap is not detection.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path
from typing import Any

from veritas.actions.contracts import ActionContract
from veritas.eval.baselines import (
    BavarStyleScheduler,
    ErrorImpactScheduler,
    NeverScheduler,
    RCVOVScheduler,
    AlwaysScheduler,
)
from veritas.risk.impact import ImpactModel


def load_swe_tasks(tasks_path: Path, limit: int = 100) -> list[dict[str, Any]]:
    """Load 100+ tasks from the frozen SWE-bench Verified metadata."""
    tasks = []
    with open(tasks_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            tasks.append(json.loads(line))
            if len(tasks) >= limit:
                break
    return tasks


def synthesize_task_trajectory(task: dict[str, Any], task_idx: int) -> list[ActionContract]:
    """Generate typed ActionContracts representing agent steps for a SWE-bench task."""
    repo = task.get("repo", "unknown/repo")
    inst_id = task.get("instance_id", f"swe_{task_idx:03d}")
    
    # Four metadata-derived action contracts; no repository actions are run.

    c1 = ActionContract(
        tool="file.read",
        operation="read",
        arguments={"path": f"src/{repo.split('/')[-1]}/core.py", "lines": 50},
        intent=f"Inspect issue context for {inst_id}",
        permissions_required=("workspace:read",),
        reversible=True,
        metadata={"task_id": inst_id, "step": 0, "is_critical": False},
    )

    c2 = ActionContract(
        tool="test.run",
        operation="exec",
        arguments={"command": f"pytest tests/test_core.py -k {inst_id[:12]}"},
        intent="Reproduce reported bug",
        permissions_required=("workspace:read", "calc:execute"),
        reversible=True,
        metadata={"task_id": inst_id, "step": 1, "is_critical": False},
    )

    # Step 3: State-mutating code patch (Crucial point of verification)
    c3 = ActionContract(
        tool="file.write",
        operation="patch",
        arguments={
            "path": f"src/{repo.split('/')[-1]}/fix.py",
            "patch_chars": len(task.get("patch", "")),
        },
        intent=f"Apply candidate fix for {inst_id}",
        permissions_required=("workspace:write",),
        reversible=False,  # Mutating state
        metadata={"task_id": inst_id, "step": 2, "is_critical": True},
    )

    c4 = ActionContract(
        tool="git.diff",
        operation="status",
        arguments={"repo": repo},
        intent="Audit workspace diff and commit status",
        permissions_required=("workspace:read",),
        reversible=True,
        metadata={"task_id": inst_id, "step": 3, "is_critical": False},
    )

    return [c1, c2, c3, c4]


def run_benchmark(
    tasks_file: Path,
    limit: int = 100,
    budget: float = 0.24,
    seed: int = 42,
) -> tuple[list[dict], dict]:
    tasks = load_swe_tasks(tasks_file, limit=limit)
    print(f"--> Loaded {len(tasks)} SWE-bench Verified tasks from {tasks_file.name}")

    impact_model = ImpactModel()
    # Assign labels independently of action content and policy features. These
    # are synthetic opportunity labels, not faults injected into execution.
    rng = random.Random(seed)
    action_keys = [
        (task_idx, step_idx)
        for task_idx, task in enumerate(tasks)
        for step_idx, _ in enumerate(synthesize_task_trajectory(task, task_idx))
    ]
    labeled_count = len(action_keys) // 2
    labeled_action_keys = set(rng.sample(action_keys, labeled_count))

    schedulers = [
        NeverScheduler(),
        AlwaysScheduler(),
        ErrorImpactScheduler(threshold=0.25),
        BavarStyleScheduler(threshold=0.25),
        RCVOVScheduler(include_recovery=True),
    ]

    results_summary = []
    
    # Track overall metrics per scheduler
    for sched in schedulers:
        t0 = time.perf_counter()
        total_steps = 0
        actions_verified = 0
        labeled_opportunities_selected = 0
        budget_spent = 0.0

        for idx, task in enumerate(tasks):
            remaining_b = budget
            trajectory = synthesize_task_trajectory(task, idx)

            for step_idx, action in enumerate(trajectory):
                total_steps += 1
                impact = impact_model.score(action).value
                # Keep the scheduler input independent of synthetic labels.
                p_err = 0.1

                record = {
                    "action_id": action.action_id,
                    "action_class": str(action.action_class.value),
                    "impact": impact,
                    "calibrated_error_probability": p_err,
                    "p_error": p_err,
                    "cost": 0.03,
                    "estimated_cost": 0.03,
                    "detection_rate": 0.95,
                    "detection_rate_estimate": 0.95,
                    "false_positive_rate": 0.02,
                    "false_positive_rate_estimate": 0.02,
                    "residual_loss": 0.1,
                    "residual_loss_after_recovery": 0.1,
                    "reversible": action.reversible,
                }

                decision = sched.select(record, remaining_budget=remaining_b, total_budget=budget)
                if decision.selected and remaining_b >= 0.03:
                    actions_verified += 1
                    remaining_b -= 0.03
                    budget_spent += 0.03

                    if (idx, step_idx) in labeled_action_keys:
                        labeled_opportunities_selected += 1

        t1 = time.perf_counter()
        elapsed_s = t1 - t0

        ver_rate = (actions_verified / max(1, total_steps)) * 100.0
        opportunities_total = len(labeled_action_keys)

        res = {
            "policy": sched.name,
            "tasks_evaluated": len(tasks),
            "total_steps": total_steps,
            "actions_verified": actions_verified,
            "verification_rate_percent": round(ver_rate, 1),
            "budget_spent": round(budget_spent, 2),
            "simulation_only": True,
            "synthetic_opportunities_selected": labeled_opportunities_selected,
            "synthetic_opportunities_total": opportunities_total,
            "fault_detection_metrics": None,
            "recovery_metrics": None,
            "state_integrity_metrics": None,
            "runtime_seconds": round(elapsed_s, 2),
        }
        results_summary.append(res)
        print(f"Policy: {sched.name:20s} | Selected: {actions_verified:3d}/{total_steps} ({ver_rate:4.1f}%) | Synthetic labeled overlap: {labeled_opportunities_selected}/{opportunities_total} | Cost: ${budget_spent:.2f}")

    return results_summary, {
        "tasks_count": len(tasks),
        "budget": budget,
        "seed": seed,
        "evaluation_type": "synthetic_scheduler_simulation",
        "executes_swebench": False,
        "injects_executable_faults": False,
        "detection_metrics_available": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic scheduler simulation over SWE-bench task metadata")
    parser.add_argument("--tasks", type=Path, default=Path("artifacts/swe-verified-map.tasks.jsonl"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--budget", type=float, default=0.24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-json", type=Path, default=Path("research/results/swe_100_eval.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("research/results/swe_100_eval.csv"))
    args = parser.parse_args()

    # Fallback to parent path if run from veritas directory
    tasks_path = args.tasks
    if not tasks_path.exists():
        tasks_path = Path("../artifacts/swe-verified-map.tasks.jsonl")
    if not tasks_path.exists():
        tasks_path = Path("F:/Abidur 2110001/VERITAS/artifacts/swe-verified-map.tasks.jsonl")

    results, meta = run_benchmark(tasks_path, limit=args.limit, budget=args.budget, seed=args.seed)

    # Save JSON
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2)
    print(f"\n--> Saved JSON results to {args.output_json}")

    # Save CSV
    keys = list(results[0].keys())
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"--> Saved CSV results to {args.output_csv}")


if __name__ == "__main__":
    main()
