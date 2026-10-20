"""
generate_cross_model_figure.py
Generates master cross-model publication figure for the 5-model 900-trial TSE benchmark.
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

MODELS = [
    ("Qwen2.5-Coder\n(14B)", REPO_ROOT / "artifacts" / "action_time_study_qwen2.5_coder_14b" / "analysis_summary.json"),
    ("DeepSeek-V2\n(16B)", REPO_ROOT / "artifacts" / "action_time_study_deepseek_coder_v2_16b" / "analysis_summary.json"),
    ("Granite-Code\n(20B)", REPO_ROOT / "artifacts" / "action_time_study_granite_code_20b" / "analysis_summary.json"),
    ("StarCoder2\n(15B)", REPO_ROOT / "artifacts" / "action_time_study_starcoder2_15b" / "analysis_summary.json"),
    ("Qwen2.5-Coder\n(30B)", REPO_ROOT / "artifacts" / "action_time_study_qwen2.5_coder_30b" / "analysis_summary.json"),
]

names, a0_res, a1_res, a2_res = [], [], [], []
a0_lat, a1_lat, a2_lat = [], [], []

for label, p in MODELS:
    data = json.loads(p.read_text(encoding="utf-8"))
    arms = data["arm_summary"]
    names.append(label)
    a0_res.append(float(arms["arm0_unverified"]["resolution_rate"]))
    a1_res.append(float(arms["arm1_random"]["resolution_rate"]))
    a2_res.append(float(arms["arm2_selective"]["resolution_rate"]))
    a0_lat.append(float(arms["arm0_unverified"]["mean_elapsed_seconds"]))
    a1_lat.append(float(arms["arm1_random"]["mean_elapsed_seconds"]))
    a2_lat.append(float(arms["arm2_selective"]["mean_elapsed_seconds"]))

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)

x = np.arange(len(names))
width = 0.26

rects1 = ax1.bar(x - width, a0_res, width, label="Arm 0 (Unverified)", color="#94a3b8", edgecolor="black")
rects2 = ax1.bar(x, a1_res, width, label="Arm 1 (Random Control)", color="#f59e0b", edgecolor="black")
rects3 = ax1.bar(x + width, a2_res, width, label="Arm 2 (Selective Gating)", color="#2563eb", edgecolor="black")

ax1.set_ylabel("Resolution Rate (%)", fontsize=11, fontweight="bold")
ax1.set_title("(a) Defect Resolution Across 5 Coder Architectures (N=900)", fontsize=11, fontweight="bold")
ax1.set_xticks(x)
ax1.set_xticklabels(names, fontsize=10)
ax1.set_ylim(0, 108)
ax1.legend(loc="upper left", frameon=True)

for rects in [rects1, rects2, rects3]:
    for rect in rects:
        h = rect.get_height()
        if h > 0:
            ax1.annotate(f"{h:.1f}%",
                        xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8, fontweight="bold")

rects4 = ax2.bar(x - width, a0_lat, width, label="Arm 0 (Unverified)", color="#94a3b8", edgecolor="black")
rects5 = ax2.bar(x, a1_lat, width, label="Arm 1 (Random Control)", color="#f59e0b", edgecolor="black")
rects6 = ax2.bar(x + width, a2_lat, width, label="Arm 2 (Selective Gating)", color="#2563eb", edgecolor="black")

ax2.set_ylabel("Mean Task Latency (Seconds)", fontsize=11, fontweight="bold")
ax2.set_title("(b) Execution Latency & Compounding Loop Truncation", fontsize=11, fontweight="bold")
ax2.set_xticks(x)
ax2.set_xticklabels(names, fontsize=10)
ax2.legend(loc="upper right", frameon=True)

for rects in [rects4, rects5, rects6]:
    for rect in rects:
        h = rect.get_height()
        if h > 0:
            ax2.annotate(f"{h:.1f}s",
                        xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8)

fig.suptitle("IEEE TSE Master Empirical Benchmark: Action-Time Runtime Verification Across 5 Models (900 Total Trials)", fontsize=13, fontweight="bold", y=0.98)
plt.tight_layout()

out_dir = REPO_ROOT / "artifacts" / "figures"
out_dir.mkdir(parents=True, exist_ok=True)
fig_path = out_dir / "cross_model_benchmark_comparison_900_trials.png"
plt.savefig(fig_path, dpi=300, bbox_inches="tight")
print(f"Master figure saved: {fig_path}")
