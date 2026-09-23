# **VERITAS Architecture, Dataset Preparation, and Benchmark Specification**

---

## **1. System Architecture**

The **VERITAS** runtime operates as an online, resource-constrained gating controller situated between a tool-using LLM agent (policy) and the execution environment. Rather than verifying every action or relying solely on uncalibrated model uncertainty, VERITAS treats verification as a scarce resource, executing expensive verifiers **only when the expected avoided loss justifies the compute cost, verifier false alarms, and state recovery overhead**.

```
                                 ┌─────────────────────────────────────────────────────────┐
                                 │                   USER TASK / GOAL                      │
                                 └────────────────────────────┬────────────────────────────┘
                                                              │
                                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. PLANNER / POLICY MODEL ADAPTER (Capable Policy Model: Claude 3.7 Sonnet / Qwen2.5-Coder-32B)                             │
│ Generates multi-turn ReAct trajectory step: h_t → a_t = (tool, args)                                                      │
└─────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. TYPED ACTION CONTRACT & DETERMINISTIC SAFETY FLOOR                                                                     │
│ Wraps a_t in ActionContract(tool, args, permissions, mutation_type, reversibility, scope).                               │
│ Runs zero-cost checks: Schema validation, AST parsing, permission boundary, allowlist.                                    │
│ └── IF BLOCKED: Fast-fail & trigger instant policy replan (Token Cost = 0).                                              │
└─────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                              │ (If Passed Floor)
                                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. ACTION MEASUREMENT & RISK CALIBRATION LAYER                                                                            │
│  • Raw Error Estimator → Temperature Scaled Calibration → Calibrated Error Probability (p_e,t)                            │
│  • Impact Engine → Consequence / Irreversibility Weight Vector (I_t)                                                     │
│  • Class-Level Empirical Verifier Operating Characteristics (d_c, f_c)                                                    │
│  • Transactional State Recovery Residual Loss (ρ_c)                                                                       │
└─────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. RISK-CALIBRATED VALUE-OF-VERIFICATION (RC-VoV) CONTROLLER                                                              │
│ Evaluates: Δ_t = p_e,t · d_t · (1 - ρ_t) · I_t - C_v,t - (1 - p_e,t) · f_t · C_fp,t                                       │
│ Decision Rule: Compare Δ_t / C_v,t against dynamic threshold λ_t(B_verify).                                               │
└─────────────────────────────┬───────────────────────────────────────────────────────────────┬─────────────────────────────┘
                              │                                                               │
                [SKIP: Δ_t ≤ λ_t · C_v,t]                                       [VERIFY: Δ_t > λ_t · C_v,t]
                              │                                                               │
                              ▼                                                               ▼
┌───────────────────────────────────────────────────────────┐   ┌───────────────────────────────────────────────────────────┐
│ 5a. DIRECT SANDBOX EXECUTION                              │   │ 5b. FALSIFICATION & SEMANTIC VERIFIER ENGINE             │
│ Execute directly in Docker / OverlayFS sandbox.           │   │ Runs deterministic probes, unit tests, static analysis,  │
│ Record observation o_t+1.                                 │   │ or LLM semantic verification.                             │
└─────────────────────────────┬─────────────────────────────┘   └─────────────────────────────┬─────────────────────────────┘
                              │                                                               │
                              │                                              ┌────────────────┴────────────────┐
                              │                                              │                                 │
                              │                                         [VERDICT: PASS]                  [VERDICT: FAIL]
                              │                                              │                                 │
                              │                                              ▼                                 ▼
                              │                                 ┌─────────────────────────┐       ┌─────────────────────────┐
                              │                                 │ EXECUTE & COMMIT        │       │ TRANSACTIONAL CHECKPOINT│
                              │                                 │ Execute verified action │       │ RESTORE (S*)            │
                              │                                 │ in sandbox.             │       │ Restore snapshot, log   │
                              │                                 └────────────┬────────────┘       │ counterfactual, replan. │
                              │                                              │                    └────────────┬────────────┘
                              ▼                                              ▼                                 ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 6. AIR-GAP OBSERVATION SANITIZER & PROVENANCE FIREWALL                                                                    │
│ Redacts secrets, strips indirect prompt injections from tool observations, attaches data provenance tags.               │
└─────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 7. ACTION EVENT STORE & DECOUPLED OFFLINE POLICY REPLAY ENGINE                                                            │
│ Writes complete immutable record (a_t, p_e,t, I_t, Δ_t, verdict, tokens, cost, state_hash) to PostgreSQL / Parquet.     │
│ Enables offline matched-budget replay sweeps across baseline gating policies (Confidence, Risk, p_e · I_t, BAVAR, RC-VoV).│
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### **Detailed Component Breakdown**

#### **Component 1: Planner & Policy Model Adapter**
* **Function**: Decouples policy generation from verification. Accepts user goal \\(q\\) and interaction context \\(h_t\\), outputting a structured action proposal \\(a_t = \pi_\theta(\cdot \mid h_t)\\).
* **Implementation**: Uses a capable foundation model (e.g., Claude 3.7 Sonnet, Qwen2.5-Coder-32B, or Llama-3.3-70B) wrapped in a unified API adapter.

#### **Component 2: Typed Action Contract & Deterministic Safety Floor**
* **Function**: Wraps every raw action \\(a_t\\) in a structured `ActionContract` specifying schema, privilege scope, mutation status, and reversibility.
* **Deterministic Checks**: Before invoking any neural model, it executes zero-token-cost validation: JSON schema check, AST syntax parsing, tool permission scope matching, and regex boundary checks. Malformed or unauthorized actions are rejected immediately.

#### **Component 3: Action Measurement & Risk Calibration Layer**
* **Step-Level Error Probability (\\(p_{e,t}\\))**: A specialized 7B/8B critic or ensemble calculates a raw failure score \\(\hat{s}_t \in\\), which is mapped to a true probability \\(p_{e,t} = P(a_t \text{ is erroneous} \mid h_t)\\) using Temperature Scaling or Isotonic Regression calibrated on held-out trajectories.
* **Action Impact Model (\\(I_t \in\\))**: A transparent weight vector categorizing action reversibility and consequence scope:
  \\[\begin{aligned}
  I_{\text{read}} &\in [0.05, 0.15] \quad (\text{e.g., } \texttt{cat}, \texttt{grep}, \texttt{ls}) \\
  I_{\text{local\_edit}} &\in [0.30, 0.50] \quad (\text{e.g., } \texttt{patch\_file}, \texttt{write\_code}) \\
  I_{\text{env\_mutation}} &\in [0.60, 0.85] \quad (\text{e.g., } \texttt{pip install}, \texttt{rm}, \texttt{schema\_migrate}) \\
  I_{\text{external\_side\_effect}} &\in [0.90, 1.00] \quad (\text{e.g., } \texttt{db\_write}, \texttt{send\_email}, \texttt{api\_call})
  \end{aligned}\\]

#### **Component 4: Empirical Verifier Characteristics (\\(d_c, f_c\\)) & Recovery Estimator (\\(\rho_c\\))**
* **Verifier Detection Rate (\\(d_c\\))**: Empirically measured true positive rate of the verifier on action class \\(c\\) (e.g., fraction of actual errors correctly flagged).
* **Verifier False Rejection Rate (\\(f_c\\))**: Empirically measured false positive rate on action class \\(c\\) (e.g., fraction of valid actions incorrectly flagged as flawed).
* **Residual Recovery Loss (\\(\rho_c \in\\))**: Measured fraction of unrecoverable loss remaining after an action error is undone via transactional rollback \\(\mathcal{S}^*\\). For local file edits restored via Git, \\(\rho_c \approx 0.05\\); for external mutations, \\(\rho_c \to 1.0\\).

#### **Component 5: Risk-Calibrated Value-of-Verification (RC-VoV) Controller**
* **Governing Equation**: Calculates the net expected avoided loss \\(\Delta_t\\) of verifying action \\(a_t\\):
  \\[\Delta_t = \underbrace{p_{e,t} \cdot d_t \cdot (1 - \rho_t) \cdot I_t}_{\text{Expected Avoided Loss}} - \underbrace{C_{v,t}}_{\text{Verifier Cost}} - \underbrace{(1 - p_{e,t}) \cdot f_t \cdot C_{fp,t}}_{\text{Expected False Alarm Penalty}}\\]
* **Budget Allocation Rule**: Given remaining verification budget \\(B_{\text{verify}}\\), verification is invoked (\\(v_t = 1\\)) if:
  \\[\frac{\Delta_t}{C_{v,t}} > \lambda_t(B_{\text{verify}})\\]
  where \\(\lambda_t\\) is a dynamic Lagrange multiplier scaled by remaining budget.

#### **Component 6: Falsification & Semantic Verifier Engine**
* **Function**: When \\(v_t = 1\\), executes multi-tiered falsification probes: static syntax analysis, unit test execution, property-based invariants, or LLM-based semantic critique. Outputs a binary verdict \\(V \in \{\text{PASS}, \text{FAIL}\}\\) and failure diagnostics.

#### **Component 7: Transactional Checkpointing & Recovery (\\(\mathcal{S}^*\\))**
* **Function**: Maintains environment snapshots (Git worktrees, OverlayFS copy-on-write layers, or database savepoints).
* **Recovery Protocol**: When \\(V = \text{FAIL}\\), restores the exact state \\(\mathcal{S}_{t-1}\\), feeds the failure diagnostic back to the policy, and branches to a counterfactual action without resetting the entire prompt history.

#### **Component 8: Air-Gap Observation Sanitizer & Provenance Firewall**
* **Function**: Defends against Indirect Prompt Injections (e.g., malicious payloads embedded in web search results or untrusted files). Enforces structural separation between untrusted observation data and system instructions, redacting credentials and blocking privilege escalation attempts.

#### **Component 9: Decoupled Offline Policy Replay Engine**
* **Function**: Enables cost-effective evaluation. Logs full trajectory records once, allowing research teams to replay dozens of gating policies (Confidence, Risk, \\(p_e \cdot I_t\\), BAVAR-style, RC-VoV) offline under identical verification budgets without invoking LLM policy models repeatedly.

---

## **2. Dataset Preparation Pipeline**

To train error estimators, calibrate probabilities, estimate verifier characteristics (\\(d_c, f_c\\)), and evaluate gating policies without circular reasoning, VERITAS uses a **5-stage data lifecycle**.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: MULTI-TURN TRAJECTORY LOGGING                                                           │
│ Deploy baseline policy models (Claude 3.7, Qwen2.5-Coder) across diverse agent tasks.            │
│ Log complete ReAct interaction traces: (s_t, a_t, o_t, token_log_probs, environment_state).     │
└────────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: OUTCOME ADJUDICATION & GROUND-TRUTH LABELING                                            │
│ Label every action step a_t with ground-truth correctness Y_t ∈ {0 (Erroneous), 1 (Correct)}.    │
│ Primary sources: Execution exit codes, unit test pass/fail, AST diffs, controlled fault seeds.   │
└────────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: 5-FOLD STRATIFIED DATASET SPLITTING                                                      │
│ Split action records by Task/Trajectory Clusters (prevents step-level data leakage):              │
│ ┌───────────────┬───────────────────┬───────────────────┬─────────────────┬─────────────────────┐ │
│ │ 1. DEV (10%)  │ 2. CALIB (25%)    │ 3. VAL (20%)      │ 4. TEST (35%)   │ 5. BACKBONE (10%)   │ │
│ │ Prompt/tool   │ Temperature       │ Threshold tuning, │ Frozen benchmark│ Cross-model         │ │
│ │ debugging.    │ scaling, d_c, f_c.│ offline replay.   │ final evaluation│ transferability.    │ │
│ └───────────────┴───────────────────┴───────────────────┴─────────────────┴─────────────────────┘ │
└────────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: PROBABILITY CALIBRATION & VERIFIER STATISTIC FITTING                                     │
│  • Fit Temperature Scaler T* on Calibration Split: minimize NLL over raw critic logits.           │
│  • Empirical Verifier Characteristics: Calculate d_c = TP/(TP+FN) and f_c = FP/(FP+TN) per class. │
│  • Recovery Loss: Execute controlled fault injection & restoration to measure residual loss ρ_c. │
└────────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: IMMUTABLE OFFLINE REPLAY DATASET EXPORT                                                 │
│ Lock action records as encrypted Parquet/JSONL tables with full cryptographic hashes.             │
│ Schema: {task_id, run_id, step_id, action_contract, p_e_calibrated, I_t, d_c, f_c, ρ_c, label}   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### **Detailed Step-by-Step Data Preparation Protocol**

### **Step 1: Trajectory Collection & Action Taxonomy Mapping**
Execute policy models across benchmark tasks, sampling full ReAct trajectories. Map every proposed action \\(a_t\\) into a standardized taxonomy:
1. `read_op`: File viewing, directory listing, searching (`cat`, `grep`, `find`).
2. `code_edit`: Patching files, modifying code scripts, writing documentation.
3. `env_mutation`: Installing packages, modifying environment variables, compiling binaries.
4. `db_write`: Database inserts, updates, migrations, drop tables.
5. `external_api`: HTTP POST/PUT requests, sending emails, triggering webhooks.

### **Step 2: Ground-Truth Adjudication & Controlled Fault Injection**
Because natural action errors may be sparse (~15–25% of steps), VERITAS augments natural trajectory logs with **seeded fault injection** to ensure statistical power:
* **Natural Adjudication**: Automatically label steps using execution assertions (e.g., non-zero bash return codes, syntax errors, failed unit tests, or scope boundary violations).
* **Controlled Fault Injection**: Inject realistic errors under fixed random seeds:
  * *Code Editing*: Inject off-by-one errors, removed null checks, or incorrect variable names.
  * *Shell / Command*: Inject invalid flag arguments, incorrect file target paths, or syntax errors.
  * *Security / Access*: Inject unauthorized path escalation (`../../etc/passwd`) or broad permissions (`chmod 777`).

### **Step 3: Dataset Splitting & Cluster-Based Isolation**
To prevent data contamination, split datasets by **Task/Trajectory ID** (never by individual action step):
* **Development Set (10%)**: Used for prompt engineering and tool interface debugging.
* **Calibration Set (25%)**: Used to train the raw error critic, fit temperature scaling parameters (\\(T^*\\)), and compute empirical verifier stats (\\(d_c, f_c, \rho_c\\)).
* **Validation Set (20%)**: Used for hyperparameter tuning and offline replay policy selection.
* **Frozen Test Set (35%)**: Locked evaluation set used exclusively for final matched-budget offline replay and online end-to-end runs.
* **Backbone Transfer Set (10%)**: Used to test whether calibrated parameters transfer across different LLM backbones (e.g., from Qwen to Llama).

### **Step 4: Calibration & Verifier Fitting**
1. **Probability Calibration**: Minimize Negative Log-Likelihood (NLL) over the Calibration Set to find temperature \\(T^*\\):
   \\[p_{e,t} = \sigma\left(\frac{z_t}{T^*}\right)\\]
   Evaluate calibration quality using Expected Calibration Error (ECE) and Brier Score.
2. **Empirical Verifier Statistics (\\(d_c, f_c\\))**: Run the verifier over all labeled actions in the Calibration Set for each action class \\(c\\):
   \\[d_c = \frac{\text{True Positives}_c}{\text{True Positives}_c + \text{False Negatives}_c}, \quad f_c = \frac{\text{False Positives}_c}{\text{False Positives}_c + \text{True Negatives}_c}\\]
3. **Residual Recovery Loss (\\(\rho_c\\))**: Execute fault restoration experiments on class \\(c\\), measuring unrecoverable damage:
   \\[\rho_c = \frac{\text{Unrecoverable Work / Residual Loss}}{\text{Total Action Impact}}\\]

---

## **3. Existing Benchmarks (From Source Literature)**

VERITAS evaluates performance across **existing, established benchmarks** cited directly across your notebook papers, covering software engineering, general multi-step reasoning, security guardrails, math/logic, domain-specific execution, and hypothesis validation.

---

### **Benchmark Classification Matrix**

| Domain | Benchmark Name | Source Paper in Notebook | Primary Task Focus | Evaluation Metric |
| :--- | :--- | :--- | :--- | :--- |
| **Software Engineering** | **SWE-bench / SWE-bench Lite / Verified** | *SWE-agent*, *SE-Agent* | Resolving real GitHub issues in Python repositories | Resolved Rate (Pass@1, Pass@5), Token Cost per Solved Issue |
| | **HumanEvalFix** | *SWE-agent* | Multi-language short-form code debugging | Pass@1 Code Repair Accuracy |
| **Generalist & Multi-Step** | **GAIA / GAIA-Text-103** | *Cognitive Kernel Pro*, *CSO*, *TRiSM* | Multi-modal / Text multi-step reasoning & tool orchestration | Pass@1, Pass@3 Accuracy across L1–L3 difficulty |
| | **AgentBoard** | *SelfCorrect-Agent* | Long-horizon multi-turn environment interaction | Success Rate, Progress Rate |
| | **XBench-DeepSearch** | *Cognitive Kernel Pro*, *CSO* | Deep web search, information retrieval & evidence synthesis | Pass@1, Pass@3 Accuracy |
| **Security & Guardrails** | **AgentDojo** | *AgentDojo* | 97 tasks, 629 security test cases under indirect prompt injection | Benign Utility Rate, Attack Success Rate (ASR) |
| | **EICU-AC & Mind2Web-SC** | *GuardAgent* | Healthcare access control & Web safety policy enforcement | Label Prediction Accuracy (LPA), Final Response Accuracy (FRA) |
| | **Agent Security Bench (ASB)** | *Memory Poisoning* | 50 tasks across 10 domains under DSRM RAG poisoning attacks | Attack Success Rate (ASR), Defense Robustness Score |
| | **CyberSecEval** | *BEAVER* | Vulnerability detection and secure code generation | Risky Distribution Ratio (RDR) |
| **Math, Logic & Reasoning** | **GSM8K / GSM-Symbolic** | *BEAVER*, *ReVISE*, *Reflexion* | Grade-school math reasoning under symbolic variation | Accuracy, Bound Tightness Gap (\\(P_{\text{UB}} - P_{\text{LB}}\\)) |
| | **MATH-500** | *ReVISE*, *Reinforce LLM* | Competition-level mathematics reasoning | Pass@1 Accuracy, Sample Efficiency |
| | **MultiArith, AQUA-RAT, StrategyQA** | *Mitigating reasoning* | Arithmetic, commonsense, and multi-step reasoning | Task Accuracy, Hallucination Reduction |
| **Interactive Environments** | **SciWorld, AlfWorld, BabyAI, PDDL** | *SelfCorrect-Agent* | Text-based embodied reasoning & symbolic planning | Success Rate, Progress Score |
| | **NEA CHF Engineering Benchmark** | *Automating data-driven modeling* | Automated nuclear critical heat flux regression & UQ | Model RMSE, UQ Coverage, Completion Rate |
| | **Bridge Portfolio Maintenance** | *LLM agents for bridge portfolio* | Multi-decade infrastructure maintenance scheduling under uncertainty | Min Structural Reliability (\\(\beta\\)), Final Budget Balance |
| **Scientific Hypothesis** | **DiscoveryBench / POPPER** | *Automated Hypothesis Validation* | Automated scientific hypothesis generation & sequential testing | Type-I Error Rate (\\(\alpha\\)), \\(e\\)-Value Evidence Accumulation |

---

### **Detailed Description of Key Experimental Benchmarks**

#### **1. Software Engineering: SWE-bench Verified & HumanEvalFix**
* **SWE-bench Verified**: Consists of 500 human-validated, self-contained software engineering problems collected from 12 major Python open-source repositories (e.g., `sympy`, `matplotlib`, `scikit-learn`). Agents interact with a full repository via terminal tools (`view_file`, `edit_file`, `pytest`).
* **Why VERITAS Uses It**: Serves as the primary online benchmark for evaluating transactional state recovery (\\(\mathcal{S}^*\\)). File edits and test executions provide clear deterministic postconditions, allowing VERITAS to measure token savings from rolling back flawed commits versus restarting 20-step trajectories from scratch.

#### **2. Generalist Reasoning: GAIA-Text-103 & XBench-DeepSearch**
* **GAIA-Text-103**: A curated text-only subset of the GAIA benchmark containing 103 complex questions across 3 difficulty levels requiring tool integration, web search, file processing, and multi-step calculations.
* **XBench-DeepSearch**: Features 100 complex web research tasks requiring multi-hop evidence gathering and synthesis.
* **Why VERITAS Uses It**: Evaluates selective verification on long-horizon reasoning trajectories where tool execution costs and search API latency are high.

#### **3. Security & Safety Control: AgentDojo & GuardAgent (EICU-AC / Mind2Web-SC)**
* **AgentDojo**: Features 97 user tasks combined with 629 security test cases across 4 stateful environments (Email, Workspace, Banking, Slack). Tests agent robustness against indirect prompt injections embedded in external observations.
* **EICU-AC**: Contains 316 healthcare access control queries spanning 51 ICU database categories and 3 user roles (`physician`, `nursing`, `general administration`).
* **Mind2Web-SC**: Evaluates web safety control across 6 real-world online policy rules (e.g., age limits, driver's license requirements, country restrictions).
* **Why VERITAS Uses It**: Tests the **Air-Gap Observation Sanitizer** and **Typed Action Contracts**, proving that VERITAS auto-blocks unauthorized tool execution and prompt injection attacks without degrading benign task utility.

#### **4. Mathematical & Deterministic Verification: GSM-Symbolic & CyberSecEval**
* **GSM-Symbolic**: Generates variations of grade-school math word problems by altering numerical values and names to test reasoning consistency.
* **CyberSecEval**: Evaluates secure code generation and vulnerability detection.
* **Why VERITAS Uses It**: Used in offline replay sweeps to benchmark RC-VoV against **BEAVER-style branch-and-bound verifiers**, measuring probability bound tightness gaps (\\(P_{\text{UB}} - P_{\text{LB}}\\)) and Risky Distribution Ratios (RDR).

---

## **4. Primary Evaluation Metrics & Success Criteria**

To rigorously prove the research claims, VERITAS records metrics across both **Offline Matched-Budget Replay** and **Online End-to-End Execution**.

### **1. Offline Replay Metrics (Allocation Quality at Equal Budget)**
* **Consequential Errors Caught (\\(E_{\text{caught}}\\))**: Number of high-impact action errors (\\(I_t \ge 0.5\\)) flagged by the verifier under verification budget \\(B_{\text{verify}}\\).
* **Verification Precision & Recall**:
  \\[\text{Precision} = \frac{\text{True Erroneous Actions Verified}}{\text{Total Actions Verified}}, \quad \text{Recall} = \frac{\text{True Erroneous Actions Verified}}{\text{Total Erroneous Actions}}\\]
* **Pareto Allocation Frontier**: Plots \\(E_{\text{caught}}\\) across continuous verification budget sweeps (\\(B_1 \dots B_k\\)) to evaluate whether RC-VoV dominates baseline policies.

### **2. Online End-to-End Metrics (Task Performance & Efficiency)**
* **Task Success / Resolved Rate (%)**: Percentage of benchmark tasks fully resolved (e.g., passing all hidden unit tests or ground-truth evaluations).
* **Total Token Consumption (\\(T_{\text{total}}\\))**: Sum of policy planning tokens, verifier tokens, and re-execution tokens per task.
* **Recovery Token Savings (\\(S_{\text{recovery}}\\))**: Percentage of tokens saved by restoring state checkpoints (\\(\mathcal{S}^*\\)) compared to full trajectory restarts:
  \\[S_{\text{recovery}} = 1 - \frac{C_{\text{checkpoint-recovery}}}{C_{\text{restart-from-zero}}}\\]
* **Budget Violation Rate (BVR)**: Fraction of runs exceeding the allocated verification budget \\(B_{\text{verify}}\\) (Target: \\(\text{BVR} = 0\%\\)).

---

### **Core Falsification Test for Publication**
VERITAS earns its architectural complexity if and only if:
\\[\text{Errors Caught}_{\text{RC-VoV}}(B) > \text{Errors Caught}_{p_e \cdot I_t}(B) > \text{Errors Caught}_{\text{Confidence}}(B)\\]
at equal verification compute budget \\(B\\), and this allocation advantage translates to **higher task success and lower token consumption in online end-to-end evaluations**.

---

💡 *Would you like me to draft a complete LaTeX experimental setup file (`experiment_manifest.yaml`) or Python code for the offline policy replay engine to run these exact benchmark sweeps?*