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

This workflow runs OpenHands CLI and the local model on the host, then uses SWE-bench's supported
Modal evaluator for grading. It does not require a local Docker daemon. Modal runs the grading
environments remotely and may incur cloud charges.

### 1. Install host tools

Install Python 3.12, `uv`, Git, Ollama, and OpenHands CLI. Then install the project dependencies:

```sh
uv tool install openhands --python 3.12
uv sync --frozen --extra dev --extra swe
```

Pull Qwen3-Coder 30B:

```sh
ollama pull qwen3-coder:30b
```

OpenHands requires a large context. Configure Ollama for at least 32K tokens, and leave it running
while the agent runs. On macOS, set `OLLAMA_CONTEXT_LENGTH=32768` for the Ollama app with
`launchctl setenv OLLAMA_CONTEXT_LENGTH 32768`, then quit and reopen Ollama. On Linux, set the
variable in the Ollama service environment before restarting it, or start it in a terminal with
`OLLAMA_CONTEXT_LENGTH=32768 ollama serve`. The default endpoint is
`http://127.0.0.1:11434/v1`.

### 2. Set up Modal once

Create a Modal account, install its SWE-bench integration, and authenticate:

```sh
uv run --extra swe modal setup
```

### 3. Run a small pilot

```sh
RUN_STAMP=qwen-pilot bash scripts/run_swebench_lite_end_to_end.sh
```

The script downloads the pinned dataset if needed, runs three tasks with normal repository
navigation and three matched tasks with oracle gold-patch file paths, then evaluates both arms on
Modal. Oracle paths are extra information, so keep those results separate from the normal score.
Predictions, task records, and OpenHands logs are stored under `runs/`.

For a live view in a second terminal, point the dashboard at the run's normal-arm folder:

```sh
SWE_LITE_DIR=runs/openhands-swe-lite-qwen-pilot python scripts/veritas_live_dashboard.py
```

Open `http://127.0.0.1:8765`. It refreshes every two seconds and shows the latest OpenHands JSONL
events while a task is running, plus completed task records. To monitor the oracle arm, restart the
dashboard with `SWE_LITE_DIR=runs/openhands-swe-lite-oracle-qwen-pilot`.

After the pilot succeeds, use `LIMIT=300` to run all Lite tasks:

```sh
LIMIT=300 bash scripts/run_swebench_lite_end_to_end.sh
```

You can run an individual arm directly as well:

```sh
uv run --extra swe python -m veritas.openhands_swe download
uv run --extra swe python -m veritas.openhands_swe run \
  --tasks data/swebench_lite.jsonl --limit 3 \
  --model openai/qwen3-coder:30b --output runs/openhands-qwen-pilot
```

Then grade its predictions remotely, using a new run ID for every evaluation:

```sh
uv run --extra swe \
  python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path runs/openhands-qwen-pilot/predictions.jsonl \
  --max_workers 2 --run_id openhands-qwen-pilot --modal true
```

The agent executes repository commands with the host user's permissions. For stronger isolation,
run it inside a disposable Linux VM, with Ollama either inside that VM or reachable over a private
network. Do not expose Ollama's API to the public internet. Set `MODEL`, `OPENHANDS_MODEL`,
`LLM_BASE_URL`, `LIMIT`, `NORMAL_OUT`, and `ORACLE_OUT` to customize runs.

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
