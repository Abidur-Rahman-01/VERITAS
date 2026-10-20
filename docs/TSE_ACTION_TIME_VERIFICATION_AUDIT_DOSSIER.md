# Formal Audit Dossier: Action-Time Runtime Verification in Autonomous Coding Agents

**Study Target:** IEEE Transactions on Software Engineering (TSE) Confirmatory Evidence Package  
**Repository & Replication Package:** [https://github.com/Abidur-Rahman-01/VERITAS](https://github.com/Abidur-Rahman-01/VERITAS)  
**Primary Commit:** [`1ed72ab`](https://github.com/Abidur-Rahman-01/VERITAS/commit/1ed72ab)  
**Date:** October 20, 2026  

---

## 1. Response to Methodological Review: The Five Core Evidence Criteria

This dossier addresses the five methodological criteria required to establish empirical evidence for **Action-Time Runtime Verification** (intercepting candidate coding agent actions *before* sandbox execution):

```
+-------------------------------------------------------------------------------------------------------------+
|                                    FIVE PILLARS OF TSE EMPIRICAL EVIDENCE                                   |
+-------------------------------------------------------------------------------------------------------------+
|  1. Frozen Protocol    | Pinned 60-task cohort, qwen2.5-coder:14b actor, llama3.1:8b verifier, 30 steps cap |
|  2. Unified Runner     | Single runner executing Arm 0 (Unverified), Arm 1 (Random), Arm 2 (Selective)       |
|  3. Run Artifacts      | 180 independent SQLite databases, SHA-256 tree state hashes, pre/post snapshots     |
|  4. Independent Grades | Raw containerized pytest logs (grade.log), objective exit codes, blocked audit flags|
|  5. Statistical Report | Clopper-Pearson 95% CIs, causal contrasts (Delta), token & latency economics        |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 2. Pillar 1: One Frozen Experiment Definition

| Experimental Parameter | Standardized Specification | Location in Replication Package |
| :--- | :--- | :--- |
| **Benchmark Cohort** | 60 unique multi-file Python repository repair tasks | [`scripts/tse_60_task_fixtures.py`](file:///F:/Sadik/VERITAS/scripts/tse_60_task_fixtures.py) |
| **Repository Domains** | `sympy` (10), `cmd2` (10), `pennylane` (10), `production_systems` (14), `repo_maintenance` (7), `core_algorithms` (4), `coding_calibration` (5) | Table 2 in [`docs/TSE_180_TRIAL_QWEN_CODER_14B.md`](file:///F:/Sadik/VERITAS/docs/TSE_180_TRIAL_QWEN_CODER_14B.md) |
| **Actor Model** | `qwen2.5-coder:14b` (greedy $T=0.0$, 2,048 max prediction tokens) | [`configs/action_time_arm0_unverified.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm0_unverified.yaml) |
| **Verifier Model** | `llama3.1:8b` (greedy $T=0.0$, 768 max predict tokens, frozen across all arms) | [`configs/action_time_arm1_random.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm1_random.yaml), [`configs/action_time_arm2_action_time_gate.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm2_action_time_gate.yaml) |
| **Search Allowance** | Standardized to exactly **30 steps** across all arms | `max_steps: 30` in all arm configs |
| **Action Eligibility** | Read-only operations (`read_file`, `list_files`) marked `decision="skip"` ($\mu = 0.1$); Workspace mutations (`edit_file`, `write_file`, `bash`) scored ($\mu \in [0.5, 0.9]$) | Section 3.1 in [`PAPER_TSE.md`](file:///F:/Sadik/VERITAS/PAPER_TSE.md) |
| **Failure Handling** | Atomic SHA-256 tree state rollback to `state_before`, `blocked=True`, `executed=False`, diagnostic critique injected into context | [`src/veritas/runtime.py`](file:///F:/Sadik/VERITAS/src/veritas/runtime.py) |
| **Verifier Budget** | $B = 0.4$ credits per task (20 verifier calls at 0.02 credits/check) | `verification_budget: 0.4` |

---

## 3. Pillar 2: The Executable Runner

The unified multi-model runner is implemented in [`scripts/run_5_coder_models_180_trials.py`](file:///F:/Sadik/VERITAS/scripts/run_5_coder_models_180_trials.py) and [`scripts/run_action_time_tse_experiment.py`](file:///F:/Sadik/VERITAS/scripts/run_action_time_tse_experiment.py):
* **Workspace Isolation:** Every trial initializes an unmodified workspace copy from `baseline/` before policy execution.
* **Comparative Arm Execution:**
  * **Arm 0 (`arm0_unverified`):** `policy: never`, zero verifier calls, 30 steps.
  * **Arm 1 (`arm1_random`):** `policy: random`, stochastic check with $p = 0.33$ under budget $B = 0.4$.
  * **Arm 2 (`arm2_selective`):** `policy: error_impact`, risk scoring $S = p_{\text{err}} \cdot \mu_{\text{action}} \ge 0.25$ under budget $B = 0.4$.

---

## 4. Pillar 3: Completed Run Artifacts (Model 1: `qwen2.5-coder:14b`)

All 180 trial directories are fully materialized on disk under [`artifacts/action_time_study_qwen2.5_coder_14b/`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_14b) and tracked in GitHub:
* **180 Transactional SQLite Event Databases (`events.sqlite`):** Recording every proposed action, verifier decision (`verify`), verifier verdict (`PASS`/`FAIL`), rollback execution (`blocked=True`), and SHA-256 tree state hashes (`state_before`, `state_after`).
* **180 Raw Containerized Pytest Logs (`grade.log`):** Independent test execution output and returncode.
* **180 Telemetry Metrics (`summary.json`):** Per-trial latency, verified checks, blocked actions, and policy token usage.
* **180 Workspace Snapshots:** Both initial `baseline/` and final modified `workspace/`.

---

## 5. Pillar 4: Independent Outcomes & Objective Safety Labeling

* **Final Resolution Outcomes:** Evaluated exclusively via independent pytest execution inside the containerized sandbox (`grade_proc.returncode == 0`).
* **Blocked Actions & Interceptions:** 
  * Total verified checks across 180 trials: **215 verifications**.
  * Total blocked faulty actions across 180 trials: **94 blocked actions** with automated workspace rollback.
* **False Block & Regression Analysis:**
  * In `python-cmd2/cmd2` Task 37 (`swe_cmd2_810`), budget-matched random verification falsely blocked valid chained alias resolutions, causing the task to fail (62.14s). The selective gate correctly classified low risk, avoided false alarm blocking, and cleanly resolved the defect in **6.66s**.

---

## 6. Pillar 5: Statistical Analysis & Findings (N = 180 Trials)

```
+------------------------------------------------------------------------------------------------------------------------------------------------+
| TABLE 1: AUDITED COMPARATIVE BENCHMARK MATRIX (60 UNIQUE TASKS X 3 ARMS = 180 TRIALS, QWEN2.5-CODER:14B + LLAMA3.1:8B)                        |
+----------------------+--------+----------+------------------+-------------------+------------------+-----------------+--------------+----------+
| Experimental Arm     | Trials | Resolved | Success Rate (%) | 95% Clopper-Pear. | Verified Actions | Blocked Actions | Mean Latency | Tokens   |
+----------------------+--------+----------+------------------+-------------------+------------------+-----------------+--------------+----------+
| Arm 0: Unverified    |   60   |    48    |     80.00%       |  [67.67%, 89.22%] |        0         |        1        |   19.71 s    | 2,687,119|
| Arm 1: Random Check  |   60   |    48    |     80.00%       |  [67.67%, 89.22%] |       136        |       47        |   32.47 s    | 1,473,651|
| Arm 2: Selective Gate|   60   |    48    |     80.00%       |  [67.67%, 89.22%] |        79        |       46        | **22.49 s**  |**1,258,362|
+----------------------+--------+----------+------------------+-------------------+------------------+-----------------+--------------+----------+
```

### Core Empirical Conclusions
1. **53.2% Net Policy Token Reduction:** Unverified trajectories spiraled into long, compounding repair loops consuming 2.68M tokens. Selective gating cut consumption to 1.25M tokens (saving **1,428,757 tokens**).
2. **Latency Efficiency:** Selective verification delivered a **30.7% speedup** over random verification (22.49s vs. 32.47s), avoiding unnecessary verifier overhead.
3. **Domain Resilience:** Achieved **100.0% resolution** in symbolic mathematics (`sympy`: 10/10) and quantum circuits (`pennylane`: 10/10), and **92.9% resolution** in production systems (13/14).

---

## 7. Multi-Model Replication & Generalization Pipeline

The experiment runner is actively executing the identical 180-trial protocol across the 4 remaining coder models:
* **Model 2:** `deepseek-coder-v2:16b` (In progress: 54 trials audited $\to$ [`docs/TSE_180_TRIAL_DEEPSEEK_CODER_16B.md`](file:///F:/Sadik/VERITAS/docs/TSE_180_TRIAL_DEEPSEEK_CODER_16B.md))
* **Model 3:** `granite-code:20b` (Queued $\to$ [`docs/TSE_180_TRIAL_GRANITE_CODE_20B.md`](file:///F:/Sadik/VERITAS/docs/TSE_180_TRIAL_GRANITE_CODE_20B.md))
* **Model 4:** `starcoder2:15b` (Queued $\to$ [`docs/TSE_180_TRIAL_STARCODER2_15B.md`](file:///F:/Sadik/VERITAS/docs/TSE_180_TRIAL_STARCODER2_15B.md))
* **Model 5:** `qwen2.5-coder:30b` (Queued $\to$ [`docs/TSE_180_TRIAL_QWEN_CODER_30B.md`](file:///F:/Sadik/VERITAS/docs/TSE_180_TRIAL_QWEN_CODER_30B.md))
