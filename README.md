# VERITAS: Evidence Selection for Repository Repair

VERITAS evaluates whether selecting fresh, runtime-visible repair evidence helps an AI coding agent
recover from initially incorrect repository patches under a matched operational budget. The primary
comparison is **Arm F (LinUCB) versus Arm C (the strongest predeclared fixed actionable-feedback
policy)**. Arm E (rule-based adaptive selection) and Arm D (fixed combined evidence) are secondary
comparators; A/B are diagnostic controls. This is an evaluation protocol over SWE-rebench, not a new
task dataset.

See [the research architecture](docs/ARCHITECTURE.md) for the research question, closest work,
experimental design, trust boundaries, metrics, and staged implementation status.

## Environment

```sh
uv sync --frozen --extra dev --extra swe
uv run veritas --help
```

The paired study has six arms: A/B diagnostic controls, C fixed actionable primary baseline,
D fixed combined, E rule-based adaptive, and F LinUCB. The primary learned comparison is F versus C.

The repository currently contains the prepared 21,336-row `nebius/SWE-rebench` release pinned in
`configs/datasets.yaml`. The separate `nebius/SWE-rebench-V2` parquet referenced by an older helper
is not present in this checkout. The active workflow uses the prepared release and records its
manifest hash in every frozen study plan.

Validate local data without model inference or Docker work:

```sh
uv run python scripts/test_dataset_with_repo.py --tasks data/prepared --source swe_rebench --limit 100
```

The staged workflow predeclares Arm C as the primary fixed comparator, uses development repositories
to freeze selector provenance, then holds out confirmation repositories. Local synthetic fixtures are for engineering
development only; benchmark-backed runs require pinned task images and official grader metadata.
See [the research architecture](docs/ARCHITECTURE.md) for the frozen protocol and remaining
implementation limits.

## End-to-end feedback-selection experiment

This is the repository-level experiment workflow for Arms A–F. It holds the agent, model, public
evidence producers, checkpoint limits, and operational budget definition common across arms; the
evidence-selection policy is the treatment. It does not include debug-versus-regenerate strategy
actions, candidate portfolios, or learned routing. Confirmation repositories are held out from
development and LinUCB training. Official grader outcomes are evaluator-side only and never enter
actor prompts, evidence, or decision-time context. Development grades are used only as post-trajectory
LinUCB reward updates on training repositories; confirmation grades never update the policy.

### 1. Install and check prerequisites

SWE-rebench has a pinned upstream harness fork that shares a package name with official SWE-bench.
Use the dedicated environment for mapping, planning, grading, and study execution:

```sh
bash scripts/setup_rebench.sh
.venv-rebench/bin/veritas --help
.venv-rebench/bin/veritas feedback-study --help
.venv-rebench/bin/veritas doctor
docker info
```

Use Linux or WSL2 with Docker available. Ensure `qwen2.5-coder:7b` (or the single predeclared actor
used for every arm) is available in the local Ollama endpoint. The runner uses
`http://localhost:11434`; keep it private. Keep the agent, model, prompt/tool configuration, and
model settings fixed across arms and between development and confirmation.

For a local Ollama setup, start the Ollama service and pull the pinned actor before starting a
study:

```sh
ollama pull qwen2.5-coder:7b
ollama list
```

The study runner does not start Ollama for you and currently uses that local endpoint directly.

### 2. Prepare and validate the pinned data

If `data/prepared` is absent or stale, download and prepare the declared SWE-rebench release:

```sh
.venv-rebench/bin/veritas data download --sources swe_rebench
.venv-rebench/bin/veritas data prepare --research-pool swe_rebench
uv run python scripts/test_dataset_with_repo.py --tasks data/prepared --source swe_rebench --limit 100
```

Generate the image map using the same task source and split as the study plan:

```sh
mkdir -p artifacts
.venv-rebench/bin/veritas swe image-map --tasks data/prepared --source swe_rebench \
  --split all --namespace '' --output artifacts/swe-rebench-image-map.json
```

This writes the JSON map and `artifacts/swe-rebench-image-map.tasks.jsonl`. Review its coverage and
grader metadata. Pull published images or build environments with the pinned fork:

