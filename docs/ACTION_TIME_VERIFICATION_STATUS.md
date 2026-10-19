# VERITAS Action-Time Verification Status & Experimental Manifest

**Status:** Official Methodological Clarification  
**Target:** Package Audit & TSE Research Question Resolution  
**Date:** October 20, 2026  

---

## 1. Package Audit Findings & Reconciliation

An audit of the 2,405 SQLite event databases across the VERITAS study archive confirmed:
1. **Macro-Level Draft $\to$ Revision Loops:** The 2,240-task benchmark suite ([`artifacts/master_full_study_20261014_014437/`](file:///F:/Sadik/VERITAS/artifacts/master_full_study_20261014_014437/)) and the 30-trial causal verifier study ([`artifacts/causal_verifier_study_20261019_011333/`](file:///F:/Sadik/VERITAS/artifacts/causal_verifier_study_20261019_011333/)) evaluated a two-phase workflow where verification feedback is delivered at the boundary of an initial draft patch before allowing a revision attempt.
2. **Intermediate Action Decisions:** During intermediate tool calls (`read_file`, `edit_file`, `python`), the action controller recorded `decision="skip"` and `verification=null`, because the action-level policy was unengaged.
3. **Audit Consequence:** The available run records test **post-draft patch critique** and **evaluation awareness ($D \times A$)**, but do not test **action-time (in-loop / per-step) verification gating**.

---

## 2. Action-Time Verification Protocol (The TSE Intervention)

To directly test action-time verification, the repository provides the frozen task manifest and 3-arm causal configurations:

### A. Experimental Arms
* **Arm 0: Unverified Baseline:** [`configs/action_time_arm0_unverified.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm0_unverified.yaml) (`policy: never`, 1 fixed allowance).
* **Arm 1: Equal-Budget Generic Self-Retry:** [`configs/action_time_arm1_generic_retry.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm1_generic_retry.yaml) (`policy: never`, matched total token/step cap, generic second chance without verifier findings).
* **Arm 2: Action-Time Verification Gate:** [`configs/action_time_arm2_action_time_gate.yaml`](file:///F:/Sadik/VERITAS/configs/action_time_arm2_action_time_gate.yaml) (`policy: always` or `rcvov`, verifier scores actions before execution, logs `decision="verify"`, blocks non-PASS actions).

### B. Frozen Task Manifest
Defined in [`configs/action_time_task_manifest.json`](file:///F:/Sadik/VERITAS/configs/action_time_task_manifest.json), spanning repository repair (`cmd2`, `sympy`, `pennylane`), function synthesis (`HumanEval`), scripting (`MBPP`), and mathematical reasoning (`GSM8K`).

---

## 3. Current Completed Experiments Included in this Package

The study package (`VERITAS_study_package.zip`) includes:
1. **The 30-Trial Causal Verifier Study (October 19, 2026):**  
   [`artifacts/causal_verifier_study_20261019_011333/`](file:///F:/Sadik/VERITAS/artifacts/causal_verifier_study_20261019_011333/)  
   Compares `draft_only` vs `self_revision` vs `verifier_guided` across 5 stratified domains, with all raw event databases, patches, and reports.
2. **The 2,240-Task Multi-Benchmark Suite:**  
   [`artifacts/master_full_study_20261014_014437/`](file:///F:/Sadik/VERITAS/artifacts/master_full_study_20261014_014437/)  
   Census of 2,240 tasks recording draft success (86.38%), repairs (+4.51%), and regressions (-6.34%).
3. **The 128-Trial SWE-bench Verified Inventory:**  
   [`replication/data/study_grand_pool_128.csv`](file:///F:/Sadik/VERITAS/replication/data/study_grand_pool_128.csv)  
   Evaluates evaluation awareness disclosure ($D \in \{0, 1\}$) and post-draft reviews ($A \in \{0, 1\}$).
