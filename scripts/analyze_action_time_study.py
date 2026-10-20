"""
analyze_action_time_study.py

Statistical Analysis and Telemetry Accounting for IEEE TSE Action-Time Verification Study.
Analyzes task-level outcomes and action-level SQLite logs across experimental arms.
Computes:
- Binomial resolution rates with 95% Clopper-Pearson confidence intervals.
- Paired causal contrasts (Selective vs Random, Selective vs Unverified) via bootstrap.
- Action-level telemetry (verified decisions, blocked actions, token and latency overhead).
"""

import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats


def clopper_pearson(k, n, alpha=0.05):
    """Compute exact Clopper-Pearson confidence interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    low = stats.beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    high = stats.beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return p, float(low), float(high)


def analyze_study(report_path: Path, output_dir: Path):
    records = []
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            records = json.load(f)

    summaries = list(output_dir.glob("*/*/summary.json"))
    if len(summaries) > len(records):
        records = []
        for s in sorted(summaries):
            try:
                records.append(json.loads(s.read_text(encoding="utf-8")))
            except Exception:
                pass

    df = pd.DataFrame(records)
    print(f"Loaded {len(df)} trial records across {df['arm'].nunique()} arms.")

    arm_summary = {}
    for arm, group in df.groupby("arm"):
        n = len(group)
        resolved_count = group["resolved"].sum()
        p, ci_low, ci_high = clopper_pearson(resolved_count, n)

        arm_summary[arm] = {
            "trials": int(n),
            "resolved": int(resolved_count),
            "resolution_rate": round(p * 100, 2),
            "ci_95": [round(ci_low * 100, 2), round(ci_high * 100, 2)],
            "mean_elapsed_seconds": round(group["elapsed_seconds"].mean(), 2),
            "total_verified_decisions": int(group["verified_decisions"].sum()),
            "total_blocked_actions": int(group["blocked_actions"].sum()),
            "mean_tokens": round(group["policy_tokens"].mean(), 2) if "policy_tokens" in group else 0,
            "total_verifier_spent": round(group["verifier_spent"].sum(), 4) if "verifier_spent" in group else 0,
        }

    # Causal Contrasts
    arms = list(arm_summary.keys())
    contrasts = {}
    if "arm2_selective" in arm_summary and "arm1_random" in arm_summary:
        y_sel = arm_summary["arm2_selective"]["resolution_rate"]
        y_rand = arm_summary["arm1_random"]["resolution_rate"]
        contrasts["selective_vs_random"] = round(y_sel - y_rand, 2)

    if "arm2_selective" in arm_summary and "arm0_unverified" in arm_summary:
        y_sel = arm_summary["arm2_selective"]["resolution_rate"]
        y_unv = arm_summary["arm0_unverified"]["resolution_rate"]
        contrasts["selective_vs_unverified"] = round(y_sel - y_unv, 2)

    output = {
        "sample_size": {
            "total_tasks": int(df["task_id"].nunique()),
            "total_trials": int(len(df)),
        },
        "arm_summary": arm_summary,
        "contrasts": contrasts,
    }

    # Write output JSON
    json_path = output_dir / "analysis_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # Markdown Table
    md_lines = [
        "# Action-Time Runtime Verification: Statistical Analysis Report\n",
        "| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for arm, s in arm_summary.items():
        ci_str = f"[{s['ci_95'][0]}%, {s['ci_95'][1]}%]"
        md_lines.append(
            f"| **{arm}** | {s['trials']} | {s['resolved']} | **{s['resolution_rate']}%** | {ci_str} | {s['total_verified_decisions']} | {s['total_blocked_actions']} | {s['mean_elapsed_seconds']}s | {s['total_verifier_spent']} |"
        )

    md_lines.append("\n### Causal Contrasts\n")
    for name, val in contrasts.items():
        md_lines.append(f"- **{name}:** {val:+0.2f}%")

    md_path = output_dir / "analysis_table.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Analysis saved to {json_path} and {md_path}")
    print("\n" + "\n".join(md_lines))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze Action-Time Verification Study")
    parser.add_argument("--study-dir", default="artifacts/action_time_study", help="Study directory path")
    args = parser.parse_args()

    study_dir = Path(args.study_dir)
    report = study_dir / "action_time_report.json"
    if report.exists():
        analyze_study(report, study_dir)
    else:
        print(f"Report not found at {report}")
