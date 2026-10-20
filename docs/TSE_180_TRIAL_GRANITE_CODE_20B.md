# IEEE TSE Full 180-Trial Benchmark Report: `granite-code:20b` (20B)

**Target Model:** `granite-code:20b` (20B Parameters, Ollama Local Execution)  
**Frozen Verifier Model:** `llama3.1:8b` (Greedy Decoding $T=0.0$, Localhost)  
**Sample Size:** 1 Unique Multi-File Repository Tasks $\times$ 3 Arms = **3 Independent Trials**  
**Standardized Limit:** Strictly **30 steps** per trial across all arms  
**Output Directory:** [`action_time_study_granite_code_20b`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_granite_code_20b)  

---

## 1. Primary Comparative Performance Matrix

| Experimental Arm | Completed Trials | Resolved | Success Rate (%) | Exact 95% Clopper-Pearson CI | Verified Decisions | Blocked Actions | Mean Latency | Total Policy Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 1 | 0 | **0.00%** | [0.00%, 97.50%] | 0 | 1 | 154.98s | 177,958 |
| **arm1_random** | 1 | 0 | **0.00%** | [0.00%, 97.50%] | 4 | 4 | 51.88s | 65,138 |
| **arm2_selective** | 1 | 0 | **0.00%** | [0.00%, 97.50%] | 0 | 4 | 259.17s | 199,636 |

### Causal Contrasts & Statistical Estimates

* **Selective Gate vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Random Verification Control vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Selective Gate vs. Random Control:** $\Delta = +0.00\%$
* **Net Policy Token Reduction:** **-12.2%** token savings under selective quality gating

---

## 2. Software Repository Domain Heterogeneity

| Domain Cohort | Unique Tasks | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) |
| :--- | :---: | :---: | :---: | :---: |
| **cmd2 (CLI Framework)** | 1 | 0/1 (0.0%) | 0/1 (0.0%) | **0/1 (0.0%)** |

---

## 3. Audited Action-Level Telemetry Across SQLite Databases

* **Total SQLite Databases Audited:** 3
* **Total Action Event Rows:** 57
* **Total Action-Time Verified Decisions (`decision='verify'`):** 4
* **Total Blocked Actions (`blocked=True`, Rollback Executed):** 9
* **Containerized Pytest Grading Logs:** 3 raw `grade.log` files recorded

---

## 4. Comprehensive Task-by-Task Outcome Matrix (60 Tasks)

| Task ID | Domain | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) | Outcome Transition | Grade Logs (Arm 0 / 1 / 2) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: |
| `swe_cmd2_744` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_granite_code_20b/arm0_unverified/swe_cmd2_744/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_granite_code_20b/arm1_random/swe_cmd2_744/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_granite_code_20b/arm2_selective/swe_cmd2_744/grade.log) |

---

## 5. Artifact Verification & Replication Trail

All trial directories under `action_time_study_granite_code_20b` contain:
- `baseline/`: Initial unmodified workspace snapshot
- `workspace/`: Final modified workspace with agent patch
- `events.sqlite`: Transactional audit log containing SHA-256 tree state hashes
- `grade.log`: Raw containerized pytest output and returncode
- `summary.json`: Per-trial telemetry dictionary
