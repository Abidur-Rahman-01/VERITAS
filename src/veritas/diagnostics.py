"""Read-only audit of collection completeness and calibration evidence."""

import json
from collections import Counter
from pathlib import Path

import numpy as np

from .calibration import calibration_metrics
from .io import read_jsonl


def diagnose_run(directory, artifact_path=None):
    directory = Path(directory)
    summaries_path = directory / "summaries.jsonl"
    summaries = list(read_jsonl(summaries_path)) if summaries_path.exists() else []
    run = json.loads((directory / "run.json").read_text())
    failure_path = directory / "failure.json"
    failure = json.loads(failure_path.read_text()) if failure_path.exists() else None
    # Read SQLite directly; opening EventStore would create a missing database.
    import sqlite3

    database = directory / "events.sqlite"
    if not database.is_file():
        raise ValueError("Run event database missing")
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM events ORDER BY rowid")]
    semantic = [
        r for r in rows if r.get("label_scope") == "semantic" and r.get("error_label") is not None
    ]
    operational = [
        r
        for r in rows
        if r.get("label_scope") == "operational" and r.get("error_label") is not None
    ]
    probability = [
        r
        for r in semantic
        if r.get("split") == "calib"
        and r.get("calibration_role") == "probability"
        and r.get("raw_logit") is not None
        and not r.get("blocked")
    ]
    logits = [r["raw_logit"] for r in probability]
    labels = [r["error_label"] for r in probability]
    warnings = []
    if failure:
        warnings.append(
            "Run interrupted; completed tasks are a partial, potentially biased sample."
        )
    if len(set(logits)) < 2 and logits:
        warnings.append(
            "Constant critic scores cannot rank errors; ECE can be zero by matching prevalence."
        )
    coverage = Counter(
        (r["action"]["action_class"], r["error_label"])
        for r in semantic
        if r.get("action") and not r.get("blocked")
    )
    result = {
        "requested_limit": run.get("limit"),
        "completed_tasks": len(summaries),
        "successes": sum(r["task_success"] is True for r in summaries),
        "task_failures": sum(r["task_success"] is False for r in summaries),
        "ungraded_tasks": sum(r["task_success"] is None for r in summaries),
        "failure": failure,
        "events": len(rows),
        "semantic_labels": dict(Counter(str(r["error_label"]) for r in semantic)),
        "operational_labels_not_semantic": dict(
            Counter(str(r["error_label"]) for r in operational)
        ),
        "unknown_labels": sum(r.get("error_label") is None for r in rows),
        "roles_by_action": dict(Counter(str(r.get("calibration_role")) for r in rows)),
        "semantic_coverage": {f"{c}:error={y}": n for (c, y), n in sorted(coverage.items())},
        "probability_fit": {
            "actions": len(labels),
            "task_groups": len({r["group_id"] for r in probability}),
            "errors": sum(labels),
            "unique_raw_logits": len(set(logits)),
            "logit_std": float(np.std(logits)) if logits else None,
            "raw_metrics": calibration_metrics(logits, labels) if logits else None,
        },
        "tokens_completed_tasks_including_audits": sum(
            r["total_online_tokens"] + r["audit_tokens"] for r in summaries
        ),
        "cost_note": "Completed-task subtotal only; failed/interrupted API calls may add unknown cost.",
    }
    if artifact_path:
        artifact = json.loads(Path(artifact_path).read_text())
        result["artifact"] = {
            "temperature": artifact["temperature"],
            "statistics": artifact["statistics"],
            "metrics_scope": "probability-fitting subset; NOT held-out validation",
            "before": artifact["before"],
            "after": artifact["after"],
        }
        classes = {r["action"]["action_class"] for r in rows if r.get("action")}
        missing = sorted(classes - artifact["statistics"].keys())
        result["artifact"]["missing_observed_action_classes"] = missing
        if missing:
            warnings.append(f"Artifact cannot gate these observed classes: {missing}.")
        if any(s["false_positive_rate"] > 0.5 for s in artifact["statistics"].values()):
            warnings.append(
                "Verifier rejects more than half of correct labeled actions in a fitted class."
            )
        warnings.append(
            "Hash restoration measures workspace integrity, not semantic loss recovery."
        )
    result["warnings"] = warnings
    return result
