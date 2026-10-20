# IEEE TSE Full 180-Trial Benchmark Report: `qwen2.5-coder:30b` (30B)

**Target Model:** `qwen2.5-coder:30b` (30B Parameters, Ollama Local Execution)  
**Frozen Verifier Model:** `llama3.1:8b` (Greedy Decoding $T=0.0$, Localhost)  
**Sample Size:** 17 Unique Multi-File Repository Tasks $\times$ 3 Arms = **51 Independent Trials**  
**Standardized Limit:** Strictly **30 steps** per trial across all arms  
**Output Directory:** [`action_time_study_qwen2.5_coder_30b`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b)  

---

## 1. Primary Comparative Performance Matrix

| Experimental Arm | Completed Trials | Resolved | Success Rate (%) | Exact 95% Clopper-Pearson CI | Verified Decisions | Blocked Actions | Mean Latency | Total Policy Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 17 | 17 | **100.00%** | [80.49%, 100.00%] | 0 | 0 | 5.62s | 153,136 |
| **arm1_random** | 17 | 17 | **100.00%** | [80.49%, 100.00%] | 31 | 0 | 25.50s | 184,974 |
| **arm2_selective** | 17 | 17 | **100.00%** | [80.49%, 100.00%] | 2 | 0 | 10.26s | 157,483 |

### Causal Contrasts & Statistical Estimates

* **Selective Gate vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Random Verification Control vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Selective Gate vs. Random Control:** $\Delta = +0.00\%$
* **Net Policy Token Reduction:** **-2.8%** token savings under selective quality gating

---

## 2. Software Repository Domain Heterogeneity

| Domain Cohort | Unique Tasks | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) |
| :--- | :---: | :---: | :---: | :---: |
| **cmd2 (CLI Framework)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |
| **pennylane (Quantum Circuits)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |
| **repo_maintenance (Maintenance)** | 2 | 2/2 (100.0%) | 2/2 (100.0%) | **2/2 (100.0%)** |
| **sympy (Symbolic Math)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |

---

## 3. Audited Action-Level Telemetry Across SQLite Databases

* **Total SQLite Databases Audited:** 51
* **Total Action Event Rows:** 246
* **Total Action-Time Verified Decisions (`decision='verify'`):** 33
* **Total Blocked Actions (`blocked=True`, Rollback Executed):** 0
* **Containerized Pytest Grading Logs:** 51 raw `grade.log` files recorded

---

## 4. Comprehensive Task-by-Task Outcome Matrix (60 Tasks)

| Task ID | Domain | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) | Outcome Transition | Grade Logs (Arm 0 / 1 / 2) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: |
| `repo_env_var_interpolator` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_env_var_interpolator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_env_var_interpolator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_env_var_interpolator/grade.log) |
| `repo_json_schema_coercer` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_json_schema_coercer/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_json_schema_coercer/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_json_schema_coercer/grade.log) |
| `swe_cmd2_744` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_744/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_744/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_744/grade.log) |
| `swe_cmd2_755` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_755/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_755/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_755/grade.log) |
| `swe_cmd2_760` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_760/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_760/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_760/grade.log) |
| `swe_cmd2_770` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_770/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_770/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_770/grade.log) |
| `swe_cmd2_780` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_780/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_780/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_780/grade.log) |
| `swe_pennylane_4376` | pennylane | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_pennylane_4376/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_pennylane_4376/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_pennylane_4376/grade.log) |
| `swe_pennylane_4402` | pennylane | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_pennylane_4402/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_pennylane_4402/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_pennylane_4402/grade.log) |
| `swe_pennylane_4488` | pennylane | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_pennylane_4488/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_pennylane_4488/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_pennylane_4488/grade.log) |
| `swe_pennylane_4512` | pennylane | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_pennylane_4512/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_pennylane_4512/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_pennylane_4512/grade.log) |
| `swe_pennylane_5063` | pennylane | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_pennylane_5063/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_pennylane_5063/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_pennylane_5063/grade.log) |
| `swe_sympy_18033` | sympy | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_sympy_18033/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_sympy_18033/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_sympy_18033/grade.log) |
| `swe_sympy_18189` | sympy | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_sympy_18189/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_sympy_18189/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_sympy_18189/grade.log) |
| `swe_sympy_18621` | sympy | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_sympy_18621/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_sympy_18621/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_sympy_18621/grade.log) |
| `swe_sympy_19512` | sympy | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_sympy_19512/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_sympy_19512/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_sympy_19512/grade.log) |
| `swe_sympy_20967` | sympy | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_sympy_20967/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_sympy_20967/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_sympy_20967/grade.log) |

---

## 5. Artifact Verification & Replication Trail

All trial directories under `action_time_study_qwen2.5_coder_30b` contain:
- `baseline/`: Initial unmodified workspace snapshot
- `workspace/`: Final modified workspace with agent patch
- `events.sqlite`: Transactional audit log containing SHA-256 tree state hashes
- `grade.log`: Raw containerized pytest output and returncode
- `summary.json`: Per-trial telemetry dictionary
