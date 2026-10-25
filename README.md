# VERITAS: Evidence Selection for Repository Repair

VERITAS is a research codebase for evaluating whether selecting current verifier evidence helps
AI coding agents recover from incorrect repository patches under a matched resource budget. The
primary comparison is adaptive evidence selection versus the strongest fixed actionable feedback
policy. The benchmark proposal is an evaluation protocol over SWE-rebench tasks, not a claim that
the downloaded dataset itself is a new benchmark.

See [the research architecture](docs/ARCHITECTURE.md) for the research question, closest work,
experimental design, trust boundaries, metrics, and staged implementation status.

## Environment

```sh
uv sync --frozen --extra dev --extra swe
uv run veritas --help
```

For the separate three-arm action-time verification experiment, model choices, and Docker commands, see [the Docker and WSL setup guide](docs/DOCKER_WSL_SETUP.md#action-time-tse-experiment-three-arms).

The repository currently contains the prepared 21,336-row `nebius/SWE-rebench` release pinned in
`configs/datasets.yaml`. The separate `nebius/SWE-rebench-V2` parquet referenced by an older helper
is not present in this checkout. The active workflow uses the prepared release and records its
manifest hash in every frozen study plan.

Validate local data without model inference or Docker work:

```sh
uv run python scripts/test_dataset_with_repo.py --tasks data/prepared --source swe_rebench --limit 100
```

Create and verify a repository-disjoint five-arm cohort plan:

```sh
uv run veritas feedback-study plan \
  --tasks data/prepared --source swe_rebench --limit 100 \
  --output runs/feedback-pilot
uv run veritas feedback-study verify --study runs/feedback-pilot
```

The plan contains a common-parent block for each task and five branch assignments: generic retry,
raw diagnostics, fixed actionable feedback, fixed combined feedback, and adaptive evidence
selection. The plan command only freezes the cohort and assignments; it does not run coding agents,
checks, or graders.

## Existing workflows

`veritas awareness` remains a separate draft/review/revision study. `veritas collect`, `compare`,
and the original controller policies are also separate and should not be treated as the proposed
feedback-selection experiment.

The new feedback-selection primitives are in `src/veritas/feedback_evidence.py` and
`src/veritas/feedback_policy.py`. `src/veritas/feedback_runtime.py` connects workspace-changing
actions to evidence invalidation, selection, and the next actor prompt through `run_phase()`.
The cohort planner and integrity checker are in `src/veritas/feedback_study.py`.

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

This is a single-condition resource-profile pilot with a reviewer/repair pass. It does not execute the architecture's five paired feedback-selection branches; that confirmatory executor remains separate work described below.

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

The evidence model, conservative patch/environment invalidation, five policy renderers, bounded
adaptive packet selection, prepared-data cohort planning, plan verification, and descriptive paired
analysis are implemented. The full experiment executor is still required: it must create one
common draft per block, grade and freeze that parent before treatment, replay the exact parent into
all five branches, run identical checks/reviewer steps at each patch checkpoint, enforce and log a
matched total resource cap, and persist independent grader outcomes. Do not treat a cohort plan or
the existing `awareness` runner as a completed result for the proposed study.

All model and grader calls should be explicitly invoked through their study commands and pinned
protocols. A successful software test run validates code behavior only; it does not establish a
positive research result.