```sh
.venv-rebench/bin/veritas swe pull-images artifacts/swe-rebench-image-map.json
# Alternatively, build the mapped environments (can take hours and substantial disk space):
.venv-rebench/bin/veritas swe build-images artifacts/swe-rebench-image-map.tasks.jsonl --workers 2
```

The runner pulls missing pinned images during preflight. Preflight covers every task in the frozen
plan before applying `--task-limit`, so even a 5-task execution diagnostic needs all plan images and
grader metadata available. Image setup is outside the per-branch repair budget and is recorded
separately.

### 3. Freeze a repository-disjoint plan

Choose a new, empty output directory. Do not reuse it for another plan:

```sh
.venv-rebench/bin/veritas feedback-study plan \
  --tasks data/prepared --source swe_rebench \
  --image-map artifacts/swe-rebench-image-map.json \
  --output runs/feedback-swe-rebench --seed 42 \
  --confirmation-fraction 0.2 --min-confirmation-incorrect N
.venv-rebench/bin/veritas feedback-study verify --study runs/feedback-swe-rebench
```

Replace `N` with a predeclared incorrect-parent threshold justified by the power approximation and
confirmation cohort size. If the planner rejects a small N, it prints the approximate required
threshold; choose that threshold before confirmation labels are observed and rerun the plan. The
planner rejects undersized benchmark plans; do not bypass the gate
with local fixtures and report benchmark conclusions. A 5–10 block run is only for pipeline,
accounting, evidence, and termination diagnostics, not a powered confirmation.

### 4. Run development, inspect, and freeze

**Gate:** development runs default to LinUCB learning. Do not start this step until the Phase 1
review confirms the frozen Arm C definition, all counters and termination/failure fields, budget
charging, parent/final grade separation, and usable success/failure trajectories. The current CLI
does not offer an all-arms pilot mode with LinUCB updates disabled; its 5–10 block `--task-limit`
run is a small learning run, not a pre-training pipeline check. If the project requires strictly
zero bandit updates before the pilot is accepted, add that pilot mode before proceeding.

```sh
.venv-rebench/bin/veritas feedback-study run --study runs/feedback-swe-rebench \
  --partition development --actor qwen2.5-coder:7b \
  --draft-steps 4 --revision-steps 6 --max-checkpoints 4 \
  --wall-budget-seconds 900 --budget 30
.venv-rebench/bin/veritas feedback-study analyze --study runs/feedback-swe-rebench --partition development
.venv-rebench/bin/veritas feedback-study freeze-baseline --study runs/feedback-swe-rebench --minimum-incorrect 20
```

Inspect `events.jsonl`, `results.jsonl`, `run.log`, development analysis, packet-selection records,
costs, and termination counts before confirmation. Check `patch_checkpoint_count`,
`same_patch_refresh_count`, `revision_attempt_count`, `model_call_count`, `tool_call_count`,
`credits_used`, `revision_termination_reason`, `final_patch_empty`, public-check status,
evaluator-side official-grade status, and failure category. The frozen baseline preserves
Arm C as primary and freezes the LinUCB policy and adaptive-selector provenance. Development
outcomes are descriptive. An optional diagnostic can run with `--task-limit 5` (or 10) against the
same plan; inspect `revision_termination_reason`, empty-patch rate, budget accounting, and counters.
After any implementation or protocol change, create a fresh study directory instead of mixing runs.

### 5. Screen confirmation parents, then run treatment branches

First run only the common parent drafts and evaluator-side grades:

```sh
.venv-rebench/bin/veritas feedback-study run --study runs/feedback-swe-rebench \
  --partition confirmation --parents-only --actor qwen2.5-coder:7b \
  --draft-steps 4 --revision-steps 6 --max-checkpoints 4 \
  --wall-budget-seconds 900 --budget 30
```

Review the parent-screening summary against the predeclared gate. Official/hidden grader output
must stay evaluator-side: it must never enter prompts, evidence records, or policy selection. Then
run confirmation branches with the identical settings:

```sh
.venv-rebench/bin/veritas feedback-study run --study runs/feedback-swe-rebench \
  --partition confirmation --actor qwen2.5-coder:7b \
  --draft-steps 4 --revision-steps 6 --max-checkpoints 4 \
  --wall-budget-seconds 900 --budget 30
.venv-rebench/bin/veritas feedback-study analyze --study runs/feedback-swe-rebench --partition confirmation
```

