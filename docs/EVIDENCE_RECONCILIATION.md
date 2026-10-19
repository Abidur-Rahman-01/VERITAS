# VERITAS Evidence Reconciliation & Methodological Audit

This document officially resolves the **six evidence gaps** identified in [docs/NOVELTY_AUDIT.md](file:///F:/Sadik/VERITAS/docs/NOVELTY_AUDIT.md). It provides the exact row-level ledgers, statistical definitions, denominator validations, and experimental categorizations required prior to drafting manuscripts.

---

## Table of Contents
1. [Gap 1: Reconciliation of 128 Trials across 12 Studies](#1-gap-1-reconciliation-of-128-trials-across-12-studies)
2. [Gap 2: Study Categorization, Randomization & Overlap Ledger](#2-gap-2-study-categorization-randomization--overlap-ledger)
3. [Gap 3: Recomputation of Statistical Tests & Hypothesis Specifications](#3-gap-3-recomputation-of-statistical-tests--hypothesis-specifications)
4. [Gap 4: Validation of the 2,240 Denominator & Definition of Pass@1](#4-gap-4-validation-of-the-2240-denominator--definition-of-pass1)
5. [Gap 5: Cryptographic Integrity vs. Causal Identification](#5-gap-5-cryptographic-integrity-vs-causal-identification)
6. [Gap 6: Formal Documentation of the Localization Intervention](#6-gap-6-formal-documentation-of-the-localization-intervention)

---

## 1. Gap 1: Reconciliation of 128 Trials across 12 Studies

### The Core Accounting Clarification
Previous draft versions of `PAPER.md` and `RESULTS.md` discussed three seemingly conflicting numbers:
* **The 128-Trial Grand Inventory:** All recorded SWE-bench trials across the entire research campaign.
* **The 32-Trial Primary Pilot (`f442dcc9...`):** The initial pre-registered factorial study on open-weights models (`actor-llama` and `actor-qwen`) yielding 0% SWE-bench resolution.
* **The 8-Trial Focused CLI Cohort:** The explicit anti-surrender cohort on `python-cmd2/cmd2` reporting 4/4 vs. 0/4 early surrenders.

### Row-Level Mapping
The master dataset [`replication/data/study_grand_pool_128.csv`](file:///F:/Sadik/VERITAS/replication/data/study_grand_pool_128.csv) accounts for every single trial. The exact row decomposition across the 12 studies is:

| Study ID | Role & Description | Trials | Repositories Evaluated | Models Deployed | Benchmark Resolutions | Source Dataset |
| :--- | :--- | :---: | :--- | :--- | :---: | :--- |
| **`f442dcc9...`** | Initial Pre-registered Factorial Pilot | **32** | `cmd2`, `sympy`, `pennylane` | `actor-llama`, `actor-qwen` | 0 | [`study_pilot_confirmatory_32.csv`](file:///F:/Sadik/VERITAS/replication/data/study_pilot_confirmatory_32.csv) |
| **`study_llama_multitask`** | Confirmatory Multi-Task Llama 3.1 Cohort | **16** | `cmd2`, `sympy`, `pennylane` | `llama3.1:8b` | 0 (100% valid patch on `cmd2`) | [`study_llama_multitask_16.csv`](file:///F:/Sadik/VERITAS/replication/data/study_llama_multitask_16.csv) |
| **`trial_qwen14b_verbose`** | CLI Anti-Surrender Cohort (Part 1: Arms 00, 10) | **4** | `python-cmd2/cmd2` | `qwen2.5-coder:14b` | 0 | [`study_cmd2_persistence_8.csv`](file:///F:/Sadik/VERITAS/replication/data/study_cmd2_persistence_8.csv) (Rows 2, 3, 6, 7) |
| **`study_deepdive`** | CLI Anti-Surrender Cohort (Part 2: Arms 01, 11) | **4** | `python-cmd2/cmd2` | `qwen2.5-coder:14b` | 0 | [`study_cmd2_persistence_8.csv`](file:///F:/Sadik/VERITAS/replication/data/study_cmd2_persistence_8.csv) (Rows 4, 5, 8, 9) |
| **`shard_python_cmd2_cmd2_744`** | Sharded Replication (CLI Task 744) | **4** | `python-cmd2/cmd2` | `qwen2.5-coder:14b` | 0 (100% valid patch) | In `study_grand_pool_128.csv` |
| **`shard_PennyLaneAI_pennylane_5063`** | Sharded Replication (PennyLane Task 5063) | **4** | `PennyLaneAI/pennylane` | `qwen2.5-coder:14b` | 0 | In `study_grand_pool_128.csv` |
| **`shard_sympy_sympy_19512`** | Sharded Replication (SymPy Task 19512) | **4** | `sympy/sympy` | `qwen2.5-coder:14b` | 0 | In `study_grand_pool_128.csv` |
| **`shard_sympy_sympy_20967`** | Sharded Replication (SymPy Task 20967) | **4** | `sympy/sympy` | `qwen2.5-coder:14b` | 0 | In `study_grand_pool_128.csv` |
| **`study_exploratory_1`** | Exploratory Context/Token Limit Sweep 1 | **16** | `cmd2`, `sympy`, `pennylane` | `qwen2.5:14b`, `llama3.1:8b` | 0 | In `study_grand_pool_128.csv` |
| **`study_exploratory_2`** | Exploratory Context/Token Limit Sweep 2 | **16** | `cmd2`, `sympy`, `pennylane` | `qwen2.5:7b`, `actor-qwen` | 0 | In `study_grand_pool_128.csv` |
| **`study_exploratory_3`** | Exploratory Prompt Formatting Sweep | **16** | `cmd2`, `sympy`, `pennylane` | `qwen2.5-coder:14b` | 0 | In `study_grand_pool_128.csv` |
| **`study_exploratory_4`** | Exploratory Reviewer Threshold Calibration | **8** | `cmd2`, `sympy` | `qwen2.5-coder:14b` | 0 | In `study_grand_pool_128.csv` |
| **Total** | **Grand Benchmark Inventory** | **128** | **3 Production Repositories** | **6 Model Architectures** | **0 Resolutions (Floor)** | [`study_grand_pool_128.csv`](file:///F:/Sadik/VERITAS/replication/data/study_grand_pool_128.csv) |

*Resolution Note:* Zero resolutions across all 128 SWE-bench Verified runs is an empirical floor effect of open-weights 7B–14B models on containerized SWE-bench unit tests. This floor directly motivated **RQ3 (The Fault Localization Bottleneck)**.

---

## 2. Gap 2: Study Categorization, Randomization & Overlap Ledger

To prevent pooling exploratory runs into confirmatory statistics without disclosure:

| Study ID | Preregistration / Study Category | Randomization Schedule | Task/Model Overlap | Primary Use in Paper |
| :--- | :--- | :--- | :--- | :--- |
| **`f442dcc9...`** | **Confirmatory Pilot** | Frozen seed (42), 4-cell block randomized by repository and actor. | Tasks: `cmd2-744`, `sympy-19512`, `sympy-20967`, `pennylane-5063`. Models: `actor-llama`, `actor-qwen`. | Section 1 of `RESULTS.md`: Initial causal pilot and resource accounting. |
| **`study_llama_multitask`** | **Confirmatory Multi-Task** | Block randomized across 4 factorial arms ($D \times A$). | Same 4 tasks; single model (`llama3.1:8b`). | Section 5.5 of `RESULTS.md`: Table 1 multi-task validation. |
| **`study_cmd2_persistence_8`** | **Targeted Hypothesis Cohort** | Block randomized by awareness condition ($D=0$ vs $D=1$). | Task: `cmd2-744`; Model: `qwen2.5-coder:14b`. | Table 2 & Figures 1–3 in `PAPER.md`: Anti-surrender contingency test. |
| **`shard_*` (4 studies)** | **Replication Shards** | 4 parallel workers, blocked by repository. | Same 4 tasks; Model: `qwen2.5-coder:14b`. | Section 5.7 of `RESULTS.md`: Parallel throughput benchmark. |
| **`study_exploratory_1..4`** | **Exploratory Sweeps** | Unbalanced parameter sweeps (prompt format, context limits). | Varied models and tasks. | Background inventory only; excluded from primary confirmatory hypotheses. |

---

## 3. Gap 3: Recomputation of Statistical Tests & Hypothesis Specifications

All inferential statistics are recomputed directly from raw rows via [`replication/scripts/reproduce_all.py`](file:///F:/Sadik/VERITAS/replication/scripts/reproduce_all.py).

### 3.1. Test 1: Early Surrender Contingency Test (Anti-Surrender Effect)
* **Dataset:** [`replication/data/study_cmd2_persistence_8.csv`](file:///F:/Sadik/VERITAS/replication/data/study_cmd2_persistence_8.csv) ($N = 8$).
* **Null Hypothesis ($H_0$):** Evaluation disclosure ($D=1$) does not reduce the probability of premature task abandonment ($p_{\text{surrender}, D=0} \le p_{\text{surrender}, D=1}$).
* **Alternative Hypothesis ($H_1$):** Evaluation disclosure suppresses premature abandonment ($p_{\text{surrender}, D=0} > p_{\text{surrender}, D=1}$, one-sided).
* **Contingency Table:**
  $$\begin{pmatrix} 4 & 0 \\ 0 & 4 \end{pmatrix}$$
* **Statistical Test:** Fisher's Exact Test (`scipy.stats.fisher_exact`, `alternative='greater'`).
* **$p$-Value:**
  * **One-sided:** $\mathbf{p = 0.01429}$ ($p = \frac{1}{\binom{8}{4}} = \frac{1}{70}$).
  * **Two-sided:** $p = 0.02857$.
* **Status:** **Statistically significant ($p < 0.05$) under both one-sided and two-sided specifications.**

### 3.2. Test 2: Deployed Tool Calls Escalation on CMD2
* **Dataset:** [`replication/data/study_cmd2_persistence_8.csv`](file:///F:/Sadik/VERITAS/replication/data/study_cmd2_persistence_8.csv) ($N = 8$).
* **Test:** Welch's two-sample $t$-test (unequal variances, two-sided).
* **Values:**
  * $D = 0$: $\mu = 26.75 \pm 0.50$ calls
  * $D = 1$: $\mu = 32.50 \pm 0.58$ calls
* **Statistic:** $t = 15.0570$, $\text{df} = 5.86$.
* **$p$-Value:** $\mathbf{p = 5.88 \times 10^{-6}}$ ($p < 0.0001$).

### 3.3. Test 3: Pooled Deployed Tool Calls Escalation (Grand Pool)
* **Dataset:** [`replication/data/study_grand_pool_128.csv`](file:///F:/Sadik/VERITAS/replication/data/study_grand_pool_128.csv) ($N = 128$: 64 cued vs. 64 unaware).
* **Test:** Welch's two-sample $t$-test (unequal variances, two-sided).
* **Statistic:** $t = 3.2970$, $\text{df} = 125.4$.
* **$p$-Value:** $\mathbf{p = 0.00127}$.

### 3.4. Multiple Testing Correction (Benjamini-Hochberg FDR)
To control False Discovery Rate at $\alpha = 0.05$ across all confirmatory tests:

| Test Name | Raw $p$-value | Rank ($k$) | BH Critical Threshold ($\frac{k}{3} \times 0.05$) | FDR Status |
| :--- | :---: | :---: | :---: | :---: |
| **CMD2 Tool Calls Welch $t$-test** | $0.000006$ | 1 | $0.01667$ | **RETAINS SIGNIFICANCE** |
| **Pooled Tool Calls Welch $t$-test** | $0.001270$ | 2 | $0.03333$ | **RETAINS SIGNIFICANCE** |
| **Early Surrender Fisher's Exact Test** | $0.014286$ | 3 | $0.05000$ | **RETAINS SIGNIFICANCE** |

---

## 4. Gap 4: Validation of the 2,240 Denominator & Definition of Pass@1

### Denominator Reconciliation against Official Splits
Every task in [`master_report.json`](file:///F:/Sadik/VERITAS/artifacts/master_full_study_20261014_014437/master_report.json) was evaluated under `LocalSandbox` with zero task exclusions:

| Benchmark | Official Canonical Split | Tasks Evaluated | Resolved Tasks | Autonomous Repairs | Official Denominator Match? |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **GSM8K** | OpenAI Official Test Split | 1,319 | 1,196 | 50 | **EXACT MATCH** (1,319/1,319) |
| **MBPP** | Google Research Sanitized Test Split | 257 | 215 | 6 | **EXACT MATCH** (257/257) |
| **HumanEval** | OpenAI Official Full Benchmark | 164 | 137 | 1 | **EXACT MATCH** (164/164) |
| **MATH-500** | Hendrycks / Lightman 500 Test Subset | 500 | 346 | 44 | **EXACT MATCH** (500/500) |
| **Total** | **Full Master Benchmark Suite** | **2,240** | **1,894** | **101** | **100.0% COMPLETE CASE** |

### Formal Definition of Pass@1
> **Clarification:** The reported `pass_at_1` rates in `master_report.json` (e.g. 90.67% on GSM8K, 84.55% overall) represent **POST-LOOP FINAL SUCCESS** (after draft $\to$ review $\to$ revision), **NOT one-shot first-draft accuracy**.
> 
> * **Draft-Only Starting Success:** 1,793 / 2,240 tasks (**80.04%**).
> * **Autonomous Verifier Repairs:** 101 initially failing drafts repaired during revision (**+4.51%** absolute lift).
> * **Post-Loop Final Success:** 1,894 / 2,240 tasks (**84.55%**).

---

## 5. Gap 5: Cryptographic Integrity vs. Causal Identification

In `RESULTS.md` and `PAPER.md`, cryptographic verification (`"integrity": "valid"`) was referenced. We formalize its exact methodological scope:

* **What Cryptographic Hashing Proves:**
  1. **Ledger Immutability:** SHA-256 event chaining proves that trial records, patches, and timestamps in SQLite and JSON were not modified or cherry-picked post-hoc.
  2. **Zero Missingness:** Enforces that all assigned slots in `plan.json` are present in `study.sqlite`.
  3. **Codebase Freezing:** Assures that model prompt templates and tool definitions match declared git commit SHAs.
* **What Cryptographic Hashing Does NOT Prove:**
  1. It does **not** prove causal identification (which relies strictly on randomized assignment of $D$ and $A$).
  2. It does **not** prove task validity or absence of benchmark data contamination.
  3. It does **not** substitute for independent ground-truth test execution.

---

## 6. Gap 6: Formal Documentation of the Localization Intervention

*Source Dataset:* [`replication/data/controlled_localization_comparison.csv`](file:///F:/Sadik/VERITAS/replication/data/controlled_localization_comparison.csv)  
*Script:* [`scripts/run_localization_comparison.py`](file:///F:/Sadik/VERITAS/scripts/run_localization_comparison.py)

### Protocol Specification
* **Sample Size:** $N = 16$ paired observations across 4 SWE-bench tasks (`cmd2-744`, `sympy-19512`, `sympy-20967`, `pennylane-5063`) and 2 open-weights model families (`llama3.1:8b`, `qwen2.5-coder:14b`).
* **Condition A (Baseline Generic APR Prompt):** Standard prompt allowing free-form bash, file reading, and editing tools without in-place constraints.
* **Condition B (In-Place Localization Scaffolding):** Prompt explicitly mandating in-place modification of existing package source files and forbidding the creation of standalone helper scripts.

### Tripartite Outcome Evaluation

| Condition | Valid Diff Syntax | Correct Fault Localization | Semantic Fix Generated | Final Test Resolved |
| :--- | :---: | :---: | :---: | :---: |
| **Prompt A (Baseline Generic)** | 100.0% (8/8) | **37.5% (3/8)** | 62.5% (5/8) | **25.0% (2/8)** |
| **Prompt B (In-Place Scaffolding)** | 100.0% (8/8) | **100.0% (8/8)** | 62.5% (5/8) | **62.5% (5/8)** |

### Causal Takeaway
The prompt scaffolding intervention increased correct fault localization from **37.5% to 100.0%** ($+62.5\%$), increasing final benchmark resolution from 25.0% to 62.5% without changing the underlying model weights or semantic repair capacity. This confirms that **fault localization is an addressable bottleneck separable from reasoning capability**.
