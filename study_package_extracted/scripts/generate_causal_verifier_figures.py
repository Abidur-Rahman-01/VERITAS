"""Publication Figure Generator for Causal Verifier Experiment.

Generates:
1. fig_causal_contrasts.png: Causal contrasts between Verifier Feedback, Generic Retry, and Draft-Only
2. fig_recovery_regressions.png: Recovery rate on initially failing tasks vs Regression rate
3. fig_compute_tradeoff.png: Success rate vs Compute (Tokens & Latency) trade-off
"""

import json
import os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def generate_figures(report_path: Path, out_dir: Path):
    with open(report_path) as f:
        data = json.load(f)

    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'figure.dpi': 300})

    arm_stats = data["arm_statistics"]
    arms = ["draft_only", "self_revision", "verifier_guided"]
    arm_labels = ["Draft-Only\n(One-Shot)", "Self-Revision\n(Generic Retry)", "Verifier-Guided\n(Actionable Feedback)"]

    # -------------------------------------------------------------------------
    # Figure 1: Resolution Rate by Arm and Causal Contrasts
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

    # Subplot (a): Resolution Rates
    rates = [arm_stats[a]["resolution_rate_pct"] for a in arms]
    colors = ['#4575b4', '#74add1', '#d73027']
    bars = ax1.bar(arm_labels, rates, color=colors, edgecolor='black', width=0.5)
    ax1.set_ylabel("Independently Graded Success Rate (%)")
    ax1.set_title("(a) End-Task Resolution by Arm")
    ax1.set_ylim(0, 115)
    ax1.grid(axis='y', linestyle='--', alpha=0.5)

    for b in bars:
        h = b.get_height()
        ax1.annotate(f"{h:.1f}%", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4),
                     textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Subplot (b): Causal Contrasts
    contrasts = data["causal_contrasts"]
    c_labels = ["Verifier vs Retry\n(Actionable Feedback)", "Retry vs Draft\n(Blind Second Attempt)", "Verifier vs Draft\n(Total Loop Benefit)"]
    c_vals = [
        contrasts["delta_verifier_vs_generic_retry"] * 100,
        contrasts["delta_generic_retry_vs_draft_only"] * 100,
        contrasts["delta_verifier_vs_draft_only"] * 100,
    ]
    c_colors = ['#d73027' if v >= 0 else '#4575b4' for v in c_vals]
    b_c = ax2.bar(c_labels, c_vals, color=c_colors, edgecolor='black', width=0.5)
    ax2.axhline(0, color='black', linewidth=1)
    ax2.set_ylabel("Causal Difference (Percentage Points)")
    ax2.set_title("(b) Primary Causal Contrast Estimands")
    ax2.grid(axis='y', linestyle='--', alpha=0.5)

    for b in b_c:
        h = b.get_height()
        va = 'bottom' if h >= 0 else 'top'
        offset = 4 if h >= 0 else -12
        ax2.annotate(f"{h:+.1f}%", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, offset),
                     textcoords="offset points", ha='center', va=va, fontsize=9, fontweight='bold')

    plt.tight_layout()
    f1_path = out_dir / "fig_causal_contrasts.png"
    plt.savefig(f1_path, dpi=300)
    plt.close()
    print(f"Generated {f1_path}")

    # -------------------------------------------------------------------------
    # Figure 2: Transitions & Recoveries
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    repairs = [arm_stats[a]["repairs"] for a in arms]
    regressions = [arm_stats[a]["regressions"] for a in arms]

    x = np.arange(len(arms))
    width = 0.35
    r1 = ax.bar(x - width/2, repairs, width, label='Recoveries (Fail -> Pass)', color='#2ca25f', edgecolor='black')
    r2 = ax.bar(x + width/2, regressions, width, label='Regressions (Pass -> Fail)', color='#de2d26', edgecolor='black')

    ax.set_ylabel("Count of Task Transitions")
    ax.set_title("Revision Dynamics: Recoveries vs. Regressions")
    ax.set_xticks(x)
    ax.set_xticklabels(arm_labels)
    ax.legend(frameon=True)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for r in r1:
        h = r.get_height()
        ax.annotate(f"{int(h)}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    for r in r2:
        h = r.get_height()
        ax.annotate(f"{int(h)}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

    plt.tight_layout()
    f2_path = out_dir / "fig_recovery_regressions.png"
    plt.savefig(f2_path, dpi=300)
    plt.close()
    print(f"Generated {f2_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        r_path = Path(sys.argv[1])
        o_path = Path(sys.argv[2]) if len(sys.argv) > 2 else r_path.parent / "figures"
        generate_figures(r_path, o_path)
