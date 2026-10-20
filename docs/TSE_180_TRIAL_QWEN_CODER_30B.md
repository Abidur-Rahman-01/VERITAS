# IEEE TSE Full 180-Trial Benchmark Report: `qwen2.5-coder:30b` (30B)

**Target Model:** `qwen2.5-coder:30b` (30B Parameters, Ollama Local Execution)  
**Frozen Verifier Model:** `llama3.1:8b` (Greedy Decoding $T=0.0$, Localhost)  
**Sample Size:** 37 Unique Multi-File Repository Tasks $\times$ 3 Arms = **111 Independent Trials**  
**Standardized Limit:** Strictly **30 steps** per trial across all arms  
**Output Directory:** [`action_time_study_qwen2.5_coder_30b`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b)  

---

## 1. Primary Comparative Performance Matrix

| Experimental Arm | Completed Trials | Resolved | Success Rate (%) | Exact 95% Clopper-Pearson CI | Verified Decisions | Blocked Actions | Mean Latency | Total Policy Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 37 | 33 | **89.19%** | [74.58%, 96.97%] | 0 | 0 | 15.39s | 1,605,890 |
| **arm1_random** | 37 | 35 | **94.59%** | [81.81%, 99.34%] | 83 | 8 | 34.80s | 1,067,961 |
| **arm2_selective** | 37 | 33 | **89.19%** | [74.58%, 96.97%] | 34 | 12 | 25.75s | 1,437,900 |

### Causal Contrasts & Statistical Estimates

* **Selective Gate vs. Unverified Baseline:** $\Delta = +0.00\%$
* **Random Verification Control vs. Unverified Baseline:** $\Delta = +5.41\%$
* **Selective Gate vs. Random Control:** $\Delta = -5.41\%$
* **Net Policy Token Reduction:** **10.5%** token savings under selective quality gating

---

## 2. Software Repository Domain Heterogeneity

| Domain Cohort | Unique Tasks | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) |
| :--- | :---: | :---: | :---: | :---: |
| **cmd2 (CLI Framework)** | 8 | 7/8 (87.5%) | 7/8 (87.5%) | **7/8 (87.5%)** |
| **coding_calibration (Calibration Utilities)** | 5 | 4/5 (80.0%) | 5/5 (100.0%) | **4/5 (80.0%)** |
| **core_algorithms (Core Algorithms)** | 4 | 3/4 (75.0%) | 3/4 (75.0%) | **3/4 (75.0%)** |
| **pennylane (Quantum Circuits)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |
| **production_systems (Production Systems)** | 3 | 3/3 (100.0%) | 3/3 (100.0%) | **3/3 (100.0%)** |
| **repo_maintenance (Maintenance)** | 7 | 6/7 (85.7%) | 7/7 (100.0%) | **6/7 (85.7%)** |
| **sympy (Symbolic Math)** | 5 | 5/5 (100.0%) | 5/5 (100.0%) | **5/5 (100.0%)** |

---

## 3. Audited Action-Level Telemetry Across SQLite Databases

* **Total SQLite Databases Audited:** 111
* **Total Action Event Rows:** 735
* **Total Action-Time Verified Decisions (`decision='verify'`):** 117
* **Total Blocked Actions (`blocked=True`, Rollback Executed):** 20
* **Containerized Pytest Grading Logs:** 111 raw `grade.log` files recorded

---

## 4. Comprehensive Task-by-Task Outcome Matrix (60 Tasks)

| Task ID | Domain | Arm 0 (Unverified) | Arm 1 (Random) | Arm 2 (Selective) | Outcome Transition | Grade Logs (Arm 0 / 1 / 2) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: |
| `repo_cli_arg_parser` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_cli_arg_parser/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_cli_arg_parser/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_cli_arg_parser/grade.log) |
| `repo_cli_parser_engine` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_cli_parser_engine/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_cli_parser_engine/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_cli_parser_engine/grade.log) |
| `repo_constant_time_compare` | core_algorithms | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_constant_time_compare/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_constant_time_compare/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_constant_time_compare/grade.log) |
| `repo_csv_delimiter_detector` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_csv_delimiter_detector/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_csv_delimiter_detector/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_csv_delimiter_detector/grade.log) |
| `repo_csv_schema_validator` | repo_maintenance | FAIL | PASS | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_csv_schema_validator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_csv_schema_validator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_csv_schema_validator/grade.log) |
| `repo_env_var_interpolator` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_env_var_interpolator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_env_var_interpolator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_env_var_interpolator/grade.log) |
| `repo_http_header_normalizer` | production_systems | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_http_header_normalizer/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_http_header_normalizer/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_http_header_normalizer/grade.log) |
| `repo_iso_duration` | core_algorithms | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_iso_duration/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_iso_duration/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_iso_duration/grade.log) |
| `repo_json_schema_coercer` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_json_schema_coercer/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_json_schema_coercer/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_json_schema_coercer/grade.log) |
| `repo_lru_cache` | coding_calibration | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_lru_cache/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_lru_cache/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_lru_cache/grade.log) |
| `repo_markdown_link_extractor` | production_systems | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_markdown_link_extractor/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_markdown_link_extractor/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_markdown_link_extractor/grade.log) |
| `repo_nested_dict_resolver` | coding_calibration | FAIL | PASS | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_nested_dict_resolver/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_nested_dict_resolver/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_nested_dict_resolver/grade.log) |
| `repo_retry_backoff_calculator` | coding_calibration | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_retry_backoff_calculator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_retry_backoff_calculator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_retry_backoff_calculator/grade.log) |
| `repo_semver_comparator` | coding_calibration | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_semver_comparator/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_semver_comparator/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_semver_comparator/grade.log) |
| `repo_sql_query_builder` | repo_maintenance | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_sql_query_builder/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_sql_query_builder/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_sql_query_builder/grade.log) |
| `repo_template_formatter` | production_systems | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_template_formatter/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_template_formatter/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_template_formatter/grade.log) |
| `repo_topological_sorter` | core_algorithms | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_topological_sorter/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_topological_sorter/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_topological_sorter/grade.log) |
| `repo_url_query_encoder` | coding_calibration | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_url_query_encoder/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_url_query_encoder/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_url_query_encoder/grade.log) |
| `repo_url_router` | core_algorithms | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/repo_url_router/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/repo_url_router/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/repo_url_router/grade.log) |
| `swe_cmd2_744` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_744/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_744/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_744/grade.log) |
| `swe_cmd2_755` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_755/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_755/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_755/grade.log) |
| `swe_cmd2_760` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_760/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_760/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_760/grade.log) |
| `swe_cmd2_770` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_770/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_770/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_770/grade.log) |
| `swe_cmd2_780` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_780/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_780/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_780/grade.log) |
| `swe_cmd2_790` | cmd2 | FAIL | FAIL | **FAIL** | Hard Defect (Unsolved) | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_790/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_790/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_790/grade.log) |
| `swe_cmd2_800` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_800/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_800/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_800/grade.log) |
| `swe_cmd2_810` | cmd2 | PASS | PASS | **PASS** | Consistently Solved | [`A0`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm0_unverified/swe_cmd2_810/grade.log) / [`A1`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm1_random/swe_cmd2_810/grade.log) / [`A2`](file:///F:/Sadik/VERITAS/artifacts/action_time_study_qwen2.5_coder_30b/arm2_selective/swe_cmd2_810/grade.log) |
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
