# Staged feedback-selection study on SWE-bench Lite

This workflow runs the VERITAS feedback-selection study on a repository-disjoint split of the
pinned SWE-bench Lite test cohort. SWE-bench Lite contains 300 test instances; dividing those
repositories into development and confirmation means the resulting confirmation subset is an
internal held-out comparison, not a standard score on all 300 Lite tasks. The [official SWE-bench
evaluation guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md) uses
`swebench.harness.run_evaluation` for Lite.

The runner requires the canonical task metadata, official image map, and pinned official grader.
Local fixture grading is available only when both planning and execution explicitly opt into it.

## 1. Prepare the locked official SWE-bench harness

Run from the repository root in WSL/Linux with Docker, Ollama, and `uv` installed:

```bash
cd /mnt/f/Sadik/VERITAS
set -euo pipefail
export PYTHONUNBUFFERED=1
uv sync --frozen --extra dev --extra swe
ollama show qwen3-coder:30b >/dev/null
docker info >/dev/null
```

The dataset revision is pinned to
[`6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite/commit/6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2).
Download and prepare only that dataset into its own immutable directory:

```bash
uv run --extra swe veritas data download \
  --manifest configs/datasets.yaml --sources swe_bench_lite \
  --output data/raw-swe-bench-lite

uv run --extra swe veritas data prepare \
  --manifest configs/datasets.yaml --raw data/raw-swe-bench-lite \
  --output data/prepared-swe-bench-lite --seed 43
```

Generate official image names for all 300 Lite test tasks:

```bash
uv run --extra swe veritas swe image-map \
  --tasks data/prepared-swe-bench-lite --source swe_bench_lite --split test \
  --namespace swebench \
  --output runs/swe-bench-lite-test-image-map.json
```

## 2. Freeze and verify the repository-disjoint cohort

The example assigns half the repositories to development and half to confirmation. It requires at
least 20 initially incorrect confirmation parents before running treatment branches. That is an
operational screening gate, not a formal power calculation. Your earlier fixture pilot cannot
establish the Lite parent-error rate or an effect size; predeclare a power analysis before making
confirmatory claims.

```bash
uv run --extra swe veritas feedback-study plan \
  --tasks data/prepared-swe-bench-lite --source swe_bench_lite --split test \
  --image-map runs/swe-bench-lite-test-image-map.json \
  --limit 300 --seed 43 --confirmation-fraction 0.5 \
  --min-confirmation-incorrect 20 \
  --output runs/feedback-selection-swe-bench-lite

uv run --extra swe veritas feedback-study verify \
  --study runs/feedback-selection-swe-bench-lite
```

The plan embeds the selected task metadata, prepared manifest and splits, and both the source and
selected image maps with hashes. Verification checks each task ID and source revision, pinned image,
official grading fields, and repository assignment.

## 3. Select the fixed comparator on development repositories

```bash
uv run --extra swe veritas feedback-study run \
  --study runs/feedback-selection-swe-bench-lite \
  --partition development --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120 2>&1 \
  | tee -a runs/feedback-selection-swe-bench-lite/run.log

uv run --extra swe veritas feedback-study freeze-baseline \
  --study runs/feedback-selection-swe-bench-lite --minimum-incorrect 20 \
  2>&1 | tee -a runs/feedback-selection-swe-bench-lite/run.log
```

Development must finish for every planned block and arm. The fixed comparator is selected by
recovery among initially incorrect development parents, then lower mean credits, then frozen arm
order. Fewer than 20 incorrect development parents stops baseline selection.

## 4. Screen confirmation parents, then run the locked comparison

Start the live dashboard in a second terminal before running the model stages. It refreshes from
the plan, parent grades, result ledger, event stores, and appended executor log:

```bash
cd /mnt/f/Sadik/VERITAS
FEEDBACK_STUDY_DIR=runs/feedback-selection-swe-bench-lite \
FEEDBACK_LOG=runs/feedback-selection-swe-bench-lite/run.log \
uv run --extra swe python scripts/veritas_live_dashboard.py
```

Open `http://localhost:8765`. The dashboard shows 300-task stage progress, parent correctness,
all 1,500 planned arm outcomes, per-arm resolution/recovery/regression, actor tokens before and
after verifier feedback, estimated resource credits, grader status, and the active task/arm.

First grade every confirmation parent without running treatment branches:

```bash
uv run --extra swe veritas feedback-study run \
  --study runs/feedback-selection-swe-bench-lite \
  --partition confirmation --parents-only --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120 2>&1 \
  | tee -a runs/feedback-selection-swe-bench-lite/run.log
```

If fewer than 20 initially incorrect parents are found, the runner stops before treatment branches.
Do not lower the threshold after observing the screen.

If the gate passes, run all five arms on confirmation. Adaptive versus the development-selected
fixed arm remains the primary contrast; the other confirmation arm results are secondary:

```bash
uv run --extra swe veritas feedback-study run \
  --study runs/feedback-selection-swe-bench-lite \
  --partition confirmation --actor qwen3-coder:30b \
  --draft-steps 4 --revision-steps 10 --budget 120 2>&1 \
  | tee -a runs/feedback-selection-swe-bench-lite/run.log

uv run --extra swe veritas feedback-study analyze \
  --study runs/feedback-selection-swe-bench-lite --partition confirmation \
  > runs/feedback-selection-swe-bench-lite/analysis-confirmation.json
```

The runner requires the lockfile-pinned official `swebench` package and grades parent and final
patches through `swebench.harness.run_evaluation`, including FAIL_TO_PASS and PASS_TO_PASS. It
records Docker image IDs and platforms. Missing image metadata, grader mismatch, or an unknown
parent grade stops the run instead of falling back to local pytest fixtures.

The per-task actor-resource ceiling includes the common parent draft, repair model tokens, actor
sandbox time, public evidence-check time, and selector credits. Model calls reserve the full
8,192-token context, at least 256 completion tokens, and bounded tool time. Image setup and private
grading are recorded separately and excluded from that actor-resource cap. Credits are experimental
resource units, not dollars.

Use a new output directory if you change the cohort, actor, phase limits, budget, or implementation.
Do not use the archived 60-task local-fixture study as benchmark evidence.

The setup shell exports `PYTHONUNBUFFERED=1` and enables `set -euo pipefail`, so log lines stream
to the dashboard and a failed command or pipeline stops the staged run.
