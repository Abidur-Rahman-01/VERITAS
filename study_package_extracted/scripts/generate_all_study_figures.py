"""Generate all remaining study figures into 'output image/'.

Covers:
1. fig4_full_benchmark_resolution.png: 2,240-task benchmark pass rates and verifier recoveries across GSM8K, MBPP, HumanEval, MATH-500
2. fig5_fault_localization_gap.png: In-place localization scaffolding intervention (Prompt A vs Prompt B)
3. fig6_model_scaling_benchmark.png: Open-weights model resolution comparison across parameter scales
"""

import json
import os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

out_dir = Path("F:/Sadik/VERITAS/output image")
out_dir.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.size': 10, 'figure.dpi': 300})

# ==============================================================================
# Figure 4: Master 2,240-Task Benchmark (Resolution & Recoveries)
# ==============================================================================
master_path = Path("artifacts/master_full_study_20261014_014437/master_report.json")
if master_path.exists():
    with open(master_path) as f:
        data_master = json.load(f)

    benchmarks = ["gsm8k", "mbpp", "humaneval", "math500"]
    bench_labels = ["GSM8K\n(1,319 tasks)", "MBPP Sanitized\n(257 tasks)", "HumanEval\n(164 tasks)", "MATH-500\n(500 tasks)"]
    pass_rates = [data_master[b]["pass_at_1"] for b in benchmarks]
    repairs = [data_master[b]["repairs"] for b in benchmarks]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

    # Subplot (a): Pass@1
    colors_pass = ['#4575b4', '#74add1', '#91bfdb', '#f46d43']
    b1 = ax1.bar(bench_labels, pass_rates, color=colors_pass, edgecolor='black', width=0.55)
    ax1.set_ylabel("Post-Loop Resolution Rate (%)")
    ax1.set_title("(a) Benchmark Pass Rates (Overall: 84.55%)")
    ax1.set_ylim(0, 110)
    ax1.grid(axis='y', linestyle='--', alpha=0.5)

    for b in b1:
        h = b.get_height()
        ax1.annotate(f"{h:.1f}%", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4),
                     textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Subplot (b): Autonomous Verifier Recoveries
    colors_rep = ['#31a354', '#74c476', '#a1d99b', '#31a354']
    b2 = ax2.bar(bench_labels, repairs, color=colors_rep, edgecolor='black', width=0.55)
    ax2.set_ylabel("Autonomous Verifier Recoveries (Tasks)")
    ax2.set_title("(b) Draft-to-Pass Recoveries (Total: 101)")
    ax2.set_ylim(0, 60)
    ax2.grid(axis='y', linestyle='--', alpha=0.5)

    for b in b2:
        h = b.get_height()
        ax2.annotate(f"{int(h)} repairs", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4),
                     textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

    plt.tight_layout()
    f4_path = out_dir / "fig4_full_benchmark_resolution.png"
    plt.savefig(f4_path, dpi=300)
    plt.close()
    print(f"Generated {f4_path}")

# ==============================================================================
# Figure 5: Fault Localization Gap & In-Place Scaffolding
# ==============================================================================
loc_path = Path("replication/data/controlled_localization_comparison.csv")
if loc_path.exists():
    df_loc = pd.read_csv(loc_path)
    
    categories = ["Prompt A\n(Generic Baseline)", "Prompt B\n(In-Place Scaffolding)"]
    loc_rates = [
        (df_loc[df_loc['condition'] == 'Prompt_A_Baseline']['correct_localization'].mean()) * 100,
        (df_loc[df_loc['condition'] == 'Prompt_B_Localized']['correct_localization'].mean()) * 100,
    ]
    sem_rates = [
        (df_loc[df_loc['condition'] == 'Prompt_A_Baseline']['semantic_correctness'].mean()) * 100,
        (df_loc[df_loc['condition'] == 'Prompt_B_Localized']['semantic_correctness'].mean()) * 100,
    ]
    res_rates = [
        (df_loc[df_loc['condition'] == 'Prompt_A_Baseline']['resolved'].mean()) * 100,
        (df_loc[df_loc['condition'] == 'Prompt_B_Localized']['resolved'].mean()) * 100,
    ]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(categories))
    width = 0.25

    r1 = ax.bar(x - width, sem_rates, width, label='Semantic Fix Deduced', color='#91bfdb', edgecolor='black')
    r2 = ax.bar(x, loc_rates, width, label='Correct Fault Localization', color='#fc8d59', edgecolor='black')
    r3 = ax.bar(x + width, res_rates, width, label='Benchmark Test Resolved', color='#2ca25f', edgecolor='black')

    ax.set_ylabel("Percentage (%)")
    ax.set_title("The Fault Localization Gap: Semantic Fix vs. In-Place Editing")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontweight='bold')
    ax.set_ylim(0, 115)
    ax.legend(frameon=True, loc='upper left')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for bars in [r1, r2, r3]:
        for b in bars:
            h = b.get_height()
            ax.annotate(f"{h:.1f}%", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 3),
                        textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    plt.tight_layout()
    f5_path = out_dir / "fig5_fault_localization_gap.png"
    plt.savefig(f5_path, dpi=300)
    plt.close()
    print(f"Generated {f5_path}")

# ==============================================================================
# Figure 6: Model Scaling & Capability Benchmark
# ==============================================================================
bench_path = Path("artifacts/model_benchmark_20261013_210244/benchmark_report.json")
if bench_path.exists():
    with open(bench_path) as f:
        data_bench = json.load(f)

    models_data = [m for m in data_bench.get("summary", []) if m["tasks_attempted"] >= 7]
    models_data.sort(key=lambda m: m["resolution_rate_pct"], reverse=True)

    m_names = [m["model"] for m in models_data]
    m_res = [m["resolution_rate_pct"] for m in models_data]
    m_sec = [m["seconds_median"] for m in models_data]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    colors_mod = ['#2ca25f' if r >= 80 else ('#4575b4' if r >= 50 else ('#fdae61' if r > 0 else '#d73027')) for r in m_res]
    bars_m = ax.barh(m_names[::-1], m_res[::-1], color=colors_mod[::-1], edgecolor='black', height=0.6)

    ax.set_xlabel("Task Resolution Rate (%)")
    ax.set_title("Local Model Capability Benchmark (Standardized Sandbox Tasks)")
    ax.set_xlim(0, 105)
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    for b, s in zip(bars_m, m_sec[::-1]):
        w = b.get_width()
        ax.annotate(f"{w:.1f}%  ({s:.1f}s med)", xy=(w, b.get_y() + b.get_height()/2), xytext=(5, 0),
                    textcoords="offset points", ha='left', va='center', fontsize=8, fontweight='bold')

    plt.tight_layout()
    f6_path = out_dir / "fig6_model_scaling_benchmark.png"
    plt.savefig(f6_path, dpi=300)
    plt.close()
    print(f"Generated {f6_path}")
