import json
from pathlib import Path

from .io import read_jsonl, write_json


def frontier_report(directory):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = Path(directory)
    rows = list(read_jsonl(directory / "frontier.jsonl"))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for policy in sorted({r["policy"] for r in rows}):
        selected = sorted(
            (r for r in rows if r["policy"] == policy), key=lambda r: r["budget_per_trajectory"]
        )
        for ax, metric, ylabel in zip(
            axes,
            ["errors_caught", "consequential_caught"],
            ["Errors caught", "Consequential errors caught"],
        ):
            ax.plot(
                [r["budget_per_trajectory"] for r in selected],
                [r[metric] for r in selected],
                marker="o",
                label=policy,
            )
            ax.set(xlabel="Verification credit cap per trajectory", ylabel=ylabel)
            ax.grid(alpha=0.2)
    axes[1].legend(fontsize=8)
    fig.savefig(directory / "frontier.png", dpi=180)
    fig.savefig(directory / "frontier.pdf")
    plt.close(fig)
    lines = [
        "# VERITAS allocation report",
        "",
        "Fixed-trajectory replay; online success is measured separately.",
        "",
        "| Policy | Budget | Spent | Errors caught | Consequential caught | BVR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['policy']} | {r['budget_per_trajectory']:g} | {r['spent']:.3f} | "
            f"{r['errors_caught']} | {r['consequential_caught']} | {r['budget_violation_rate']:.3f} |"
        )
    lines += [
        "",
        "![Allocation frontier](frontier.png)",
        "",
        "Bootstrap comparisons: paired_bootstrap.json.",
        "The ordering in the proposal is a falsifiable hypothesis, not an enforced result.",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    return str(directory / "report.md")


def online_report(summaries, output, swe_report=None):
    rows = list(read_jsonl(summaries))
    if not rows:
        raise ValueError("Empty online run")
    if swe_report:
        result = json.loads(Path(swe_report).read_text())
        resolved, unresolved = set(result["resolved_ids"]), set(result["unresolved_ids"])
        for row in rows:
            instance_id = row["task_id"].removeprefix("swe:")
            if instance_id in resolved | unresolved:
                row["task_success"] = instance_id in resolved
    scored = [r for r in rows if r["task_success"] is not None]
    report = {
        "tasks": len(rows),
        "scored_tasks": len(scored),
        "ungraded_tasks": len(rows) - len(scored),
        "task_success_rate": sum(r["task_success"] for r in scored) / len(rows)
        if len(scored) == len(rows)
        else None,
        "scored_subset_success_rate": sum(r["task_success"] for r in scored) / len(scored)
        if scored
        else None,
        "total_online_tokens": sum(r["total_online_tokens"] for r in rows),
        "audit_tokens_separate": sum(r["audit_tokens"] for r in rows),
        "token_usage_complete": all(r["token_usage_complete"] for r in rows),
        "budget_violation_rate": sum(r["budget_violation"] for r in rows) / len(rows),
    }
    write_json(output, report)
    return report


def action_metrics(records):
    """Unknown semantic labels never become zero errors or false alarms."""
    all_rows = list(records)
    rows = [r for r in all_rows if not r.get("blocked") and r.get("action")]
    labeled = [
        r for r in rows if r.get("label_scope") == "semantic" and r.get("error_label") is not None
    ]
    rejected = [
        r
        for r in rows
        if r.get("decision") == "verify" and (r.get("verification") or {}).get("verdict") == "FAIL"
    ]
    known_rejected = [r for r in rejected if r in labeled]
    complete = len(known_rejected) == len(rejected)
    return {
        "eligible_actions": len(rows),
        "semantic_labeled_actions": len(labeled),
        "semantic_label_coverage": len(labeled) / len(rows) if rows else None,
        "verifications": sum(r.get("decision") == "verify" for r in rows),
        "verifier_errors": sum(
            (r.get("verification") or {}).get("verdict") == "ERROR" for r in rows
        ),
        "critic_errors": sum(bool(r.get("critic_error")) for r in all_rows),
        "fallback_actions": sum(bool(r.get("fallback_reason")) for r in all_rows),
        "advisory_reviews": sum(bool(r.get("revision_requested")) for r in all_rows),
        "deterministic_rejections": sum(
            (r.get("verification") or {}).get("basis") == "deterministic" for r in rejected
        ),
        "unlabeled_rejections": len(rejected) - len(known_rejected),
        "errors_caught": sum(r["error_label"] == 1 for r in known_rejected) if complete else None,
        "false_rejections": sum(r["error_label"] == 0 for r in known_rejected)
        if complete
        else None,
    }


def recovery_comparison(checkpoint_path, restart_path, output):
    a, b = list(read_jsonl(checkpoint_path)), list(read_jsonl(restart_path))

    def keyed(rows):
        return {(r["task_id"], r["model"], r["seed"]): r for r in rows}

    if any(r.get("recovery_mode") != "checkpoint" for r in a) or any(
        r.get("recovery_mode") != "restart" for r in b
    ):
        raise ValueError("Compare checkpoint runs against measured restart runs")
    left, right = keyed(a), keyed(b)
    if len(left) != len(a) or len(right) != len(b) or set(left) != set(right):
        raise ValueError("Recovery comparison needs unique paired task/model runs")
    checkpoint = sum(r["total_online_tokens"] for r in a)
    restart = sum(r["total_online_tokens"] for r in b)
    result = {
        "paired_tasks": len(left),
        "checkpoint_tokens": checkpoint,
        "restart_tokens": restart,
        "recovery_token_savings": 1 - checkpoint / restart if restart else None,
        "warning": "Measured paired runs only; ensure identical policies, seeds, and stopping rules",
    }
    write_json(output, result)
    return result
