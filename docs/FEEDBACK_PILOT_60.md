# VERITAS 60-task feedback-selection pilot

This guide sets up the paired five-arm pilot on a fresh Linux machine or Windows with WSL2. It
does not start model inference until the `run` command below. The pilot has 60 SWE-rebench tasks and
five paired continuations per task (300 branch runs), plus one shared draft and parent grade per
task.

## What this pilot can tell you

Every arm for a task starts from the same frozen parent patch. The five arms are generic retry, raw
diagnostics, fixed actionable feedback, fixed combined feedback, and adaptive evidence selection.
The main descriptive comparison is adaptive versus fixed actionable, among tasks where the shared
parent patch does not resolve the task.

This first pilot uses public issue text, `git diff --check`, syntax checks on changed Python files,
and actor tool output as evidence. It does not call a model reviewer. Actor phase limits match across
arms; estimated costs and latency are recorded, but a single hard total-cost cap is not enforced.
Use the results to validate the pipeline and estimate behavior. They do not establish that adaptive
selection is superior or cost-effective. The `confirmation` partition is reserved in the plan, but
this pilot's analysis is descriptive and should not be treated as a held-out confirmatory study.

## 1. Prepare the other PC

Use Ubuntu/Linux, or WSL2 with Docker Desktop integration enabled. Install Git, Python 3.11–3.13,
`uv`, Docker, and Ollama. Docker must be running, and Ollama must serve its API at
`http://localhost:11434` on the machine where the commands below run. From the project root:

```sh
uv sync --frozen --extra dev --extra swe
ollama pull qwen2.5-coder:7b
docker info
ollama list
```

If the first machine's `data/prepared` directory is available, copy it intact to the new checkout;
it is about 1.2 GB and includes the original dataset manifest and integrity hashes. Otherwise,
download the pinned SWE-rebench release and prepare it locally:

```sh
uv run veritas data download --sources swe_rebench --output data/raw
uv run veritas data prepare --raw data/raw --output data/prepared \
  --research-pool swe_rebench --seed 42
```

Dataset preparation downloads roughly 21,336 tasks. It can take time and needs an internet
connection. The runner also pulls each required SWE-rebench task image from Docker Hub on demand;
allow substantial disk space for these images.

## 2. Freeze and verify the 60-task cohort

Run once from the repository root. The output directory must be new or empty:

```sh
uv run veritas feedback-study plan \
  --tasks data/prepared --source swe_rebench --limit 60 --seed 42 \
  --confirmation-fraction 0.2 --output runs/feedback-selection-pilot-60
uv run veritas feedback-study verify --study runs/feedback-selection-pilot-60
```

The plan command does not run agents. It creates the selected task list, one shared-parent block per
task, five arm assignments per block, a protocol, and hashes. Keep the whole directory unchanged
and back it up with the final results.

## 3. Run one end-to-end smoke task

This makes real model calls and Docker grading for one task across all five arms:

```sh
uv run veritas feedback-study run \
  --study runs/feedback-selection-pilot-60 --actor qwen2.5-coder:7b \
  --draft-steps 4 --revision-steps 6 --budget 30 --task-limit 1
```

Before continuing, check that `runs/feedback-selection-pilot-60/results.jsonl` has five rows, that
`blocks/` contains the parent patch and five branch patches, and that each branch has `grade.json`
and `events.jsonl`. Inspect any `infrastructure_error` status and fix Docker/Ollama setup before
the full run. The `--budget 30` value is recorded as a reference only; it does not stop a branch
when estimated cost reaches 30.

## 4. Run all 60 tasks

The same command without `--task-limit 1` resumes the smoke task and continues through the remaining
tasks. It can take many hours and use substantial model compute, Docker storage, and network
bandwidth for task images:

```sh
uv run veritas feedback-study run \
  --study runs/feedback-selection-pilot-60 --actor qwen2.5-coder:7b \
  --draft-steps 4 --revision-steps 6 --budget 30
```

If the machine shuts down or the run stops, issue the same command again. The runner resumes
completed branches and reuses completed parent drafts. Do not change the actor, step limits, budget
value, or code in the same study directory: the execution protocol pins these settings and code
hashes. Start a new output directory for a different configuration.

## 5. Create the analysis report

```sh
uv run veritas feedback-study analyze \
  --study runs/feedback-selection-pilot-60 \
  > runs/feedback-selection-pilot-60/analysis.json
```

The report includes each arm's planned/recorded/graded counts, resolved and unresolved tasks, empty
patches, grader infrastructure errors, resolution intervals, repository-level summaries, and the
paired adaptive-versus-fixed-actionable outcomes. A grader infrastructure error is unknown, not an
unresolved task. Review denominators and missing rows before comparing rates.

Keep `plan.json`, `protocol.json`, `execution_protocol.json`, `results.jsonl`, `analysis.json`, and
the `blocks/` logs together. These are the audit trail needed to reproduce and explain the result.
