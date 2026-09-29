# VERITAS Infrastructure & Qualification Status Report

> **Research status (September 29, 2026):** The causal evaluation-awareness experiment ($D \times A$) has not run. There is no `awareness-report.json`, and no causal estimate is available. This document records software infrastructure, qualification status, and exploratory legacy-track outputs; it does not report evidence for the project's core causal claim and is not a publication results report.

**Document Date:** September 29, 2026  
**Repository:** [VERITAS](file:///D:/2110001/VERITAS) (`Abidur-Rahman-01/VERITAS`)  
**Specification Reference:** [docs/ARCHITECTURE.md](file:///D:/2110001/VERITAS/docs/ARCHITECTURE.md)  
**Configuration Reference:** [configs/awareness-local.yaml](file:///D:/2110001/VERITAS/configs/awareness-local.yaml), [configs/datasets.yaml](file:///D:/2110001/VERITAS/configs/datasets.yaml)

---

## 1. Executive Summary & Codebase Updates

The repository contains an implemented causal evaluation-awareness ($D \times A$) framework and legacy-track scripts and data. The causal experiment has not been executed: the split and plan files are absent, qualification lists unresolved prerequisites, and no awareness report exists. The numbers in Section 2 are exploratory outputs from the earlier track and must not be treated as validation of the causal hypothesis.

### Recent Commit Timeline & Major Updates

| Commit | Date | Summary & Architectural Significance |
|---|---|---|
| `5a57809` | 2026-09-29 | **Local Deployment & Docker Integration:** Added [Dockerfile](file:///D:/2110001/VERITAS/Dockerfile), [docker-compose.yml](file:///D:/2110001/VERITAS/docker-compose.yml), local awareness configs ([awareness-local.yaml](file:///D:/2110001/VERITAS/configs/awareness-local.yaml), [experiment_local.yaml](file:///D:/2110001/VERITAS/configs/experiment_local.yaml)), Windows model pull automation ([scripts/pull_all_models.ps1](file:///D:/2110001/VERITAS/scripts/pull_all_models.ps1)), and awareness store transactional hardening. |
| `884b905` | 2026-09-29 | **Architecture Completion & Measurements:** Implemented [awareness_qualification.py](file:///D:/2110001/VERITAS/src/veritas/awareness_qualification.py), [awareness_measurements.py](file:///D:/2110001/VERITAS/src/veritas/awareness_measurements.py), [awareness_costs.py](file:///D:/2110001/VERITAS/src/veritas/awareness_costs.py), and [model_provenance.py](file:///D:/2110001/VERITAS/src/veritas/model_provenance.py) with 243 passing tests. |
| `1c781ee` | 2026-09-28 | **VERITAS v2 Overhaul:** Formalized the $2 \times 2$ factorial evaluation-awareness decomposition ($D \in \{0, 1\} \times A \in \{0, 1\}$), two-phase draft/revision execution loop, bounded patch reviewer, cluster-robust resampling, and Learn-Then-Test gate calibration. |
| `2774437` | 2026-09-26 | **Task-Level Extended Evaluation & CSO:** SWE-100 benchmark execution, 8-model reasoning latency/accuracy suite, GAIA evaluation, scaling multi-eval, and the 23-pair Contract & State Optimization preference dataset. |
| `6a3fd07` | 2026-09-25 | **Graph Verification Engine:** Added DAG-based dependency verifier and prerequisite/semantic review pipeline. |

---

## 2. Exploratory Legacy-Track Outputs (Not Core-Hypothesis Evidence)

### 2.1. Legacy SWE-100 Synthetic Policy Simulation (Not SWE-bench Task Performance)

*Source:* [swe_100_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/swe_100_eval.json) & [swe_100_eval.csv](file:///D:/2110001/VERITAS/veritas/research/results/swe_100_eval.csv)  
*Setup as implemented in the revised script:* 100 task metadata rows are used to synthesize four action contracts each. This does not execute SWE-bench tasks or evaluate patches. Synthetic opportunity labels are randomized independently of policy inputs and are not placed in action contracts. The script reports scheduler selections and label overlap only; detection, recovery, and state-integrity metrics are explicitly unavailable. The result files currently in the repository predate this correction and must not be interpreted as outputs of the revised script.

| Verification Policy | Actions Verified | Verification Rate (%) | Budget Spent ($) | Errors Caught (of 50) | Detection Recall (%) | Verifier Precision (%) | False Rejections | Recoveries Executed | Hash Invariance Rate |
|---|---|---|---|---|---|---|---|---|---|
| **`never`** | 0 / 400 | 0.0% | $0.00 | 0 | 0.0% | 0.0% | 0 | 0 | 100% |
| **`always`** | 400 / 400 | 100.0% | $12.00 | 50 | 100.0% | 12.5% | 0 | 50 | 100% |
| **`error_x_impact` (VERITAS)** | **50 / 400** | **12.5%** | **$1.50** | **50** | **100.0%** | **100.0%** | **0** | **50** | **100%** |
| **`bavar_style`** | 100 / 400 | 25.0% | $3.00 | 50 | 100.0% | 50.0% | 0 | 50 | 100% |
| **`rc_vov`** | 100 / 400 | 25.0% | $3.00 | 50 | 100.0% | 50.0% | 0 | 50 | 100% |

#### Interpretation:
These are scheduler counts under a synthetic trajectory and label-informed error-probability input. They do not establish detection recall, verifier precision, cost effectiveness on SWE-bench, or cryptographic state integrity. Do not cite the headline metrics as empirical findings. The script requires redesign with fault assignment independent of scheduler inputs and an outcome-based verifier oracle before it can support a detection claim.

---

### 2.2. Extended Multi-Model Reasoning & Contract Benchmark

*Source:* [extended_models_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/extended_models_eval.json) & [extended_models_eval.csv](file:///D:/2110001/VERITAS/veritas/research/results/extended_models_eval.csv)  
*Setup:* Ten problems per model, as recorded in the CSV. These small exploratory runs have high sampling uncertainty; the percentages are descriptive only. No scaling inference is warranted from this sample.

| Model | Family | Scale | VRAM Footprint | Accuracy (%) | Step Latency (ms) | Contract Latency (ms) | Valid Contract | Tool / Operation Proposed | Calibrated Risk Prior |
|---|---|---|---|---|---|---|---|---|---|
| `llama3.2:1b` | Llama 3.2 | 1B | 1.3 GB | 30.0% | 3,283.9 | 2,372.8 | True | `audit` / `queryset` | 0.20 |
| `qwen2.5:1.5b` | Qwen 2.5 | 1.5B | 1.0 GB | 50.0% | 2,804.9 | 2,230.5 | True | `audit_django_cache` / `invalidate_queryset_cache` | 0.01 |
| `gemma2:2b` | Gemma 2 | 2B | 1.6 GB | 50.0% | 5,101.1 | 2,284.7 | True | `django-orm-cache-analyzer` / `analyze` | 0.10 |
| `llama3.2:3b` | Llama 3.2 | 3B | 2.0 GB | 60.0% | 3,552.2 | 2,339.5 | True | `dbshell` / `queryset_cache_invalidate` | 0.05 |
| `mistral:7b` | Mistral | 7B | 4.1 GB | 40.0% | 4,296.7 | 2,413.2 | True | `Django Debug Toolbar` / `enable` | 0.01 |
| `llama3.1:8b` | Llama 3.1 | 8B | 4.7 GB | 70.0% | 4,082.4 | 2,409.1 | True | `shell` / `echo` | 0.80 |
| `qwen2.5-coder:7b` | Qwen 2.5 Coder | 7B | 4.7 GB | 80.0% | 4,458.8 | 2,367.4 | True | `Django ORM` / `list_queryset_cache` | 0.01 |
| `qwen2.5-coder:14b` | Qwen 2.5 Coder | 14B | 9.0 GB | **90.0%** | 6,008.7 | 2,801.9 | True | `Django ORM` / `QuerySet` | 0.01 |

#### Interpretation:
Every reported model has n=10. The results are too small to support a scaling claim. Accuracy is non-monotonic: `mistral:7b` scores 40%, below `llama3.2:3b` at 60%; all model rows should be retained in any discussion. Latency and role assignments are exploratory measurements, not validated deployment recommendations.

---

### 2.3. Multi-Model Speculative Scaling Evaluation

*Source:* [scaling_multi_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/scaling_multi_eval.json)

| Model Tier | Parameter Scale | VRAM | Assigned Architecture Role | Contract Latency (ms) | Speculative Verifier Latency (ms) | Fast Path Verified |
|---|---|---|---|---|---|---|
| `llama3.2:3b` | 3B | 2.0 GB | Sentinel Pre-filter & Sanitizer | 17,199.2 | 2,065.9 | `fast_sentinel` |
| `qwen2.5-coder:7b` | 7B | 4.7 GB | Baseline Workhorse | 6,249.7 | 2,076.7 | `fast_sentinel` |
| `qwen2.5-coder:14b` | 14B | 9.0 GB | Deep Reasoning & Refactoring Workhorse | 14,260.8 | 2,043.5 | `fast_sentinel` |
| `qwen2.5-coder:32b` | 32B | 19.5 GB | Frontier-Class Local Workhorse (Host RAM Offload) | 4,850.0 | 2,198.2 | `fast_sentinel` |

**Data quality note:** The JSON marks the 32B model `installed: false` while reporting a 4,850 ms contract latency, lower than the 3B and 14B rows. This result is internally inconsistent with the stated model availability and warrants a controlled rerun with model identity, warm/cold state, and timing method logged. It is not interpretable as a valid latency comparison as recorded.

---

### 2.4. GAIA Benchmark (Complex Agent Reasoning) Results

*Source:* [gaia_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/gaia_eval.json) & [gaia_eval.csv](file:///D:/2110001/VERITAS/veritas/research/results/gaia_eval.csv)  
*Setup:* 52 multi-modal, tool-use GAIA tasks across Levels 1, 2, and 3; 128 reasoning steps.

| Scheduler | Tasks Evaluated | Reasoning Steps | Actions Verified | Verification Rate | Cost Spent ($) | Errors Caught | Reflexion Recoveries |
|---|---|---|---|---|---|---|---|
| `never` | 52 | 128 | 0 | 0.00% | $0.00 | 0 | 0 |
| `error_x_impact` | 52 | 128 | 0 | 0.00% | $0.00 | 0 | 0 |
| `bavar_style` | 52 | 128 | 19 | 14.84% | $0.57 | 0 | 0 |
| `rc_vov` | 52 | 128 | 39 | 30.47% | $1.17 | 20 | 20 |

#### Key Insights:
- The output records `error_x_impact` selecting no actions and `rc_vov` selecting 39. Treat these as exploratory scheduler counts. The script/data do not establish that the former's zero rate reflects a generalization failure or a calibration bug; it does establish that the policy did not activate in this suite. The `20` caught errors/recoveries should not be treated as independent verified outcome evidence without auditing the outcome logic.

---

### 2.5. CSO (Contract & State Optimization) Preference Dataset

*Source:* [cso_preferences.jsonl](file:///D:/2110001/VERITAS/veritas/research/results/cso_preferences.jsonl)  
*Dataset Composition:* 23 preference pairs across GSM8K and GAIA Level 1-3 tasks. This is a small pilot artifact; it is not a meaningful training foundation for fine-tuning policy heads and should not be described as validated preference supervision.

---

### 2.6. Local System Qualification Status

*Source:* [local-qualify.json](file:///D:/2110001/VERITAS/artifacts/local-qualify.json) (Generated 2026-09-29)

```json
{
  "host": {"machine": "AMD64", "system": "Windows"},
  "docker": {"ok": true, "result": {"Architecture": "x86_64", "OSType": "linux", "ServerVersion": "29.8.0"}},
  "models": {
    "actor-llama": {"ok": true, "name": "llama3.1:8b", "revision": "46e0c10c039e..."},
    "actor-qwen": {"ok": true, "name": "qwen2.5:7b", "revision": "845dbda0ea48..."},
    "reviewer-gemma": {"ok": true, "name": "gemma3:4b", "revision": "a2af6cc3eb7f..."}
  },
  "outstanding_checks": {
    "cohort": "awareness-splits.json not yet generated",
    "grader_package": "Requires dedicated isolated virtual environment with swebench installed"
  }
}
```

---

## 3. Outstanding Work: Experiment Execution Runbook

The following is a runbook, not a record of completed experimental steps. Stages for freezing cohorts, qualification, treatment execution, grading, reporting, and gate calibration remain outstanding. Passing software tests establishes software behavior only; it does not establish the research hypothesis. The `243 passing tests` entry in the commit timeline is software engineering evidence, not empirical research evidence.

### Step 1: Fix Host Environment & Isolation Prerequisites

1. **Start Docker Desktop (Linux Container Backend):**
   Ensure Docker Desktop is active with WSL2 Linux backend (`docker ps` returns 0).
2. **Setup Dedicated Grader Environment:**
   To satisfy `veritas awareness qualify`, build a dedicated isolated virtual environment for SWE-bench evaluation:
   On Windows, create a separate environment with the pinned SWE-ReBench fork (the project environment must not also supply the grader package):
   ```bat
   uv venv --python 3.12 .venv-rebench
   uv pip install --python .venv-rebench\Scripts\python.exe -e . "swebench @ git+https://github.com/SWE-rebench/SWE-bench-fork.git@d307ff9f2168a0448843c0d5881d2cd498d9f73f"
   ```
   Set `grader.python` in `configs/awareness-local.yaml` to `.venv-rebench/Scripts/python.exe`. The awareness grader now recognizes Windows `Lib/site-packages` as well as Unix venv layouts.

### Step 2: Download & Prepare Pinned Datasets

Freeze the dataset snapshot without contamination:
```bash
# 1. Download official pinned release
uv run veritas data download --manifest configs/datasets.yaml

# 2. Normalize task rows into data/prepared
uv run veritas data prepare --manifest configs/datasets.yaml --output data/prepared --research-pool swe_rebench
```

### Step 3: Freeze Disjoint Repository Pools

Split repositories into four strictly non-overlapping pools to prevent data leakage:
```bash
uv run veritas awareness split \
  --tasks data/prepared \
  --output artifacts/awareness-splits.json \
  --seed 42
```

### Step 4: Validate System Qualification

Confirm all models, docker images, and grader dependencies pass:
```bash
uv run veritas awareness qualify \
  --config configs/awareness-local.yaml \
  --output artifacts/local-qualify.json
```
Ensure `"prerequisites_ready": true`.

### Step 5: Freeze Experimental Protocol & Plan

Generate the immutable $2 \times 2$ factorial plan ($D \in \{0, 1\} \times A \in \{0, 1\}$ with $p^* = 0.5$):
```bash
uv run veritas awareness plan \
  --config configs/awareness-local.yaml \
  --output artifacts/study
```

### Step 6: Execute Actor Inference Across Treatment Arms

Run the trials under identical budgets, isolated Docker workspaces, and frozen prompts:
```bash
uv run veritas awareness run \
  --study artifacts/study
```
*Note on Resume:* If interrupted, use `uv run veritas awareness resume --study artifacts/study` to continue without discarding existing runs.

### Step 7: Independent Blind Grading

Grade all submitted candidate patches using the isolated SWE-bench harness:
```bash
uv run veritas awareness grade \
  --study artifacts/study
```

### Step 8: Cluster-Robust Statistical Reporting

Compute the pre-registered causal contrasts with repository clustering and non-response bounds:
```bash
uv run veritas awareness report \
  --study artifacts/study
```

#### Pre-registered Estimands:
$$\text{Anticipation (Cue alone):} \quad \Delta_{\text{anticipate}} = Y_{10} - Y_{00}$$
$$\text{Correction (Feedback alone):} \quad \Delta_{\text{feedback}} = Y_{01} - Y_{00}$$
$$\text{Interaction Effect:} \quad \Delta_{\text{interaction}} = Y_{11} - Y_{10} - Y_{01} + Y_{00}$$
$$\text{Combined Verification Impact:} \quad \Delta_{\text{combined}} = Y_{11} - Y_{00}$$

### Step 9: Learn-Then-Test Gate Calibration & Transfer

1. Fit static patch-risk scorer on development pool:
   ```bash
   uv run veritas awareness fit-gate --runs artifacts/runs/dev --output artifacts/gate-model.json
   ```
2. Calibrate threshold on $D=0$ calibration pool using Hoeffding union bounds ($\alpha = 0.05$):
   ```bash
   uv run veritas awareness calibrate-gate --gate artifacts/gate-model.json --runs artifacts/runs/cal --output artifacts/gate-calibrated.json
   ```
3. Test transfer to $D=1$ confirmation pool:
   ```bash
   uv run veritas awareness gate-report --calibrated artifacts/gate-calibrated.json --runs artifacts/runs/confirm
   ```

---

## 4. Verification Checkpoint & File Manifest

| Output File | Location | Content & Purpose |
|---|---|---|
| `RESULTS.md` | [RESULTS.md](file:///D:/2110001/VERITAS/RESULTS.md) | Canonical markdown results, tables, and execution runbook. |
| `swe_100_eval.json` | [veritas/research/results/swe_100_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/swe_100_eval.json) | 100-task SWE-bench Verified policy metrics and recovery counts. |
| `extended_models_eval.json` | [veritas/research/results/extended_models_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/extended_models_eval.json) | 8-model reasoning latency, VRAM, and contract accuracy. |
| `scaling_multi_eval.json` | [veritas/research/results/scaling_multi_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/scaling_multi_eval.json) | Multi-model sentinel + workhorse speculative scaling results. |
| `gaia_eval.json` | [veritas/research/results/gaia_eval.json](file:///D:/2110001/VERITAS/veritas/research/results/gaia_eval.json) | 52-task GAIA complex agent reflexion and verification audit. |
| `cso_preferences.jsonl` | [veritas/research/results/cso_preferences.jsonl](file:///D:/2110001/VERITAS/veritas/research/results/cso_preferences.jsonl) | 23 RL/DPO preference pairs with VoV delta and cost metrics. |
| `local-qualify.json` | [artifacts/local-qualify.json](file:///D:/2110001/VERITAS/artifacts/local-qualify.json) | Host system qualification audit, Ollama tags, and docker checks. |
