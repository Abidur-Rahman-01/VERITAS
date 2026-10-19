# VERITAS Action-Time Verification Status & Experimental Manifest

**Status:** Official Methodological Reconciliation  
**Target:** Package Audit & TSE Research Question Resolution  
**Date:** October 20, 2026  

---

## 1. Package Audit Findings & Design Reconciliation

An audit of the 2,405 SQLite event databases across the VERITAS historical archive confirmed:
1. **Macro-Level Draft $\to$ Revision Loops:** The 2,240-task benchmark suite ([`artifacts/master_full_study_20261014_014437/`](file:///F:/Sadik/VERITAS/artifacts/master_full_study_20261014_014437/)) and the 30-trial causal verifier study ([`artifacts/causal_verifier_study_20261019_011333/`](file:///F:/Sadik/VERITAS/artifacts/causal_verifier_study_20261019_011333/)) evaluated a two-phase workflow where verification feedback is delivered only at the boundary of an initial draft patch before allowing a revision attempt.
2. **Intermediate Action Decisions:** During intermediate tool calls (`read_file`, `edit_file`, `python`), the action controller recorded `decision="skip"` and `verification=null`, because the action-level policy was unengaged.
3. **Audit Consequence:** The historical records test **post-draft patch critique** and **evaluation awareness ($D \times A$)**, but do not test **action-time (in-loop / per-step) verification gating**.

---

## 2. Reconciled 3-Arm Comparative Design

All three arms share identical search bounds, identical step limits, identical model architectures, and identical tool harnesses:

```
+-------------------------------------------------------------------------------------------------------+
|                                    RECONCILED 3-ARM EXPERIMENTAL MATRIX                               |
+--------------------------------+-------------------+-----------+----------------+---------------------+
| Experimental Arm               | Policy            | Step Cap  | Verifier Budget| Verifier Execution  |
+--------------------------------+-------------------+-----------+----------------+---------------------+
| Arm 0: Unverified Baseline     | policy: "never"   | 30 steps  | 0.0 credits    | Zero verifications  |
| Arm 1: Random Control          | policy: "random"  | 30 steps  | 0.4 credits    | p=0.33 per mutation |
| Arm 2: Selective Quality Gate  | policy: "error_impact"| 30 steps| 0.4 credits  | Risk-calibrated gate|
+--------------------------------+-------------------+-----------+----------------+---------------------+
```

* **Actor Model:** `qwen2.5-coder:7b` (Ollama, `temperature: 0.0`, greedy decoding, context: 2,048).
* **Verifier Model:** `llama3.1:8b` (Ollama, `temperature: 0.0`, context: 768).
* **Step Limit:** Fixed at **30 steps** across all three arms to eliminate search-depth confounding.
* **Configs:**
  * Arm 0: [`configs/action_time_arm0_unverified.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm0_unverified.yaml)
  * Arm 1: [`configs/action_time_arm1_random.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm1_random.yaml)
  * Arm 2: [`configs/action_time_arm2_action_time_gate.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm2_action_time_gate.yaml)

---

## 3. Pinned 20-Task Repository-Repair Cohort

The frozen task manifest is defined in [`configs/action_time_task_manifest.json`](file:///F:/Sadik/VERITAS/configs/action_time_task_manifest.json), comprising 20 distinct multi-file repository maintenance and repair tasks:
* **`python-cmd2/cmd2` (5 tasks):** Tasks 744, 755, 760, 770, 780.
* **`sympy/sympy` (5 tasks):** Tasks 19512, 20967, 18033, 18189, 18621.
* **`PennyLaneAI/pennylane` (5 tasks):** Tasks 5063, 4376, 4402, 4488, 4512.
* **Multi-file Python packages (5 tasks):** `repo_env_var_interpolator`, `repo_json_schema_coercer`, `repo_csv_schema_validator`, `repo_cli_parser_engine`, `repo_sql_query_builder`.

---

## 4. Runtime Logging Fix Verified

In [`src/veritas/runtime.py`](file:///F:/Sadik/VERITAS/src/veritas/runtime.py), when a verifier decision results in `rejected = True`:
```python
if rejected:
    record.blocked = True
    record.executed = False
    record.block_reason = record.verification.reason if record.verification else "Rejected by verifier"
    before_restore = time.monotonic()
    if checkpoint:
        record.restored_hash = checkpoint.restore()
```
This ensures that `events.sqlite` explicitly records `blocked = 1` and `executed = 0` whenever an action is blocked by the verifier gate.

---

## 5. Execution Engine

The dedicated executable runner [`scripts/run_action_time_tse_experiment.py`](file:///F:/Sadik/VERITAS/scripts/run_action_time_tse_experiment.py) runs the arms and records all trials to `artifacts/action_time_study/`.
