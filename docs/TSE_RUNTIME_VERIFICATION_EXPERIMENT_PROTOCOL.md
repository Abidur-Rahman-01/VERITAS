# IEEE TSE Experimental Protocol: Runtime Verification During Autonomous Coding Agent Actions

**Document Title:** Protocol & Evidence Specification for In-Loop Action Verification  
**Target Venue:** IEEE Transactions on Software Engineering (TSE)  
**System:** VERITAS Runtime Controller & Action-Time Verification Engine  
**Date:** October 20, 2026  

---

## 1. Executive Summary & Audit Response

The package audit established that historical VERITAS datasets (`master_full_study_20261014_014437` and `f442dcc9...`) tested macro-level patch reviews (Draft $\to$ Review $\to$ Revision) and evaluation awareness ($D \times A$). In all 2,405 historical SQLite databases, action-level rows recorded `decision="skip"` and `verification=null`.

This document specifies the **definitive, auditable empirical experiment** required to answer the TSE research question:  
> **"Does selective, in-loop runtime verification of proposed agent actions improve independently graded task success over unverified execution and budget-matched random verification, and at what cost?"**

```
+----------------------------------------------------------------------------------------------------+
|                             ACTION-TIME RUNTIME VERIFICATION ARCHITECTURE                          |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|   Agent Proposes Action               Controller Policy Evaluation              Verifier Decision  |
|  [Tool: edit_file/bash] ----> [Risk Score: p_err * impact / cost] ----> { decision = "verify" }   |
|                                                                                |                   |
|                                                                                v                   |
|                                                                     [Pre-Execution Verifier]       |
|                                                                                |                   |
|                        +-----------------------+-------------------------------+                   |
|                        |                       |                               |                   |
|                     [PASS]                  [FAIL]                      [ERROR / TIMEOUT]          |
|                        |                       |                               |                   |
|                        v                       v                               v                   |
|                Execute Action          Block Action (Rollback)          Fallback / Budget Cost     |
|             (executed = True)         (executed = False, blocked = True)                           |
|                        |                       |                               |                   |
|                        +-----------------------+-------------------------------+                   |
|                                                |                                                   |
|                                                v                                                   |
|                                    Log to SQLite (EventStore)                                      |
|                               (action, decision, verdict, states)                                  |
|                                                |                                                   |
|                                                v                                                   |
|                                    Independent Grading (pytest)                                    |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Requirement 1: Clear Treatment Definition

### A. Target Action Eligibility (Which Actions Are Checked)
Actions proposed by the agent are categorized by mutation risk in [`src/veritas/controller.py`](file:///F:/Sadik/VERITAS/src/veritas/controller.py):
* **Verified Actions (Candidate Mutations):**
  * `edit_file` / `write_file` (in-tree codebase modifications)
  * `bash` / shell commands with file or environment mutations (`env_mutation`, `db_write`)
  * `final_answer` (terminal task submission)
* **Exempt Actions (Read-Only Diagnostics):**
  * `read_file`, `directory_list`, `grep`, `file_search` (zero workspace mutation risk; always `decision="skip"` to conserve compute).

### B. What the Verifier Does
Before the sandbox executes the proposed action:
1. An isolated workspace checkpoint is created (`state_before = tree_hash(workspace)`).
2. The verifier (`llama3.1:8b` or static constraint checker) inspects the proposed diff/command against the issue statement, AST integrity, and syntax.
3. For code edits, candidate unit tests are dry-run in an isolated sub-container.

### C. State Machine & Verdict Handling

| Verdict | `decision` | `executed` | `blocked` | Action Taken | Agent Observation |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **`PASS`** | `"verify"` | `True` | `False` | Sandbox executes mutation; `state_after` recorded. | Standard tool execution output. |
| **`FAIL`** | `"verify"` | `False` | `True` | Workspace restored to `state_before` via checkpoint rollback. | Verifier critique delivered with replan directive. |
| **`ERROR`** | `"verify"` | `False` | `True` | Execution suppressed if uncalibrated; charged to budget. | Error notice; fallback contract invoked. |
| **`TIMEOUT`**| `"verify"` | `False` | `True` | Verifier killed at limit (e.g., 30s); logged as timeout. | Replan prompt: "Verifier timed out; refine proposal." |

---

## 3. Requirement 2: The Three-Arm Matched Experimental Design

To isolate whether selective quality-gating adds value beyond chance or extra compute, three matched arms run under identical conditions:

```
+-------------------------------------------------------------------------------------------+
|                                THREE-ARM COMPARATIVE MATRIX                               |
+-------------------+--------------------+------------------------+-------------------------+
| Condition         | Policy in Runtime  | Verification Budget    | Controller Decision     |
+-------------------+--------------------+------------------------+-------------------------+
| Arm 0: Unverified | policy: "never"    | Budget = 0.0 credits   | Always decision="skip"  |
| Arm 1: Random     | policy: "random"   | Budget = 0.4 credits   | rng.random() < p_check  |
| Arm 2: Selective  | policy: "rcvov"    | Budget = 0.4 credits   | Score(Risk) >= lambda   |
+-------------------+--------------------+------------------------+-------------------------+
```

1. **Arm 0 (Unverified Baseline Control):**
   * Config: [`configs/action_time_arm0_unverified.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm0_unverified.yaml)
   * The actor interacts with tools freely up to the step cap; zero verifier calls.
