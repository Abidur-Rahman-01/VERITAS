# IEEE TSE Manuscript Dossier & Submission Readiness Package

**Target Publication:** IEEE Transactions on Software Engineering (TSE)  
**Title:** Action-Time Runtime Verification in Autonomous Coding Agents: When Do Dynamic Quality Gates Prevent Repository Regressions?  
**Authors:** Md Abidur Rahman, et al.  
**Repository:** [VERITAS (GitHub)](https://github.com/Abidur-Rahman-01/VERITAS)  
**Date:** October 20, 2026  

---

## 1. IEEE Computer Society Publication Specifications

| Criterion | Requirement | Status in VERITAS Submission |
| :--- | :--- | :--- |
| **Page Limit** | Regular paper: $\le 12$ pages (IEEE Computer Society template) | Formatted to comply within 12-page boundary |
| **Layout** | 2-column, IEEEtran documentclass, 10pt font | Source LaTeX prepared in IEEE format |
| **Unit of Analysis** | Task run (not individual actions or pooled steps) | Clustered by repository defects; no task pooling |
| **Comparators** | Unverified Baseline, Native Check, Budget-Matched Random | 3-arm / 4-arm matched causal trial under identical step bounds |
| **Artifact Policy** | Open science, reproducible code, unedited raw logs | Pinned SQLite traces, manifests, scripts, and ZIP archive |

---

## 2. Manuscript Section Roadmap & Narrative Blueprint

### Section 1: Introduction
* The rise of LLM agents in automated program repair (APR).
* The failure mode of compound unverified action mutations: agents fail not from pure reasoning limitations, but from early unconstrained regressions and fault mislocalization.
* The core research question: *Can lightweight, in-loop action verification protect codebase integrity and boost end-task resolution without blowing up inference budgets?*

### Section 2: Related Work & Novelty Delimitation
* **Classical APR vs. Interactive Agentic APR:** Classical repair separates fault localization from patch synthesis. Interactive agents conflate them.
* **Post-Hoc Patch Repair (Draft $\to$ Review $\to$ Repair):** Existing 2026 literature (IST 2026, VeriHarness) studies whole-patch test feedback. VERITAS investigates pre-execution inter-action gating.
* **Evaluation Awareness & Prompt Psychology:** Prior work notes Hawthorne effects; VERITAS isolates action-time verification from evaluation cues.

### Section 3: Architecture of Action-Time Verification
* **Action Contract Pipeline:** Distinguishing read-only observations from candidate codebase mutations (`edit_file`, `bash`).
* **Controller Policies:** Formal definition of `never`, `random`, and `error_impact` ($RCVOV$).
* **Workspace Rollback Mechanism:** Checkpoint state restoration (`state_before` and `restored_hash`) upon verifier rejection.
* **Cryptographic Event Store:** SQLite append-only audit trail logging every proposed action, verdict, and state transition.

### Section 4: Empirical Study Design
* Four matched experimental arms with equal step bounds ($S = 30$).
* Benchmark cohort: 20 pinned repository defect tasks across production Python codebases (`cmd2`, `sympy`, `pennylane`, and standalone packages).
* Two-stage protocol: Graded power pilot ($N = 20$) followed by held-out confirmatory evaluation.
* Independent grading harness: Containerized execution using ground-truth `pytest` suites.

### Section 5: Empirical Results & Mechanism Analysis
* **End-Task Resolution:** Net causal contrast $\Delta_{\text{treatment}}$ over random and unverified baselines.
* **Intervention Accuracy:** True Harm Prevented ($TP$) vs. False Alarms ($FP$).
* **Compute & Latency Economics:** Token consumption, verifier credit expenditure, and wall-clock overhead.

### Section 6: Threats to Validity
* **Construct Validity:** Operational definitions of blocked actions and regression prevention.
* **Internal Validity:** Elimination of step-limit confounds; identical temperature ($0.0$) and model versions.
* **External Validity:** Generalization across diverse repository architectures and multi-file codebases.

### Section 7: Conclusion & Implications for Software Engineering
* Guidelines for engineering robust runtime quality gates in production autonomous developer agents.

---

## 3. Data & Artifact Availability Statement

All data, raw event databases, conversation transcripts, evaluation harnesses, and analysis scripts supporting this study are permanently and publicly accessible:
* **Primary Git Repository:** `https://github.com/Abidur-Rahman-01/VERITAS`
* **Study Archive:** `VERITAS_study_package.zip` (containing raw SQLite logs with cryptographic SHA-256 event chains).
* **Execution Script:** `python scripts/run_action_time_tse_experiment.py`
* **Analysis Script:** `python scripts/analyze_action_time_study.py`

---

## 4. Submission Readiness Checklist

- [x] Clear treatment defined: mutation checks, rollback on FAIL, specific replan feedback.
- [x] Matched comparative arms: Unverified vs. Random Control vs. Selective Gate.
- [x] Step limits standardized (30 steps across all conditions).
- [x] Model identities pinned: Actor `qwen2.5-coder:7b`, Verifier `llama3.1:8b`.
- [x] Blocked-action logging bug in `runtime.py` fixed and verified.
- [x] Complete SQLite event schema with `decision="verify"`, `blocked=1`, `executed=0`.
- [x] Independent outcome grading via containerized `pytest`.
- [x] Statistical analysis clustered by repository with bootstrap intervals.
