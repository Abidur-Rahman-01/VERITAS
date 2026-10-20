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
ax.set_title("Figure 1: Benchmark Resolution by Verification Condition (N = 60)")
ax.grid(axis="y", linestyle=":", alpha=0.6)

plt.tight_layout()
fig1_path = FIG_DIR / "fig1_resolution_by_arm.png"
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f"Saved {fig1_path}")

# Figure 2: Domain-Level Resolution
domains = ["cmd2\n(CLI Framework)", "pennylane\n(Quantum Circuits)", "sympy\n(Symbolic Math)", "repo_maintenance\n(Multi-file Utils)"]
unverified_domain = [40.0, 20.0, 80.0, 60.0]
verified_domain = [60.0, 60.0, 100.0, 60.0]

x = np.arange(len(domains))
width = 0.35

fig, ax = plt.subplots(figsize=(8.0, 4.5))
rects1 = ax.bar(x - width/2, unverified_domain, width, label="Arm 0: Unverified Baseline", color="#7f7f7f", edgecolor="black")
rects2 = ax.bar(x + width/2, verified_domain, width, label="Arms 1 & 2: Action-Time Verification", color="#2ca02c", edgecolor="black")

ax.set_ylabel("Resolved Tasks (%)")
ax.set_title("Figure 2: Resolution by Software Repository Domain (5 Tasks / Domain)")
ax.set_xticks(x)
ax.set_xticklabels(domains)
ax.set_ylim(0, 115)
ax.legend(loc="upper left", frameon=True)
ax.grid(axis="y", linestyle=":", alpha=0.6)

for rect in rects1:
    h = rect.get_height()
    ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom")
for rect in rects2:
    h = rect.get_height()
    ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontweight="bold")

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

ax1.set_ylabel("Total Action Count Across 20 Tasks")
ax1.set_xticks(x)
ax1.set_xticklabels(labels)
ax1.set_title("Figure 3: Runtime Quality-Gate Interceptions and Blocked Actions")
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