2. **Arm 1 (Random Verification at Equal Budget):**
   * Config: [`configs/action_time_arm1_random.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm1_random.yaml)
   * Proposed mutations are verified with probability $p = \text{budget} / (\text{expected mutations})$. Once the budget is spent, subsequent actions skip verification.
3. **Arm 2 (Selective Action-Time Verification Gate):**
   * Config: [`configs/action_time_arm2_action_time_gate.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm2_action_time_gate.yaml)
   * Controller calculates $RCVOV = \frac{\Delta}{\text{cost}}$, verifying only high-risk / high-yield actions. Non-PASS actions are blocked.

---

## 4. Requirement 3: Fixed Benchmark & Pinned Protocol

All runs use frozen manifests pinned prior to data collection:

* **Task Manifest:** [`configs/action_time_task_manifest.json`](file:///F:/Sadik/VERITAS/configs/action_time_task_manifest.json)
* **Model Versions:**
  * **Actor:** `qwen2.5-coder:7b` (Ollama, `temperature: 0.0`, greedy decoding, context: 4,096 tokens).
  * **Verifier:** `llama3.1:8b` (Ollama, `temperature: 0.0`, context: 2,048 tokens).
* **Limits:**
  * Maximum agent steps per task: **30 steps**.
  * Maximum replan attempts after verifier rejection: **3 replans**.
  * Total verifier credit budget per task: **0.4 credits** (20 verifier calls at 0.02 credits/call).
  * Step timeout: **60 seconds**; Verifier timeout: **30 seconds**.
* **Repository Commits Pinned:**
  * `python-cmd2/cmd2`: `b3e0dc92f7c0065098ffb41505c8793b8279ad91`
  * `sympy/sympy`: `c4240751f77d33b497b7cb3ff6f3cc979d36ffc1`
  * `PennyLaneAI/pennylane`: `a52e05a812df5dc87c4276189ef851a70ff614f1`

---

## 5. Requirement 4: Power Pilot $\to$ Confirmatory Sample Sizing

To prevent pseudoreplication and ensure formal statistical power:
1. **Pilot Phase ($N = 20$ tasks per arm):**
   * Execute 20 matched tasks across SWE, HumanEval, MBPP, and GSM8K.
   * Estimate:
     * Baseline resolution rate $P_0$ (expected 15–25% for 7B models on repo tasks).
     * Action-level mutation error rate $p_{\text{error}}$.
     * Inter-task variance and repository clustering coefficient (ICC).
2. **Confirmatory Power Calculation:**
   * Targeting $\Delta = +10\%$ absolute resolution gain at $\alpha = 0.05$ (two-sided) with power $1 - \beta = 0.80$.
   * Using clustered bootstrap power simulation in [`src/veritas/awareness_power.py`](file:///F:/Sadik/VERITAS/src/veritas/awareness_power.py).
3. **Task Independence Rule:** Each benchmark task ID represents exactly **one independent experimental block**. Repeated runs with different seeds on the same task are treated as repeated measures within-cluster, never as independent sample units.

---

## 6. Requirement 5: Action-Level SQLite Logging Schema

Every event is committed to `events.sqlite` via [`src/veritas/store.py`](file:///F:/Sadik/VERITAS/src/veritas/store.py) using the [`StepRecord`](file:///F:/Sadik/VERITAS/src/veritas/schema.py#L90-L140) schema:

```sql
-- Schema of every action-time record in events.sqlite:
SELECT 
    step_id,
    phase,
    json_extract(payload, '$.action.proposal.tool') AS proposed_tool,
    json_extract(payload, '$.action.proposal.args') AS proposed_args,
    decision,          -- 'verify', 'skip', or 'blocked'
    json_extract(payload, '$.verification.verdict') AS verifier_verdict,
    json_extract(payload, '$.verification.reason')  AS verifier_reason,
    executed,          -- 1 if executed, 0 if blocked
    blocked,           -- 1 if blocked by verifier
    state_before,      -- SHA-256 tree hash before action
    state_after,       -- SHA-256 tree hash after execution
    restored_hash,     -- SHA-256 tree hash after rollback (if blocked)
    budget_spent       -- Cumulative verifier credits spent
FROM events;
```

---

## 7. Requirement 6: Independent Outcome Grading & Classification Metrics

Final artifacts are graded through isolated container execution (`pytest`), never self-reported by the agent:

```
+----------------------------------------------------------------------------------------------------+
|                                    INDEPENDENT METRIC TAXONOMY                                     |
+------------------------------+------------------------------------+--------------------------------+
| Metric                       | Formula / Definition               | Objective                      |
+------------------------------+------------------------------------+--------------------------------+
| Task Resolution ($Y$)        | Ground-truth pytest suite passes   | Primary TSE success outcome    |
| Regression Prevention        | Initial Pass broken at final exit  | Measures safety retention      |
| True Harmful Blocked ($TP$)  | Flawed action blocked by verifier  | Harm prevented                 |
| False Alarm ($FP$)           | Benign action wrongly blocked      | False alarm cost               |
| Incomplete Runs              | Execution exceeded timeout/step cap| Operational reliability        |
+------------------------------+------------------------------------+--------------------------------+
```

---

## 8. Requirement 7: Cost & Statistical Analysis Plan

* **Primary Estimands:**
  * $\Delta_{\text{selective}} = Y_{\text{selective}} - Y_{\text{unverified}}$
  * $\Delta_{\text{policy\_advantage}} = Y_{\text{selective}} - Y_{\text{random}}$
* **Statistical Testing:**
  * Paired percentile bootstrap resampling (10,000 resamples), clustered by repository/domain.
  * Holm-Bonferroni correction for family-wise error rate across primary and secondary endpoints.
  * 95% Clopper-Pearson exact confidence intervals for binary success rates.
* **Compute Accounting:**
  * Total inference tokens: $\text{Tokens}_{\text{total}} = \text{Tokens}_{\text{actor}} + \text{Tokens}_{\text{verifier}}$.
  * Net compute cost per additional resolved task: $\frac{\text{Cost}_{\text{Arm 2}} - \text{Cost}_{\text{Arm 0}}}{N_{\text{resolved, Arm 2}} - N_{\text{resolved, Arm 0}}}$.

---

## 9. Requirement 8: Raw Evidence & Reproducibility Directory

When the runner completes, each task folder in `artifacts/action_time_study/` contains:
```text
artifacts/action_time_study/
├── arm0_unverified/
│   └── task_001_cmd2/
│       ├── events.sqlite       # Complete step-level event log (decision='skip')
│       ├── final.patch         # Final unverified patch
│       └── grade.log           # Independent pytest execution trace
├── arm1_random/
│   └── task_001_cmd2/
│       ├── events.sqlite       # Random decisions and rollbacks
│       └── grade.log
└── arm2_selective/
    └── task_001_cmd2/
        ├── events.sqlite       # Verifier decisions (decision='verify', verdicts)
        ├── final.patch
        └── grade.log
```

---

## 10. Executable Next Step

To execute the pilot study and generate the auditable action-time databases, run:
```powershell
uv run python scripts/run_action_time_tse_experiment.py --pilot --tasks 10
```
