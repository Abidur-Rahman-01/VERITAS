# Staged feedback-selection study

This is the current workflow for image-backed repository tasks. It separates policy selection
(development repositories) from the held-out comparison (confirmation repositories). The study
runner refuses to start when a pinned task image or official grader metadata is missing; local
fixture grading requires an explicit local-pilot plan and run flag.

## 1. Prepare the pinned SWE-rebench harness

Run from the repository root in WSL/Linux with Docker and Ollama running:

```sh
bash scripts/setup_rebench.sh
```

The prepared task data must retain the original `data/prepared/manifest.json`, `tasks.jsonl`, and
`splits.json`. Generate the official image-name map for the same source and prepared split that the
study will use:

```sh
.venv-rebench/bin/veritas swe image-map \
  --tasks data/prepared --source swe_rebench --split test \
  --namespace '' --output runs/swe-rebench-test-image-map.json
```

This step makes no model calls and does not pull images. If the pinned upstream task metadata
cannot produce image names, stop: do not use the local-fixture fallback as a benchmark result.

## 2. Freeze the cohort and confirmation gate

For a 300-task cohort, the example gives development and confirmation half of the repositories
each, with a minimum of 20 initially incorrect confirmation parents before treatment branches run.
This is a screening floor only, not a formal power calculation. The earlier 60-task pilot had just
8 initially incorrect parents and used local fixtures; it cannot establish the benchmark-backed
error rate or a defensible effect size. Set final cohort size and thresholds from a predeclared
power analysis before making confirmatory claims.

```sh
.venv-rebench/bin/veritas feedback-study plan \
  --tasks data/prepared --source swe_rebench --split test \
  --image-map runs/swe-rebench-test-image-map.json \
  --limit 300 --seed 43 --confirmation-fraction 0.5 \
  --min-confirmation-incorrect 20 \
  --output runs/feedback-selection-qwen3-confirmatory

.venv-rebench/bin/veritas feedback-study verify \
  --study runs/feedback-selection-qwen3-confirmatory
```

The plan embeds the selected task metadata, source manifest, and both the full source image map and
selected image map with hashes. It refuses to create a benchmark plan if any eligible task lacks an
official image-map entry or if the requested sample exceeds the available cohort. `verify` checks
each selected task ID against the embedded prepared split map, source, pinned
image and official grader fields, as well as the frozen repository split.

## 3. Run development and choose the fixed comparator

```sh
.venv-rebench/bin/veritas feedback-study run \
  --study runs/feedback-selection-qwen3-confirmatory \
  --partition development --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120

.venv-rebench/bin/veritas feedback-study freeze-baseline \
  --study runs/feedback-selection-qwen3-confirmatory \
  --minimum-incorrect 20
```

Development must finish for every planned development block and every arm. Baseline selection
uses only recovery among initially incorrect development parents, breaking ties by lower mean
credits and then frozen arm order. It writes an immutable baseline and a snapshot of the development
results used to choose it. If fewer than 20 development parents are incorrect, increase the
development cohort under a new plan; do not lower the rule after seeing results.

## 4. Screen confirmation parents, then run the locked comparison

First create and independently grade every common parent in the confirmation partition. No
treatment branches are run in this step:

```sh
.venv-rebench/bin/veritas feedback-study run \
  --study runs/feedback-selection-qwen3-confirmatory \
  --partition confirmation --parents-only --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120
```

If the predeclared minimum of 20 incorrect parents is not met, the runner stops before confirmation
branches. Make a new, larger plan with a new seed and a predeclared threshold; do not lower the
existing threshold after inspecting confirmation outcomes.

If the gate passes, run only adaptive and the fixed baseline selected from development:

```sh
.venv-rebench/bin/veritas feedback-study run \
  --study runs/feedback-selection-qwen3-confirmatory \
  --partition confirmation --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120

.venv-rebench/bin/veritas feedback-study analyze \
  --study runs/feedback-selection-qwen3-confirmatory \
  --partition confirmation \
  > runs/feedback-selection-qwen3-confirmatory/analysis-confirmation.json
```

The runner fingerprints the installed grader and requires the pinned SWE-rebench fork from
`scripts/setup_rebench.sh`; final and parent grades go through `swebench.harness.run_evaluation`,
including its FAIL_TO_PASS and PASS_TO_PASS checks. It records the actual Docker image IDs and
platforms after pulling them. A missing image, grader mismatch, grader infrastructure error, or
invalid parent grade stops the run instead of silently falling back to local pytest fixtures.

The per-task credit ceiling includes the common parent draft, repair model tokens, actor tool time,
public evidence-check time, and selector credits. Each model call reserves the full 8,192-token
context, at least 256 completion tokens, and bounded tool time before it starts. Image setup and
private outcome grading are recorded separately and excluded from this actor-resource cap. The
reported credits are an experimental resource unit, not a dollar estimate.

The confirmation report uses a repository-cluster bootstrap for the paired recovery difference.
It also reports the number of independent repository clusters; few clusters make the interval
unstable. A successful gate and a clustered interval do not replace a predeclared power analysis.

Use a new, empty output directory for every change to the cohort, actor, phase limits, budget, or
implementation. Do not reuse the archived 60-task local-fixture study as the confirmation set.