Confirmation treatment uses a frozen evaluation-only LinUCB policy and must keep the development
alpha and operational settings. Report paired F-versus-C recovery among initially incorrect parents,
full-cohort resolution,
regressions among initially correct parents, pre-existing-test regressions, infrastructure/grader
failures, per-arm costs, model/tool calls, tokens, wall time, exploration/exploitation statistics,
action counts, and termination-reason distribution. Each branch carries the common parent spend into
the same operational-credit cap and wall-time ceiling. LinUCB feature construction, selection,
updates, and offline fitting are charged to Arm F. Equal caps do not imply equal realized compute;
report resource balance and do not describe this as equal GPU/CPU compute.

The primary estimate is the paired F-minus-C recovery-rate difference among parent drafts graded
incorrect before treatment. Include every assigned pair, report its interval, and cluster uncertainty
by repository. Also report full-cohort resolution, regression among initially correct parents,
public-pass/official-fail cases, empty and non-empty incorrect patches, unknown grader/infrastructure
outcomes, and cost per resolved task. If the planned confirmation gate, power approximation, or
independent-repository requirement is not met, label the result descriptive rather than confirmatory.

Local fixtures may be used only through the explicit `--allow-local-fixtures` flag and are
engineering diagnostics, not SWE-bench evidence. Do not mix those results into benchmark estimates.

`veritas awareness` remains a separate draft/review/revision study. `veritas collect`, `compare`,
and the original controller policies are also separate and should not be treated as the proposed
feedback-selection experiment.

The new feedback-selection primitives are in `src/veritas/feedback_evidence.py` and
`src/veritas/feedback_policy.py`. `src/veritas/feedback_runtime.py` connects workspace-changing
actions to evidence invalidation, selection, and the next actor prompt through `run_phase()`.
The cohort planner and integrity checker are in `src/veritas/feedback_study.py`.

## Live evaluation and ablation dashboard

Start the dashboard from the repository root in a second Ubuntu/WSL terminal while the paired
feedback study is running. Point it at the study output directory (the directory containing
`blocks.jsonl`, `branches.jsonl`, `results.jsonl`, and `run.log`):

```sh
FEEDBACK_STUDY_DIR=runs/feedback-selection-swe-bench-lite \
FEEDBACK_LOG=runs/feedback-selection-swe-bench-lite/run.log \
python scripts/veritas_live_dashboard.py
```

Open `http://127.0.0.1:8765`. Set `FEEDBACK_STUDY_DIR` and `FEEDBACK_LOG` to your actual run
directory when it differs. The dashboard refreshes live study counts and separates the four
overall evaluation conditions (E1–E4) from the paired feedback arms (A–F). It also shows the
predeclared contrasts, component-removal plan, task and branch progress, resource use, and recent
graded outcomes. The E1–E4 panel describes the evaluation protocol; it does not imply those four
conditions were executed by the paired feedback runner. Final inference and repository-clustered
uncertainty estimates still come from the saved analysis.

## OpenHands SWE-bench Lite agent

This workflow runs OpenHands CLI and the local models in WSL/Linux, then grades with SWE-bench.
Grading uses Modal by default; set `EVAL_MODAL=false` to grade in local Docker containers.

### 1. Install host tools

Install Python 3.12, `uv`, Git, Ollama, and OpenHands CLI. Then install the project dependencies:

```sh
uv tool install openhands --python 3.12
uv sync --frozen --extra dev --extra swe
```

Pull the OpenHands actor and the Veritas verifier models:

```sh
ollama pull qwen3-coder:30b
ollama pull qwen2.5-coder:14b
```

OpenHands requires a large context. Configure Ollama for at least 32K tokens, and leave it running
while the agent runs. On macOS, set `OLLAMA_CONTEXT_LENGTH=32768` for the Ollama app with
`launchctl setenv OLLAMA_CONTEXT_LENGTH 32768`, then quit and reopen Ollama. On Linux, set the
variable in the Ollama service environment before restarting it, or start it in a terminal with
`OLLAMA_CONTEXT_LENGTH=32768 ollama serve`. The default endpoint is
`http://127.0.0.1:11434/v1`.

### 2. Set up Modal once (skip this for local Docker grading)

Create a Modal account, install its SWE-bench integration, and authenticate:

```sh
uv run --extra swe modal setup
```

### 3. Run a one-task resource pilot

