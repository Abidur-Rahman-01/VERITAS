"""Regrade saved feedback-study workspaces without rerunning the actor."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veritas.feedback_runner import evaluate_task
from veritas.feedback_study import analyze_results, verify_plan
from veritas.io import file_hash, read_jsonl, write_json, write_jsonl
from veritas.schema import Task


def regrade_study(study_dir: str | Path, *, suffix: str = "regraded") -> dict:
    study = Path(study_dir).resolve()
    verify_plan(study)
    tasks = {
        row["task_id"]: Task.model_validate(row)
        for row in read_jsonl(study / "tasks.jsonl")
    }
    blocks = list(read_jsonl(study / "blocks.jsonl"))
    results_path = study / "results.jsonl"
    results = list(read_jsonl(results_path))
    if not results:
        raise ValueError("Study has no saved branch results to regrade")

    ledger = study / f"{suffix}_results.jsonl"
    parents = study / f"{suffix}_parent_grades.jsonl"
    analysis_path = study / f"{suffix}_analysis.json"
    manifest_path = study / f"{suffix}_manifest.json"
    outputs = (ledger, parents, analysis_path, manifest_path)
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Regrade outputs already exist; choose another --suffix:\n" + "\n".join(existing)
        )

    # Validate every workspace first so an incomplete run cannot produce a
    # partial regrade ledger.
    missing = []
    for block in blocks:
        block_dir = study / "blocks" / block["block_id"]
        for path in (block_dir / "parent_workspace", block_dir / "parent_baseline"):
            if not path.is_dir():
                missing.append(str(path))
    for row in results:
        branch_dir = study / "blocks" / row["block_id"] / row["arm"]
        for path in (branch_dir / "workspace", branch_dir / "baseline"):
            if not path.is_dir():
                missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            "Saved workspace or baseline missing; cannot regrade without actor reruns:\n"
            + "\n".join(missing[:20])
        )

    parent_rows = []
    parent_by_block = {}
    for block in blocks:
        task = tasks[block["task_id"]]
        block_dir = study / "blocks" / block["block_id"]
        grade = evaluate_task(
            task, block_dir / "parent_workspace", block_dir / "parent_baseline"
        )
        parent_by_block[block["block_id"]] = grade
        parent_rows.append({
            "block_id": block["block_id"],
            "task_id": block["task_id"],
            "resolved": grade["resolved"],
            "grader_status": grade["status"],
            "grader_seconds": grade["seconds"],
            "output": grade["log"],
        })

    regraded_rows = []
    for row in results:
        task = tasks[row["task_id"]]
        branch_dir = study / "blocks" / row["block_id"] / row["arm"]
        grade = evaluate_task(task, branch_dir / "workspace", branch_dir / "baseline")
        result = dict(row)
        result["regrade_previous_status"] = row.get("grader_status")
        result["resolved"] = grade["resolved"]
        result["grader_status"] = (
            "invalid_patch" if row.get("patch_empty") else grade["status"]
        )
        result["grader_seconds"] = grade["seconds"]
        result["parent_resolved"] = parent_by_block[row["block_id"]]["resolved"]
        result["regrade_output"] = grade["log"][:4000]
        regraded_rows.append(result)

    write_jsonl(ledger, regraded_rows)
    write_jsonl(parents, parent_rows)
    analysis = analyze_results(study, ledger)
    write_json(analysis_path, analysis)
    write_json(manifest_path, {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study": str(study),
        "original_results_sha256": file_hash(results_path),
        "evaluator": "veritas.feedback_runner.evaluate_task",
        "platform": platform.platform(),
        "actor_rerun": False,
        "branch_rows_regraded": len(regraded_rows),
        "parent_rows_regraded": len(parent_rows),
        "outputs": {
            "results": ledger.name,
            "parent_grades": parents.name,
            "analysis": analysis_path.name,
        },
    })
    return {
        "study": str(study),
        "branch_rows_regraded": len(regraded_rows),
        "parent_rows_regraded": len(parent_rows),
        "analysis": str(analysis_path),
        "manifest": str(manifest_path),
        "arm_summary": analysis["arms"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Regrade saved feedback-study workspaces without model calls"
    )
    parser.add_argument("--study", required=True, help="Completed study directory")
    parser.add_argument("--suffix", default="regraded", help="Output filename prefix")
    args = parser.parse_args()
    print(json.dumps(regrade_study(args.study, suffix=args.suffix), indent=2))


if __name__ == "__main__":
    main()
