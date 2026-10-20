"""
generate_tse_action_time_figures.py

Generates publication-quality figures for the IEEE TSE Action-Time Verification manuscript:
- Figure 1: Task Resolution Rate with 95% Clopper-Pearson CIs across Arms.
- Figure 2: Domain-Level Resolution Comparison across Repository Suites.
- Figure 3: Action-Level Telemetry (Verified Decisions vs Blocked Actions vs Compute Overhead).
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDY_DIR = REPO_ROOT / "artifacts" / "action_time_study"
FIG_DIR = STUDY_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Set IEEE Publication Styling
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "figure.dpi": 300,
})

# Load analysis data
with open(STUDY_DIR / "analysis_summary.json", "r", encoding="utf-8") as f:
    summary = json.load(f)

# Figure 1: Task Resolution Rates with Exact 95% CIs
fig, ax = plt.subplots(figsize=(6.5, 4.2))

arms = ["arm0_unverified", "arm1_random", "arm2_selective"]
labels = ["Arm 0\nUnverified Baseline", "Arm 1\nRandom Verification", "Arm 2\nSelective Gate (VERITAS)"]
colors = ["#7f7f7f", "#1f77b4", "#2ca02c"]

rates = [summary["arm_summary"][a]["resolution_rate"] for a in arms]
ci_lows = [summary["arm_summary"][a]["ci_95"][0] for a in arms]
ci_highs = [summary["arm_summary"][a]["ci_95"][1] for a in arms]
total_tasks = summary["sample_size"]["total_tasks"]
total_trials = summary["sample_size"]["total_trials"]

yerr = [
    [rates[i] - ci_lows[i] for i in range(len(arms))],
    [ci_highs[i] - rates[i] for i in range(len(arms))],
]

bars = ax.bar(labels, rates, yerr=yerr, capsize=6, color=colors, alpha=0.85, edgecolor="black", width=0.55)

# Add values above bars
for bar, r in zip(bars, rates):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width() / 2.0, height + 4.5, f"{r:.1f}%", ha="center", va="bottom", fontweight="bold")

ax.set_ylabel("Independently Graded Resolution Rate (%)")
ax.set_ylim(0, 105)
ax.axhline(50.0, color="gray", linestyle="--", linewidth=1.0, alpha=0.7)
ax.set_title(f"Figure 1: Benchmark Resolution by Verification Condition (N = {total_trials} Trials, {total_tasks} Tasks)")
ax.grid(axis="y", linestyle=":", alpha=0.6)

plt.tight_layout()
fig1_path = FIG_DIR / "fig1_resolution_by_arm.png"
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f"Saved {fig1_path}")

# Figure 2: Domain-Level Resolution
# Dynamically aggregate from action_time_report.json
with open(STUDY_DIR / "action_time_report.json", "r", encoding="utf-8") as f:
    records = json.load(f)

def get_domain(task_id: str) -> str:
    if "cmd2" in task_id: return "cmd2\n(CLI Framework)"
    if "sympy" in task_id: return "sympy\n(Symbolic Math)"
    if "pennylane" in task_id: return "pennylane\n(Quantum Circuits)"
    if any(k in task_id for k in ["interpolator", "coercer", "csv", "cli", "sql"]):
        return "maintenance\n(Multi-file Utils)"
    if any(k in task_id for k in ["topological", "router", "constant_time", "iso_duration"]):
        return "algorithms\n(Core Algorithms)"
    if any(k in task_id for k in ["lru", "nested", "query", "links", "headers", "semver", "retry"]):
        return "calibration\n(Calibration Utils)"
    return "production\n(Production Systems)"

import collections
domain_arm_res = collections.defaultdict(lambda: collections.defaultdict(list))
for r in records:
    dom = get_domain(r["task_id"])
    domain_arm_res[dom][r["arm"]].append(r["resolved"])

domains = sorted(domain_arm_res.keys())
unverified_rates = [
    (sum(domain_arm_res[d]["arm0_unverified"]) / max(1, len(domain_arm_res[d]["arm0_unverified"]))) * 100
    for d in domains
]
selective_rates = [
    (sum(domain_arm_res[d]["arm2_selective"]) / max(1, len(domain_arm_res[d]["arm2_selective"]))) * 100
    for d in domains
]

x = np.arange(len(domains))
width = 0.35

fig, ax = plt.subplots(figsize=(10.0, 5.0))
rects1 = ax.bar(x - width/2, unverified_rates, width, label="Arm 0: Unverified Baseline", color="#7f7f7f", edgecolor="black")
rects2 = ax.bar(x + width/2, selective_rates, width, label="Arm 2: Selective Quality Gate (VERITAS)", color="#2ca02c", edgecolor="black")

ax.set_ylabel("Resolved Tasks (%)")
ax.set_title(f"Figure 2: Resolution by Software Repository Domain ({total_tasks} Tasks Across {len(domains)} Domains)")
ax.set_xticks(x)
ax.set_xticklabels(domains, fontsize=9)
ax.set_ylim(0, 115)
ax.legend(loc="upper left", frameon=True)
ax.grid(axis="y", linestyle=":", alpha=0.6)

for rect in rects1:
    h = rect.get_height()
    ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8)
for rect in rects2:
    h = rect.get_height()
    ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontweight="bold", fontsize=8)

plt.tight_layout()
fig2_path = FIG_DIR / "fig2_domain_resolution.png"
plt.savefig(fig2_path, dpi=300)
plt.close()
print(f"Saved {fig2_path}")

# Figure 3: Action-Level Telemetry (Verifications vs Blocked)
fig, ax1 = plt.subplots(figsize=(7.0, 4.5))

x = np.arange(len(arms))
verified_counts = [summary["arm_summary"][a]["total_verified_decisions"] for a in arms]
blocked_counts = [summary["arm_summary"][a]["total_blocked_actions"] for a in arms]

w = 0.32
b1 = ax1.bar(x - w/2, verified_counts, w, label="Verified Decisions (decision='verify')", color="#1f77b4", edgecolor="black")
b2 = ax1.bar(x + w/2, blocked_counts, w, label="Blocked Faulty Actions (blocked=True)", color="#d62728", edgecolor="black")

ax1.set_ylabel(f"Total Action Count Across {total_tasks} Tasks")
ax1.set_xticks(x)
ax1.set_xticklabels(labels)
ax1.set_title(f"Figure 3: Runtime Quality-Gate Interceptions and Blocked Actions (N = {total_trials})")
ax1.legend(loc="upper left")
ax1.grid(axis="y", linestyle=":", alpha=0.6)

for b in b1:
    h = b.get_height()
    ax1.annotate(f"{h}", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom")
for b in b2:
    h = b.get_height()
    ax1.annotate(f"{h}", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontweight="bold")

plt.tight_layout()
fig3_path = FIG_DIR / "fig3_action_telemetry.png"
plt.savefig(fig3_path, dpi=300)
plt.close()
print(f"Saved {fig3_path}")