```sh
EVAL_MODAL=false LIMIT=1 RUN_STAMP=pilot-1 bash scripts/run_swebench_lite_end_to_end.sh
```

The script downloads the pinned dataset if needed, runs OpenHands with Qwen3-Coder, asks Qwen2.5-Coder to review the patch, and returns actionable findings to OpenHands for up to two repair rounds. It stops early when the verifier returns PASS, then evaluates the final prediction with the SWE-bench grader. Per-task token counts (when exposed by the model/runtime), verifier usage, action-event counts, patch size, and wall time are written to `resource_report.json`; predictions, task records, and OpenHands logs are stored under `runs/`.

This is a single-condition resource-profile pilot with a reviewer/repair pass. It does not execute the paired feedback-selection branches; that executor remains a separate workflow described below.

Continue with non-overlapping slices so each task is only charged once during profiling. These use
the dataset's pinned row order; they are larger samples, not an easy-to-hard ranking.

```sh
EVAL_MODAL=false OFFSET=1 LIMIT=2 RUN_STAMP=pilot-2 bash scripts/run_swebench_lite_end_to_end.sh
EVAL_MODAL=false OFFSET=3 LIMIT=7 RUN_STAMP=pilot-7 bash scripts/run_swebench_lite_end_to_end.sh
```

For a live view in a second terminal, point the dashboard at the run folder:

```sh
SWE_LITE_DIR=runs/openhands-swe-lite-pilot-1 python scripts/veritas_live_dashboard.py
```

Open `http://127.0.0.1:8765`. It refreshes every two seconds and shows the latest OpenHands JSONL
events while a task is running, plus completed task records.

For a separate full run over all 300 Lite tasks (including tasks used in the pilot slices):

```sh
EVAL_MODAL=false OFFSET=0 LIMIT=300 RUN_STAMP=full-300 bash scripts/run_swebench_lite_end_to_end.sh
```

You can run the agent without Modal grading directly as well:

```sh
uv run --extra swe python -m veritas.openhands_swe download
uv run --extra swe python -m veritas.openhands_swe run \
  --tasks data/swebench_lite.jsonl --limit 3 \
  --model openai/qwen3-coder:30b --output runs/openhands-qwen-pilot \
  --verifier-model qwen2.5-coder:14b --max-verifier-rounds 3
```

Then grade its predictions remotely, using a new run ID for every evaluation:

```sh
uv run --extra swe \
  python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path runs/openhands-qwen-pilot/predictions.jsonl \
  --max_workers 2 --run_id openhands-qwen-pilot --modal true
```

OpenHands headless mode approves tool actions automatically, so run it in WSL or a disposable Linux
environment with only the task workspace mounted. Ollama should be reachable over a private local
network. Do not expose its API to the public internet. Set `MODEL`, `OPENHANDS_MODEL`,
`VERIFIER_MODEL`, `LLM_BASE_URL`, `VERIFIER_BASE_URL`, `LIMIT`, `MAX_VERIFIER_ROUNDS`,
`OFFSET`, `LIMIT`, `NORMAL_OUT`, or `EVAL_MODAL` to customize runs. Docker grading may download and build task images; start with a small `LIMIT`.

## Current implementation boundary

The paired executor has six arms: A/B diagnostic controls, C fixed actionable primary baseline,
D fixed combined, E rule-based adaptive, and F LinUCB. LinUCB learns on development repositories;
confirmation requires a frozen evaluation-only policy artifact. The executor, evidence/event
ledgers, independent grading, and analysis are implemented, but the full pipeline still needs a
small end-to-end pilot before it is experiment-ready.
Runtime evidence includes public issue text, static diff checks, changed-file Python syntax checks,
change-based targeted tests, and actor tool observations. The current CLI does not enable the
optional reviewer. Patch/tree/environment freshness is enforced. Packet decisions record evidence
scores and repeat delivery; actual evidence use is not reliably measured. Trajectory outcomes can
be compared with the next patch, but that does not establish causal credit for an individual packet.
A pilot must validate budget charging, resumability, termination counts, and hidden-grader isolation.
LinUCB has not yet been trained or run. See the runbook above and [architecture](docs/ARCHITECTURE.md).

All model and grader calls should be explicitly invoked through their study commands and pinned
protocols. A successful software test run validates code behavior only; it does not establish a
positive research result.
