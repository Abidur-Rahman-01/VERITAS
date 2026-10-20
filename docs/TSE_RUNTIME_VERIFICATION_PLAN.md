# IEEE TSE Research Plan: Action-Time Runtime Verification for Autonomous Coding Agents

**Target Publication:** IEEE Transactions on Software Engineering (TSE)  
**Research Program:** VERITAS Runtime Quality Gates & Action-Time Verification  
**Status:** Frozen Methodological Plan & Experimental Specification  
**Date:** October 20, 2026  

---

## 1. Context, Motivation & The Epistemic Pivot

Autonomous software engineering agents powered by LLMs iteratively issue shell commands, inspect directories, and edit codebases. When agents execute faulty intermediate edits (e.g., mislocalized file modifications, broken AST syntax, or destructive environment mutations), these errors compound over long horizons, leading to benchmark failure.

Prior work has focused heavily on **post-hoc patch repair** (generating a draft patch and revising it after full test suite execution). However, in realistic developer settings, executing entire test suites or allowing unchecked file mutations after every step is compute-prohibitive and risky. 

This study investigates **action-time runtime verification**: dynamic, in-loop quality gates that intercept candidate agent actions *before* sandbox execution, evaluate risk vs. cost, and either permit execution, block faulty mutations with workspace rollback, or request replanning.

---

## 2. Formal Research Questions

* **RQ1 (End-Task Effectiveness):** Does selective, action-time runtime verification improve independently graded repository repair success over unverified baselines and budget-matched random verification?
* **RQ2 (Intervention Precision & Safety):** What fraction of intercepted actions represent true harmful mutations (regression prevention) versus false alarms (benign actions wrongly blocked)?
* **RQ3 (Compute & Latency Tradeoffs):** What is the net compute overhead (tokens, wall-clock time, verifier calls) per additional resolved repository task?
* **RQ4 (Task & Domain Heterogeneity):** How does the efficacy of action-time verification vary across repository scale, fault localization complexity, and task domain?

---

## 3. The Unified Experimental Matrix (Four Matched Arms)

To isolate verifier guidance from extra search depth, inference tokens, or chance, all arms share identical step caps (30 steps), identical actor models (`qwen2.5-coder:7b`), and identical tool harnesses:

```
+---------------------------------------------------------------------------------------------------------+
|                                    FOUR-ARM COMPARATIVE STUDY MATRIX                                    |
+------------------------------------+-------------------+-----------+----------------+-------------------+
| Experimental Arm                   | Controller Policy | Step Cap  | Verifier Budget| Verifier Timing   |
+------------------------------------+-------------------+-----------+----------------+-------------------+
| Arm 0: Unverified Baseline         | policy: "never"   | 30 steps  | 0.0 credits    | None (Zero checks)|
| Arm 1: Native-Check Control        | policy: "never"   | 30 steps  | 0.0 credits    | Local dry-run only|
| Arm 2: Random Verification Control | policy: "random"  | 30 steps  | 0.4 credits    | p=0.33 per action |
| Arm 3: Selective Action Gate (Treat)| policy: "error_impact"| 30 steps| 0.4 credits | Pre-action gate   |
+------------------------------------+-------------------+-----------+----------------+-------------------+
```

### Treatment Specifications
1. **Arm 0 (Unverified Baseline):** Actor generates proposals and executes them directly.
2. **Arm 1 (Native-Check Control):** Actor is allowed internal test dry-runs via `pytest` without external verifier critique or blocking.
3. **Arm 2 (Budget-Matched Random Verification):** Verifier is invoked randomly on candidate mutations ($p = 0.33$) until the 0.4 credit budget is exhausted.
4. **Arm 3 (Selective Action-Time Gate):** Controller calculates risk $R = p_{\text{error}} \cdot \text{impact}$, scores candidates against threshold $\tau = 0.25$, and invokes the verifier only when risk justifies verification cost. If verifier returns `FAIL`:
   * `record.blocked = True`, `record.executed = False`
   * Workspace rolled back via checkpoint restore
   * Specific diagnostic critique returned to agent to trigger replanning.

---

## 4. Benchmark Cohort & Sampling Strategy

### A. Two-Stage Protocol (Pilot $\to$ Confirmatory)
1. **Stage 1: Graded Power Pilot ($N = 20$ tasks):**
   * Calibrate controller threshold $\tau$ and verifier false alarm rate.
   * Estimate baseline success $P_0$, within-task correlation, and repository clustering coefficient.
2. **Stage 2: Held-Out Confirmatory Benchmark ($N = 60$ tasks):**
   * Pinned repository tasks across SWE-bench Verified (`python-cmd2/cmd2`, `sympy/sympy`, `PennyLaneAI/pennylane`) and real-world multi-file software packages.
   * Frozen random assignment seeds with block randomization by repository.

### B. Task Independence Guarantee
Each unique repository defect or task ID constitutes exactly **one independent experimental unit**. Repeated seeds on the same task are analyzed as repeated measures within-cluster, never as independent tasks.

---

## 5. Action-Level Auditing & Independent Outcome Grading

### A. Telemetry Schema in SQLite (`events.sqlite`)
For every proposed action turn:
* `proposed_action`: Tool name, target file path, diff or command.
* `decision`: `"verify"`, `"skip"`, or `"blocked"`.
* `verifier_verdict`: `"PASS"`, `"FAIL"`, `"ERROR"`, or `"TIMEOUT"`.
* `verifier_evidence`: Exact diagnostic critique delivered.
* `blocked`: Boolean (`True` if intercepted).
* `executed`: Boolean (`True` if executed in sandbox).
* `state_before` / `state_after` / `restored_hash`: SHA-256 tree hashes.

### B. Independent Grading
* Final workspaces are evaluated using independent containerized test harnesses (`pytest`).
* Tasks are classified as:
  * **Resolved ($Y=1$):** All ground-truth unit tests pass.
  * **Unresolved ($Y=0$):** Test assertion failure or syntax error.
  * **Regression:** Candidate passed initial tests at step $t$ but failed final evaluation.
  * **True Harm Prevented ($TP$):** Verifier intercepted an action that would have broken existing tests.
  * **False Alarm ($FP$):** Verifier intercepted a benign or correct repair action.

---

## 6. Statistical Analysis Plan

* **Primary Estimand:** $\Delta_{\text{treatment}} = Y_{\text{selective}} - Y_{\text{random}}$ on final task resolution.
* **Inference Method:** Repository-clustered percentile bootstrap resampling (10,000 iterations).
* **Multiple Testing:** Holm-Bonferroni correction applied across primary and secondary hypotheses.
* **Confidence Intervals:** 95% Clopper-Pearson exact intervals for binomial proportions; bootstrap percentile intervals for causal contrasts.
