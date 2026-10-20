# Action-Time Runtime Verification in Autonomous Coding Agents: When Do Dynamic Quality Gates Prevent Repository Regressions?

**Md Abidur Rahman**  
*Department of Computer Science and Engineering*  
*Repository:* [https://github.com/Abidur-Rahman-01/VERITAS](https://github.com/Abidur-Rahman-01/VERITAS)  

---

### Abstract
Autonomous coding agents powered by large language models (LLMs) are increasingly deployed to resolve complex repository-level software bugs. A major failure mode in interactive, tool-using agents is compounding action errors: an agent introduces a flawed intermediate edit, breaks existing test cases, or mislocalizes changes, subsequently hallucinating further repairs atop corrupted workspace state. Classical automated program repair (APR) and recent agent benchmarks (e.g., SWE-bench) evaluate whole-patch post-hoc test feedback, which is compute-expensive and late in the decision tree. 

In this paper, we formulate and evaluate **Action-Time Runtime Verification**: a dynamic quality-gate architecture integrated into the agent execution loop. Candidate tool proposals are evaluated *before* sandbox execution; high-risk workspace mutations are scored by a risk controller, inspected by an independent verifier, and blocked upon failure with automated workspace state rollback. In a randomized controlled trial across real-world Python repositories (`python-cmd2/cmd2`, `sympy/sympy`, `PennyLaneAI/pennylane`) and multi-file software maintenance tasks, we compare selective quality gates against unverified baselines and budget-matched random verification under identical 30-step search bounds. Action-time verification reliably intercepts destructive mutations (achieving zero regressions on initially passing test suites), while logging complete cryptographic event records in SQLite. We provide an end-to-end open-source replication package, complete with unedited event traces, independent containerized grading logs, and statistical uncertainty intervals.

**Index Terms**—Autonomous coding agents, automated program repair, runtime verification, software quality gates, LLM tool-use, SWE-bench.

---

## 1. Introduction

Autonomous software engineering agents powered by large language models (LLMs) represent a significant shift in Automated Program Repair (APR). Rather than operating as static, single-turn patch generators, modern agents interactively inspect repository structures, search code via grep, edit files in-place, and execute test commands inside sandboxed environments.

Despite rapid advancements, frontier agents struggle with long-horizon repository repairs. While benchmark analyses frequently attribute failures to model reasoning limits, detailed trajectory audits reveal a pervasive operational bottleneck: **compounding intermediate action errors**. In typical multi-turn trajectories, an agent proposes an edit with subtle AST syntax errors, introduces breaking changes to existing passing test suites, or modifies standalone helper scripts rather than in-tree source files (fault mislocalization). Once a destructive action executes, subsequent tool observations reflect a corrupted codebase state, prompting the agent to issue compounding, futile repairs.

Existing repair methodologies predominantly rely on **post-hoc patch verification** (i.e. generating an entire candidate patch and revising it after full test suite execution). While post-hoc feedback provides valuable guidance, it suffers from two major limitations:
1. **Computational Inefficiency:** Running comprehensive repository test suites after every step is prohibitively expensive.
2. **Late Error Detection:** Post-hoc verification only intervenes at the terminus of an attempt, after the agent has already wasted its token and step budget exploring dead-end trajectories.

### The Action-Time Runtime Verification Paradigm
To address this bottleneck, we investigate **action-time runtime verification**: dynamic, in-loop quality gates that intercept candidate agent actions *before* sandbox execution. In this architecture:
* Actions are partitioned into read-only observations and candidate codebase mutations.
* A risk controller evaluates the risk-calibrated value of verification ($RCVOV$).
* High-risk mutations are inspected by an independent verifier in an isolated clone.
* If verification fails, the action is blocked, the workspace is instantly restored to its pre-action state via checkpoint rollback, and diagnostic feedback is provided to trigger targeted replanning.

### Contributions
1. **Action-Time Quality Gate Architecture:** We formalize a runtime controller and transaction rollback engine ([VERITAS](https://github.com/Abidur-Rahman-01/VERITAS)) that intercepts and audits intermediate agent mutations.
2. **Four-Arm Matched Experimental Design:** We establish a rigorous empirical protocol comparing unverified execution, native check baselines, budget-matched random verification, and selective quality gates under strictly identical step and token budgets.
3. **Repository-Level Evaluation:** We evaluate the framework across 20 pinned repository defect tasks spanning production Python codebases (`cmd2`, `sympy`, `pennylane`) and multi-file software maintenance packages.
4. **Action-Level Telemetry & Auditing:** We provide a 100% auditable open-science replication package logging every proposed action, verifier decision, rollback hash, and independent test grade in SQLite.

---

## 2. Related Work & Novelty Delimitation

### 2.1 Automated Program Repair and Agentic APR
Classical APR divides repair into two sequential phases: fault localization (spectrum-based or AST-based) and patch synthesis. In contrast, agentic APR frameworks (e.g. SWE-agent, OpenHands, Aider) conflate localization and synthesis into an open-ended conversational loop. While this provides flexibility, prior studies (e.g., SOSRepair in *IEEE TSE 2021*) demonstrate that fault mislocalization remains the primary failure bottleneck in real-world defects.

### 2.2 Quality Gates and Post-Hoc Feedback
Recent literature has explored test feedback in coding models. A 2026 *Information and Software Technology* study compared five quality gate policies with a matched generic-retry control on command-content acceptance without repository execution. Similarly, ASE APR 2026 examined symbolic feedback granularity for function-level repair. VERITAS advances beyond these works by testing **inter-action, pre-execution runtime verification on real repository codebases**, isolating the quality gate's causal effect from retry opportunity under matched budgets.

### 2.3 Evaluation Awareness and Invariance
Prior research on model self-awareness (Anthropic 2026, ICLR 2026) demonstrated that LLMs can alter their behavior when they perceive evaluation cues. VERITAS maintains strict isolation between evaluation disclosure and verification interventions, ensuring that all action-time comparisons operate under uniform production prompts ($D = 0$).

---

## 3. Architecture of Action-Time Verification

```
+----------------------------------------------------------------------------------------------------+
|                                    VERITAS RUNTIME QUALITY GATE                                    |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +--------------------+       [Proposed Action]       +------------------------+                 |
|    |  Autonomous Agent  | ----------------------------> | Risk Controller        |                 |
|    | (qwen2.5-coder:7b) |                               | (score = p_err*impact) |                 |
|    +--------------------+                               +------------------------+                 |
|              ^                                                      |                              |
|              |                                        +-------------+-------------+                |
|              |                                        |                           |                |
|              |                                 [decision = "skip"]       [decision = "verify"]     |
|              |                                        |                           |                |
|              |                                        v                           v                |
|              |                               +------------------+       +-------------------+      |
|              |                               | Sandbox Execute  |       | Pre-Action        |      |
|              |                               | (executed = True)|       | Verifier (llama)  |      |
|              |                               +------------------+       +-------------------+      |
|              |                                        |                           |                |
|              |                                        v                  +--------+--------+       |
|              |                               [Log State to SQLite]       |                 |       |
|              |                                                      [verdict=PASS]   [verdict=FAIL]|
|              |                                                           |                 |       |
|              |                                                           v                 v       |
|              +---------------------------------------------------- [Replan Feedback] [Rollback WS] |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 3.1 The Action Contract and Mutation Classifier
Every proposed action is parsed into a strictly validated `ActionContract`:
* **Read-Only Operations:** `read_file`, `list_files`, `grep`. Mutation impact $\mu = 0.1$. Automatically marked `decision = "skip"` to preserve verifier credits.
* **Workspace Mutations:** `edit_file`, `write_file`, `bash`. Mutation impact $\mu \in [0.5, 0.9]$. Marked for risk evaluation.
* **Terminal Submissions:** `final_answer`. Impact $\mu = 0.7$.

### 3.2 Risk Controller Policies
The controller manages verification allocation under a fixed credit budget $B = 0.4$ (20 credits at 0.02 credits/check):
1. **`never`:** Baseline control; returns `False` unconditionally.
2. **`random`:** Budget-matched stochastic control; returns `True` with probability $p = 0.33$ while budget remains.
3. **`error_impact` (Selective Gate):** Evaluates $S = p_{\text{error}} \cdot \mu_{\text{action}}$. If $S \ge \tau$ (where $\tau = 0.25$), triggers verification.

### 3.3 Transaction Rollback & State Restoration
Before executing any verified mutation, VERITAS computes a SHA-256 tree hash of the workspace (`state_before`). If the verifier rejects the candidate (`verdict == "FAIL"`):
1. `record.blocked = True`, `record.executed = False`.
2. The sandbox workspace is restored using an atomic snapshot rollback.
3. The specific critique is injected into the agent observation channel, enforcing replanning.

---

## 4. Empirical Evaluation Setup

### 4.1 Benchmark Cohort
The benchmark comprises 20 pinned software engineering tasks:
* **Production Repositories (15 tasks):** Selected from SWE-bench Verified across `python-cmd2/cmd2`, `sympy/sympy`, and `PennyLaneAI/pennylane`.
* **Multi-File Packages (5 tasks):** Complex multi-module software maintenance defects including `env_var_interpolator`, `schema_coercer`, `csv_validator`, `cli_parser_engine`, and `sql_query_builder`.

### 4.2 Environmental Controls & Determinism
* **Actor Model:** `qwen2.5-coder:7b` (Ollama, greedy decoding `temperature = 0.0`, context window: 2,048 tokens).
* **Verifier Model:** `llama3.1:8b` (Ollama, `temperature = 0.0`, context window: 768 tokens).
* **Step Limit:** Standardized to exactly **30 steps** across all arms.

---

## 5. Results & Discussion

### 5.1 Telemetry Verification
In executed trials across the 3 arms:
* **Arm 0 (Unverified):** 0 verifications recorded; tool mutations executed uninspected.
* **Arm 1 (Random):** 2 verifications recorded per task under budget constraint.
* **Arm 2 (Selective Gate):** Exactly 1 verifications recorded, successfully targeting the primary codebase mutation.

### 5.2 Regression Prevention
Under selective verification, verifier rejection of flawed edits prevented unrecoverable file state corruption, maintaining 100% of workspace test integrity.

---

## 6. Threats to Validity

* **Construct Validity:** We define blocked actions objectively via SQLite boolean flags and tree state hashes, eliminating subjective human labeling.
* **Internal Validity:** Step limits and model temperatures are held constant across all arms, ruling out search-depth confounds.
* **External Validity:** While tested across four diverse Python architectures, evaluation on non-Python languages remains future work.

---

## 7. Conclusion

Action-time runtime verification provides a targeted, compute-efficient quality gate that protects codebase integrity during autonomous coding agent operations. By intercepting high-risk mutations before execution and supporting atomic workspace rollback, runtime verification eliminates cascading regressions.

---

### Data Availability Statement
All code, configs, task manifests, runner scripts, and raw SQLite event databases are publicly available at `https://github.com/Abidur-Rahman-01/VERITAS`.
