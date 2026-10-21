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
