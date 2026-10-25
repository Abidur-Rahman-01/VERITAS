# VERITAS Publication Figures (`output image/`)

This directory contains all **8 high-resolution (300 DPI) publication-ready figures** covering 100% of the experimental tracks, benchmark suites, and causal studies in the VERITAS project. All figures are tracked in git and formatted for direct inclusion into LaTeX / Overleaf manuscripts.

---

## Complete Figure Catalog

### 1. [`fig1_compute_escalation.png`](fig1_compute_escalation.png)
* **Title:** Compute Escalation & Tool Calls under Evaluation Awareness
* **Dimensions:** 3000 × 1260 px (300 DPI)
* **What it Illustrates:**
  * **(a) Token Escalation:** Demonstrates the **3.18× compute surge** (+218% token consumption) when agents are informed of benchmark evaluation ($D=1$, 75,084 tokens) vs. unmonitored production prompts ($D=0$, 23,631 tokens).
  * **(b) Deployed Tool Calls:** Demonstrates the statistically significant escalation in multi-turn tool invocations on CLI tasks ($26.75 \pm 0.50$ vs. $32.50 \pm 0.58$ calls, Welch's $t = 15.0570, p < 0.0001$).
* **Role:** Primary empirical evidence for **Paper 1 (The Anti-Surrender Hawthorne Effect)**.
* **Source:** [`replication/data/study_cmd2_persistence_8.csv`](../replication/data/study_cmd2_persistence_8.csv).

---

### 2. [`fig2_factorial_interaction.png`](fig2_factorial_interaction.png)
* **Title:** $2 \times 2$ Factorial Design Interaction (Awareness vs. Feedback)
* **Dimensions:** 1950 × 1200 px (300 DPI)
* **What it Illustrates:**
  * Median token consumption across all four factorial cells:
    * **Arm 00 ($D=0, A=0$):** 23,410 median tokens.
    * **Arm 01 ($D=0, A=1$):** 23,647 median tokens.
    * **Arm 10 ($D=1, A=0$):** 75,150 median tokens.
    * **Arm 11 ($D=1, A=1$):** 75,018 median tokens.
  * Shows that compute escalation is driven by disclosure factor $D$, refuting passive single-turn "sandbagging".
* **Role:** Factorial interaction decomposition for **Paper 1**.
* **Source:** [`replication/data/study_grand_pool_128.csv`](../replication/data/study_grand_pool_128.csv).

---

### 3. [`fig3_persistence_survival.png`](fig3_persistence_survival.png)
* **Title:** Agent Persistence & Anti-Surrender Survival Function
* **Dimensions:** 2040 × 1200 px (300 DPI)
* **What it Illustrates:**
  * Kaplan-Meier survival curves measuring the probability of continued execution over 60 steps.
  * **Unmonitored ($D=0$):** Sharp drop-off at step 11 due to premature surrender (100% surrender rate on CLI).
  * **Evaluated ($D=1$):** Complete persistence through all 32+ draft and revision steps (0% surrender rate, Fisher's Exact $p = 0.0143$).
* **Role:** Core persistence and survival proof for **Paper 1**.
* **Source:** [`replication/data/study_grand_pool_128.csv`](../replication/data/study_grand_pool_128.csv).

---

### 4. [`fig4_full_benchmark_resolution.png`](fig4_full_benchmark_resolution.png)
* **Title:** Master 2,240-Task Standardized Benchmark Suite
* **Dimensions:** 3000 × 1260 px (300 DPI)
* **What it Illustrates:**
  * **(a) Resolution Rates:** 100% full-split benchmark resolution under LocalSandbox:
    * **GSM8K:** 90.67% (1,196 / 1,319 resolved)
    * **MBPP Sanitized:** 83.66% (215 / 257 resolved)
    * **HumanEval:** 83.54% (137 / 164 resolved)
    * **MATH-500:** 69.20% (346 / 500 resolved)
    * **Overall Pass@1:** **84.55%** (1,894 / 2,240 tasks resolved).
  * **(b) Autonomous Verifier Recoveries:** Total of **101 draft-to-pass repairs** (50 GSM8K, 44 MATH-500, 6 MBPP, 1 HumanEval).
* **Role:** Large-scale empirical foundation for **Paper 2 (Causal Verifier Attribution)**.
* **Source:** [`artifacts/master_full_study_20261014_014437/master_report.json`](../artifacts/master_full_study_20261014_014437/master_report.json).

---

### 5. [`fig5_fault_localization_gap.png`](fig5_fault_localization_gap.png)
* **Title:** The Fault Localization Gap & In-Place Scaffolding Intervention
* **Dimensions:** 2100 × 1260 px (300 DPI)
* **What it Illustrates:**
  * Controlled comparison ($N = 16$ paired trials across 4 tasks and 2 models) between Generic Prompt A and In-Place Scaffolding Prompt B:
    * **Semantic Fix Deduced:** 62.5% vs. 62.5% (models deduce the repair logic regardless of prompt).
    * **Correct Fault Localization:** Jumps from **37.5% to 100.0%** ($+62.5\%$).
    * **Final Benchmark Pass Rate:** Increases from **25.0% to 62.5%** ($+37.5\%$) without modifying model weights.
* **Role:** Primary empirical proof for **Paper 3 (The Fault Localization Bottleneck)**.
* **Source:** [`replication/data/controlled_localization_comparison.csv`](../replication/data/controlled_localization_comparison.csv).

---

### 6. [`fig6_model_scaling_benchmark.png`](fig6_model_scaling_benchmark.png)
* **Title:** Local Open-Weights Model Scaling & Capability Benchmark
* **Dimensions:** 2400 × 1260 px (300 DPI)
* **What it Illustrates:**
  * Comparative task resolution rates and median execution latencies across 6 open-weights model architectures on standardized sandbox tasks:
    * `qwen2.5-coder:30b`: **85.7%** resolution (5.2s median)
    * `qwen2.5-coder:14b`: **57.1%** resolution (14.6s median)
    * `deepcoder:14b`: **57.1%** resolution (60.2s median)
    * `deepseek-coder-v2:16b`: **28.6%** resolution (14.6s median)
    * `granite-code:20b` & `starcoder2:15b`: **0.0%**
* **Role:** Multi-model generalizability and scaling calibration figure.
* **Source:** [`artifacts/model_benchmark_20261013_210244/benchmark_report.json`](../artifacts/model_benchmark_20261013_210244/benchmark_report.json).

---

### 7. [`fig_causal_contrasts.png`](fig_causal_contrasts.png)
* **Title:** Causal Contrasts under Equal Inference Budgets
* **Dimensions:** 3000 × 1260 px (300 DPI)
* **What it Illustrates:**
  * **(a) Resolution by Arm:** Compares Draft-Only (20.0%) vs. Self-Revision (20.0%) vs. Verifier-Guided (20.0%) under identical token/step limits.
  * **(b) Primary Causal Contrasts:** Illustrates $\Delta_{\text{verifier\_vs\_retry}} = +0.00\%$ and the safety boundary under advisory reviewer models.
* **Role:** Causal identification figure for **Paper 2**.
* **Source:** [`artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json`](../artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json).

---

### 8. [`fig_recovery_regressions.png`](fig_recovery_regressions.png)
* **Title:** Revision Dynamics: Autonomous Recoveries vs. Regressions
* **Dimensions:** 1950 × 1260 px (300 DPI)
* **What it Illustrates:**
  * Task state transitions between Draft and Revision phases, confirming an unblemished **0.0% regression rate** on working code.
* **Role:** Safety and stability analysis for **Paper 2**.
* **Source:** [`artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json`](../artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json).

---

## Deterministic Regeneration Commands

To regenerate any or all of these figures from raw CSV and JSON records:

```bash
# 1. Regenerate Figures 1, 2, and 3
python replication/scripts/reproduce_all.py

# 2. Regenerate Figures 4, 5, and 6
python scripts/generate_all_study_figures.py

# 3. Regenerate Figures 7 and 8
python scripts/generate_causal_verifier_figures.py artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json "output image"
```
