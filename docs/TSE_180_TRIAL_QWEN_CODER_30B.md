# IEEE TSE Full 180-Trial Benchmark Report: `qwen2.5-coder:30b` (30B)

**Target Model:** `qwen2.5-coder:30b` (30B Parameters, Ollama Local Execution)  
**Frozen Verifier Model:** `llama3.1:8b` (Greedy Decoding $T=0.0$, Localhost)  
**Sample Size:** 21 Unique Multi-File Repository Tasks $\times$ 3 Arms = **63 Independent Trials**  
**Standardized Limit:** Strictly **30 steps** per trial across all arms  
**Output Directory:** [`action_time_study_qwen2.5_coder_30b`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b)  

---

## 1. Primary Comparative Performance Matrix

| Experimental Arm | Completed Trials | Resolved | Success Rate (%) | Exact 95% Clopper-Pearson CI | Verified Decisions | Blocked Actions | Mean Latency | Total Policy Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 21 | 20 | **95.24%** | [76.18%, 99.88%] | 0 | 0 | 6.91s | 319,167 |
| **arm1_random** | 21 | 21 | **100.00%** | [83.89%, 100.00%] | 43 | 1 | 30.97s | 418,895 |
| **arm2_selective** | 21 | 20 | **95.24%** | [76.18%, 99.88%] | 6 | 4 | 12.34s | 311,004 |

### Causal Contrasts & Statistical Estimates

* **Selective Gate vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Random Verification Control vs. Unverified Baseline:** $\Delta = +4.76\%$
* **Selective Gate vs. Random Control:** $\Delta = -4.76\%$
* **Net Policy Token Reduction:** **2.6%** token savings under selective quality gating

---

## 2. Software Repository Domain Heterogeneity

| Domain Cohort | Unique Tasks | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) |
| :--- | :---: | :---: | :---: | :---: |
| **cmd2 (CLI Framework)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |
| **core_algorithms (Core Algorithms)** | 1 | 1/1 (100.0%) | 1/1 (100.0%) | **1/1 (100.0%)** |
| **pennylane (Quantum Circuits)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |
| **repo_maintenance (Maintenance)** | 5 | 4/5 (80.0%) | 5/5 (100.0%) | **4/5 (80.0%)** |
| **sympy (Symbolic Math)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |

---

## 3. Audited Action-Level Telemetry Across SQLite Databases

* **Total SQLite Databases Audited:** 63
* **Total Action Event Rows:** 353
* **Total Action-Time Verified Decisions (`decision='verify'`):** 49
* **Total Blocked Actions (`blocked=True`, Rollback Executed):** 5
* **Containerized Pytest Grading Logs:** 63 raw `grade.log` files recorded

---

## 4. Comprehensive Task-by-Task Outcome Matrix (60 Tasks)

| Task ID | Domain | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) | Outcome Transition | Grade Logs (Arm 0 / 1 / 2) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: |
| `repo_cli_parser_engine` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_cli_parser_engine/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_cli_parser_engine/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_cli_parser_engine/grade.log) |
| `repo_csv_schema_validator` | repo_maintenance | FAIL | PASS | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_csv_schema_validator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_csv_schema_validator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_csv_schema_validator/grade.log) |
| `repo_env_var_interpolator` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_env_var_interpolator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_env_var_interpolator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_env_var_interpolator/grade.log) |
| `repo_json_schema_coercer` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_json_schema_coercer/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_json_schema_coercer/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_json_schema_coercer/grade.log) |
| `repo_sql_query_builder` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_sql_query_builder/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_sql_query_builder/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_sql_query_builder/grade.log) |
| `repo_topological_sorter` | core_algorithms | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_topological_sorter/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_topological_sorter/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_topological_sorter/grade.log) |
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
