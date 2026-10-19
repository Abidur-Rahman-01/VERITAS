# VERITAS Publication Figures (`output image/`)

This directory contains all high-resolution (300 DPI) publication-ready figures generated across the VERITAS experimental campaigns. These figures are tracked in git and ready for publication in research manuscripts, presentations, and LaTeX submissions.

---

## Figure Manifest & Scientific Summary

### 1. [`fig1_compute_escalation.png`](fig1_compute_escalation.png)
* **Title:** Compute Escalation & Tool Calls under Evaluation Awareness
* **Dimensions:** 3000 × 1260 px (300 DPI, Vector Fonts)
* **What it Illustrates:**
  * **Subplot (a) Token Escalation:** Demonstrates the **3.18× compute surge** (+218% increase in deployed model tokens) when autonomous agents are informed of benchmark evaluation ($D=1$, 75,084 tokens) compared to identical unmonitored production prompts ($D=0$, 23,631 tokens).
  * **Subplot (b) Deployed Tool Calls:** Demonstrates the statistically significant escalation in active multi-turn tool invocations on CLI tasks ($26.75 \pm 0.50$ vs. $32.50 \pm 0.58$ calls, Welch's $t = 15.0570, p < 0.0001$).
* **Primary Paper Role:** Main empirical result for **Paper 1 (The Anti-Surrender Hawthorne Effect)**.
* **Data Source:** [`replication/data/study_cmd2_persistence_8.csv`](../replication/data/study_cmd2_persistence_8.csv) and [`replication/data/study_grand_pool_128.csv`](../replication/data/study_grand_pool_128.csv).

---

### 2. [`fig2_factorial_interaction.png`](fig2_factorial_interaction.png)
* **Title:** $2 \times 2$ Factorial Design Interaction (Awareness vs. Feedback)
* **Dimensions:** 1950 × 1200 px (300 DPI)
* **What it Illustrates:**
  * Median token consumption across all four factorial cells:
    * **Arm 00 ($D=0, A=0$):** Baseline unmonitored control (23,410 median tokens).
    * **Arm 01 ($D=0, A=1$):** Feedback alone without advance disclosure (23,647 median tokens).
    * **Arm 10 ($D=1, A=0$):** Advance disclosure alone / pure anticipation (75,150 median tokens).
    * **Arm 11 ($D=1, A=1$):** Combined disclosure and delivered review feedback (75,018 median tokens).
  * Shows that compute escalation is primarily driven by disclosure factor $D$, refuting passive single-turn "sandbagging".
* **Primary Paper Role:** Factorial decomposition figure for **Paper 1**.
* **Data Source:** [`replication/data/study_grand_pool_128.csv`](../replication/data/study_grand_pool_128.csv).

---

### 3. [`fig3_persistence_survival.png`](fig3_persistence_survival.png)
* **Title:** Agent Persistence & Anti-Surrender Survival Function
* **Dimensions:** 2040 × 1200 px (300 DPI)
* **What it Illustrates:**
  * Kaplan-Meier empirical survival curve measuring the probability of continued agent execution across step horizons (0 to 60 steps).
  * **Unmonitored ($D=0$):** Sharp drop-off around step 11 due to premature task abandonment (100% surrender rate on CLI tasks).
  * **Evaluated ($D=1$):** Near-horizontal line maintaining active execution through all 32+ draft and revision steps (0% surrender rate, Fisher's Exact $p = 0.0143$).
* **Primary Paper Role:** Core persistence proof for **Paper 1**.
* **Data Source:** [`replication/data/study_grand_pool_128.csv`](../replication/data/study_grand_pool_128.csv).

---

### 4. [`fig_causal_contrasts.png`](fig_causal_contrasts.png)
* **Title:** Causal Contrasts under Equal Inference Budgets
* **Dimensions:** 3000 × 1260 px (300 DPI)
* **What it Illustrates:**
  * **Subplot (a) Resolution Rates:** Independently graded test pass rates across the 3 matched arms:
    * **Draft-Only:** Fixed single-attempt allowance (20.0% resolution across multi-domain strata).
    * **Self-Revision:** Equal-budget generic retry without external feedback (20.0%).
    * **Verifier-Guided:** Equal-budget independent reviewer evaluation with structured findings (20.0%).
  * **Subplot (b) Causal Contrasts:** Illustrates the incremental causal gain of verifier feedback over generic retry ($\Delta = +0.00\%$) and the zero-regression boundary across matched inference limits.
* **Primary Paper Role:** Primary causal identification figure for **Paper 2 (Causal Verifier Attribution)**.
* **Data Source:** [`artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json`](../artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json).

---

### 5. [`fig_recovery_regressions.png`](fig_recovery_regressions.png)
* **Title:** Revision Dynamics: Autonomous Recoveries vs. Regressions
* **Dimensions:** 1950 × 1260 px (300 DPI)
* **What it Illustrates:**
  * Compares task state transitions between Draft and Revision phases across all three experimental arms.
  * Confirms an unblemished **0.0% regression rate** (zero instances where initially passing code was broken by revision or verifier feedback).
* **Primary Paper Role:** Safety and stability analysis for **Paper 2**.
* **Data Source:** [`artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json`](../artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json).

---

## Deterministic Regeneration

All figures in this folder can be regenerated deterministically from raw data using:

```bash
# Regenerate Figures 1, 2, and 3
python replication/scripts/reproduce_all.py

# Regenerate Figures 4 and 5
python scripts/generate_causal_verifier_figures.py artifacts/causal_verifier_study_20261019_011333/causal_verifier_report.json "output image"
```
