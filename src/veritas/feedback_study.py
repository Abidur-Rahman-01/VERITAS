"""Immutable cohort planning and paired analysis for feedback-selection experiments."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .data import load_tasks
from .feedback_policy import ARMS
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl

PLAN_FILES = ("tasks.jsonl", "blocks.jsonl", "branches.jsonl", "protocol.json")


def create_plan(tasks_dir, output, *, source="swe_rebench", task_limit=None, seed=42,
                confirmation_fraction=0.2):
    """Freeze a repository-disjoint task cohort and the five paired policy branches."""
    if not 0 < confirmation_fraction < 1:
        raise ValueError("confirmation_fraction must be strictly between 0 and 1")
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Feedback study output must be empty; plans are immutable")
    prepared_manifest = Path(tasks_dir) / "manifest.json"
    if not prepared_manifest.is_file():
        raise ValueError(f"Prepared dataset manifest not found: {prepared_manifest}")
    all_tasks = [task for task, _ in load_tasks(tasks_dir, source=source)]
    if not all_tasks:
        raise ValueError(f"No tasks found for source={source!r}")
    if any(task.kind != "swe" or not task.repo or not task.base_commit for task in all_tasks):
        raise ValueError("Feedback study requires SWE tasks with repository and pinned base commit")

    # Limit is selected deterministically across repositories, not by source-file order.
    all_tasks.sort(key=lambda task: digest([seed, task.repo, task.task_id]))
    if task_limit is not None:
        if task_limit < 1:
            raise ValueError("task_limit must be positive")
        all_tasks = all_tasks[:task_limit]
    repos = sorted({task.repo for task in all_tasks})
    if len(repos) < 2:
        raise ValueError("At least two repositories are needed for repository-disjoint development/confirmation")
    confirmation_count = max(1, round(len(repos) * confirmation_fraction))
    confirmation = set(sorted(repos, key=lambda repo: digest([seed, "confirmation", repo]))[:confirmation_count])
    selected = sorted(all_tasks, key=lambda task: task.task_id)

    blocks, branches = [], []
    for task in selected:
        partition = "confirmation" if task.repo in confirmation else "development"
        block_id = digest([seed, source, task.task_id, "actor-default", 0])[:24]
        blocks.append({"block_id": block_id, "task_id": task.task_id,
            "repository": task.repo, "partition": partition,
            "draft_seed": 0, "common_parent_required": True})
        for arm in ARMS:
            branches.append({"branch_id": digest([block_id, arm])[:24],
                "block_id": block_id, "task_id": task.task_id, "repository": task.repo,
                "partition": partition, "arm": arm, "status": "planned"})

    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "tasks.jsonl", (task.model_dump(mode="json") for task in selected))
    write_jsonl(root / "blocks.jsonl", blocks)
    write_jsonl(root / "branches.jsonl", branches)
    protocol = {
        "schema_version": 1, "study": "veritas-feedback-selection",
        "dataset_source": source,
        "dataset_manifest_sha256": file_hash(prepared_manifest),
        "prepared_tasks_sha256": file_hash(Path(tasks_dir) / "tasks.jsonl"),
        "prepared_splits_sha256": file_hash(Path(tasks_dir) / "splits.json"),
        "seed": seed, "task_count": len(selected), "repository_count": len(repos),
        "development_repositories": sorted(set(repos) - confirmation),
        "confirmation_repositories": sorted(confirmation),
        "arms": list(ARMS), "primary_comparison": ["adaptive", "fixed_actionable"],
        "design": "paired branches from a single independently graded common parent patch",
        "note": "Planning only. Branch execution must freeze one parent patch per block before treatment branches are run.",
    }
    write_json(root / "protocol.json", protocol)
    plan = {"files": {name: file_hash(root / name) for name in PLAN_FILES}}
    plan["plan_hash"] = digest(plan)
    write_json(root / "plan.json", plan)
    return {"plan_hash": plan["plan_hash"], "tasks": len(selected),
            "repositories": len(repos), "branches": len(branches),
            "development_repositories": len(repos) - len(confirmation),
            "confirmation_repositories": len(confirmation), "output": str(root)}


def verify_plan(directory):
    root = Path(directory)
    plan = json.loads((root / "plan.json").read_text())
    if digest({"files": plan.get("files")}) != plan.get("plan_hash"):
        raise ValueError("Feedback plan hash mismatch")
    for name, expected in plan["files"].items():
        if file_hash(root / name) != expected:
            raise ValueError(f"Feedback plan artifact changed: {name}")
    tasks = list(read_jsonl(root / "tasks.jsonl"))
    blocks = list(read_jsonl(root / "blocks.jsonl"))
    branches = list(read_jsonl(root / "branches.jsonl"))
    if len(branches) != len(blocks) * len(ARMS):
        raise ValueError("Every block must have exactly one branch per frozen arm")
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs in plan")
    for block in blocks:
        arms = [branch["arm"] for branch in branches if branch["block_id"] == block["block_id"]]
        if sorted(arms) != sorted(ARMS):
            raise ValueError(f"Incomplete or duplicate arms for block {block['block_id']}")
    protocol = json.loads((root / "protocol.json").read_text())
    if set(protocol["development_repositories"]) & set(protocol["confirmation_repositories"]):
        raise ValueError("Development and confirmation repositories overlap")
    return {"plan_hash": plan["plan_hash"], "integrity": "valid", "tasks": len(tasks),
            "blocks": len(blocks), "branches": len(branches)}


def analyze_results(directory, results_path=None):
    """Summarize branch outcomes; unknown/infrastructure statuses stay missing."""
    root = Path(directory)
    verify_plan(root)
    results_path = Path(results_path) if results_path else root / "results.jsonl"
    if not results_path.is_file():
        raise ValueError(f"Branch outcome ledger not found: {results_path}")
    results = list(read_jsonl(results_path))
    by_block = defaultdict(dict)
    planned = {(row["block_id"], row["arm"]): row for row in read_jsonl(root / "branches.jsonl")}
    for row in results:
        if row.get("arm") not in ARMS:
            raise ValueError("Unknown feedback arm in results")
        assignment = planned.get((row.get("block_id"), row["arm"]))
        if assignment is None or row.get("branch_id") not in (None, assignment["branch_id"]):
            raise ValueError("Result does not match a frozen branch assignment")
        if row["arm"] in by_block[row["block_id"]]:
            raise ValueError("Duplicate block/arm outcome")
        by_block[row["block_id"]][row["arm"]] = row
    paired = []
    for block in read_jsonl(root / "blocks.jsonl"):
        arms = by_block.get(block["block_id"], {})
        if not {"adaptive", "fixed_actionable"} <= set(arms):
            continue
        adaptive, fixed = arms["adaptive"], arms["fixed_actionable"]
        if adaptive.get("resolved") not in (True, False) or fixed.get("resolved") not in (True, False):
            continue
        parent_correct = block.get("parent_resolved")
        if parent_correct is None:
            # Parent label is recorded with each arm result by the runner.
            parent_correct = adaptive.get("parent_resolved")
        paired.append({"block_id": block["block_id"], "repository": block["repository"],
            "partition": block["partition"], "parent_resolved": parent_correct,
            "adaptive_resolved": adaptive["resolved"], "fixed_actionable_resolved": fixed["resolved"],
            "adaptive_credits": adaptive.get("total_credits"),
            "fixed_actionable_credits": fixed.get("total_credits")})
    incorrect = [row for row in paired if row["parent_resolved"] is False]
    correct = [row for row in paired if row["parent_resolved"] is True]
    adaptive_costs = [row["adaptive_credits"] for row in paired if row["adaptive_credits"] is not None]
    fixed_costs = [row["fixed_actionable_credits"] for row in paired
                   if row["fixed_actionable_credits"] is not None]
    return {"paired_blocks": len(paired), "incorrect_parent_blocks": len(incorrect),
        "all_block_adaptive_resolution": _mean([r["adaptive_resolved"] for r in paired]),
        "all_block_fixed_resolution": _mean([r["fixed_actionable_resolved"] for r in paired]),
        "recovery_adaptive": _mean([r["adaptive_resolved"] for r in incorrect]),
        "recovery_fixed_actionable": _mean([r["fixed_actionable_resolved"] for r in incorrect]),
        "regression_adaptive": _mean([not r["adaptive_resolved"] for r in correct]),
        "regression_fixed_actionable": _mean([not r["fixed_actionable_resolved"] for r in correct]),
        "paired_recovery_difference": _mean([
            int(r["adaptive_resolved"]) - int(r["fixed_actionable_resolved"]) for r in incorrect
        ]),
        "mean_adaptive_credits": _mean(adaptive_costs),
        "mean_fixed_actionable_credits": _mean(fixed_costs),
        "analysis_status": "descriptive_unclustered",
        "note": "Use repository-clustered paired intervals for confirmatory inference."}


def _mean(values):
    return sum(float(v) for v in values) / len(values) if values else None
