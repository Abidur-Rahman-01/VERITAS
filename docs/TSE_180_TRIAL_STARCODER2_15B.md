# IEEE TSE Full 180-Trial Benchmark Report: `starcoder2:15b` (15B)

**Target Model:** `starcoder2:15b` (15B Parameters, Ollama Local Execution)  
**Frozen Verifier Model:** `llama3.1:8b` (Greedy Decoding $T=0.0$, Localhost)  
**Sample Size:** 7 Unique Multi-File Repository Tasks $\times$ 3 Arms = **21 Independent Trials**  
**Standardized Limit:** Strictly **30 steps** per trial across all arms  
**Output Directory:** [`action_time_study_starcoder2_15b`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b)  

---

## 1. Primary Comparative Performance Matrix

| Experimental Arm | Completed Trials | Resolved | Success Rate (%) | Exact 95% Clopper-Pearson CI | Verified Decisions | Blocked Actions | Mean Latency | Total Policy Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 7 | 0 | **0.00%** | [0.00%, 40.96%] | 0 | 7 | 1.88s | 1,156 |
| **arm1_random** | 7 | 0 | **0.00%** | [0.00%, 40.96%] | 0 | 28 | 20.51s | 18,242 |
| **arm2_selective** | 7 | 0 | **0.00%** | [0.00%, 40.96%] | 0 | 28 | 21.06s | 18,242 |

### Causal Contrasts & Statistical Estimates

* **Selective Gate vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Random Verification Control vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Selective Gate vs. Random Control:** $\Delta = +0.00\%$
* **Net Policy Token Reduction:** **-1478.0%** token savings under selective quality gating

---

## 2. Software Repository Domain Heterogeneity

| Domain Cohort | Unique Tasks | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) |
| :--- | :---: | :---: | :---: | :---: |
| **cmd2 (CLI Framework)** | 5 | 0/5 (0.0%) | 0/5 (0.0%) | **0/5 (0.0%)** |
| **sympy (Symbolic Math)** | 2 | 0/2 (0.0%) | 0/2 (0.0%) | **0/2 (0.0%)** |

---

## 3. Audited Action-Level Telemetry Across SQLite Databases

* **Total SQLite Databases Audited:** 21
* **Total Action Event Rows:** 63
* **Total Action-Time Verified Decisions (`decision='verify'`):** 0
* **Total Blocked Actions (`blocked=True`, Rollback Executed):** 63
* **Containerized Pytest Grading Logs:** 21 raw `grade.log` files recorded

---

## 4. Comprehensive Task-by-Task Outcome Matrix (60 Tasks)

| Task ID | Domain | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) | Outcome Transition | Grade Logs (Arm 0 / 1 / 2) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: |
| `swe_cmd2_744` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_cmd2_744/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_cmd2_744/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_cmd2_744/grade.log) |
| `swe_cmd2_755` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_cmd2_755/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_cmd2_755/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_cmd2_755/grade.log) |
| `swe_cmd2_760` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_cmd2_760/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_cmd2_760/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_cmd2_760/grade.log) |
| `swe_cmd2_770` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_cmd2_770/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_cmd2_770/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_cmd2_770/grade.log) |
| `swe_cmd2_780` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_cmd2_780/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_cmd2_780/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_cmd2_780/grade.log) |
| `swe_sympy_19512` | sympy | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_sympy_19512/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_sympy_19512/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_sympy_19512/grade.log) |
| `swe_sympy_20967` | sympy | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm0_unverified/swe_sympy_20967/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm1_random/swe_sympy_20967/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_starcoder2_15b/arm2_selective/swe_sympy_20967/grade.log) |

---

## 5. Artifact Verification & Replication Trail

All trial directories under `action_time_study_starcoder2_15b` contain:
- `baseline/`: Initial unmodified workspace snapshot
- `workspace/`: Final modified workspace with agent patch
- `events.sqlite`: Transactional audit log containing SHA-256 tree state hashes
- `grade.log`: Raw containerized pytest output and returncode
- `summary.json`: Per-trial telemetry dictionary
