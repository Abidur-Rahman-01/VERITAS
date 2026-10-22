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

## LangGraph SWE-bench Lite agent

The optional coding-agent path uses three LangGraph nodes: fault localization, patch generation,
and a verifier. The verifier checks that a unified diff applies cleanly, changes repository files,
passes `git diff --check`, and receives a valid `PASS` from the configured review model. Verifier
errors and malformed responses fail closed and can trigger another repair attempt. This review
does not run the task tests, and it cannot guarantee patch correctness. Final task success is
measured separately with the official SWE-bench Docker evaluator.

Build the Docker image (it installs LangGraph and the SWE-bench harness), then download
the pinned 300-task Lite test split:

```sh
docker compose build swe-langgraph
docker compose run --rm --entrypoint python swe-langgraph -m veritas.langgraph_swe download
```

Build the benchmark's isolated task environments before evaluation (this downloads/builds up to
300 repository images and needs substantial disk space):

```sh
docker compose run --rm --entrypoint veritas veritas swe build-images data/swebench_lite.jsonl --workers 2
```

Ollama must be running on the host with a coding model already pulled. Run a small pilot first:

```sh
OLLAMA_HOST=http://host.docker.internal:11434 docker compose run --rm swe-langgraph run \
  --tasks data/swebench_lite.jsonl --model codestral:22b --limit 3 \
  --output runs/langgraph-swe-lite-pilot
```

`predictions.jsonl` is compatible with the official evaluator. On Linux with Docker available and
SWE-bench task images built or pulled, evaluate the pilot with:

```sh
docker compose run --rm --entrypoint python swe-langgraph -m swebench.harness.run_evaluation \
  --dataset_name data/swebench_lite.jsonl \
  --predictions_path runs/langgraph-swe-lite-pilot/predictions.jsonl \
  --max_workers 2 --run_id langgraph-lite-pilot --namespace swebench
```

For the full benchmark run, omit `--limit` and give the run a separate output directory. Build the
task images once, then point the official evaluator at that run's `predictions.jsonl`.

To measure repair/verifier behavior when repository navigation is removed as a confound, run the
same tasks with `--oracle-localization`. This supplies only paths parsed from each gold patch; it
does not reveal patch contents. The output records `oracle_localization: true` and
`localization_mode: oracle_gold_patch_paths`. Treat these scores as a separate oracle ablation,
never as the ordinary SWE-bench score. The model-localized run is the normal benchmark setting.

```sh
docker compose run --rm swe-langgraph run --tasks data/swebench_lite.jsonl \
  --model codestral:22b --limit 3 --oracle-localization \
  --output runs/langgraph-swe-lite-oracle-pilot
```

To run both full 300-task arms and their official evaluations sequentially, use the guarded
one-shot runner. It checks Docker, Ollama, and both model tags before it builds task images:

```sh
bash scripts/run_swebench_lite_end_to_end.sh
```

Override `MODEL`, `VERIFIER_MODEL`, `IMAGE_WORKERS`, or `EVAL_WORKERS` in the environment to
match the models and machine. The full run can take hours and needs substantial disk space.

The current verifier is a patch-integrity gate, not a per-step test runner. Only the official
Docker evaluation outcome establishes SWE-bench task resolution. The agent checks out each task's
declared `base_commit`; use the official evaluator's task images to run the benchmark tests.

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
