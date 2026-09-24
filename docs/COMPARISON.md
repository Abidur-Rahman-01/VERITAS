# Compare installed local models and verification policies

This model-screening workflow uses real prepared tasks. It compares the same task
IDs across all selected models, using the existing tool-agent interface and
deterministic action floor. It runs without an optional verifier or critic overhead.
The default configuration screens model baselines. The same runner now supports
calibrated policy matrices; see [PERFORMANCE_UPGRADE.md](PERFORMANCE_UPGRADE.md)
for the new configurations, evidence requirements and executable next steps.
Model screening alone does not establish an RC-VoV advantage.

Run from the repository root. On Windows, first copy/sync the updated source,
configs and docs, then run:

    uv sync --frozen --extra dev --extra swe

All command examples below are single lines usable in PowerShell or a Unix shell.

## Diagnose the interrupted calibration run first

Your reported run finished 47 of 100 requested tasks, then failed. Preserve it.

    uv run veritas diagnose-run runs/calib-pilot-v1 --artifact artifacts/calibration.json

This reads files/SQLite only; it does not invoke a model. It reports the failure,
completed-task counts, semantic versus operational labels, task-group counts in the
probability-fitting role, unique critic logits, and missing calibrated action classes.

Your reported near-zero ECE is measured on the fitting subset. A constant score can
match that subset's error prevalence perfectly while providing no error ranking.
A 71.4% false-positive rate means most correctly labeled answers were rejected.
A final-answer-only calibration artifact cannot be applied to Python/file actions.
Reducing a sample-count guard does not improve those measurements. Diagnose the
actual failure and the changes made to models.py before a new calibration batch.
Keep the failed run, diagnostic retries and subsequent experiments distinct.

## Discover and plan without inference

    uv run veritas compare --output runs/model-pilot --limit 5

This reads Ollama model metadata. All installed completion-capable models are
selected. Embedding-only models are recorded as excluded. No model is downloaded.
For OpenAI-compatible local servers, set server.backend and server.base_url in
configs/comparison.yaml; discovery uses the models endpoint.
For direct Transformers, explicitly set local model paths in the models list.

The plan contains model names/digests when supplied by the server, selected original
records, original split assignments, implementation hashes, and all model/task jobs.
All models receive identical task selections and generation settings. Sampling uses
a deterministic hash, not model outcomes.

Default coverage is all sources in the prepared manifest: SWE train/dev/test,
Verified, SWE-rebench, GSM8K train/test, and MATH-500. This is the deduplicated prepared
corpus, not independent full copies of overlapping releases. Other datasets outside
the implemented adapters are not supported.

The default null split includes held-out sources. The plan prints the test-task count.
If you use outcomes to choose models, those tasks become model-selection data,
not untouched final evaluation. For development only, set split to dev and select
development sources. Verified and MATH-500 then have no matching tasks.
Preserve separate evaluation tasks for the final paper.

## First executable comparison: math

This starts local inference. Docker and the existing sandbox image must be ready.

    uv run veritas compare --output runs/math-model-pilot --sources gsm8k_train --limit 5 --execute

This smaller first run detects JSON/tool-interface incompatibility without consuming
official holdouts. To include all math sources, supply the source list:
gsm8k_train gsm8k_test math500.
MATH uses normalized exact-string grading, not full mathematical equivalence. Its
scores are not interchangeable with published symbolic-equivalence scores.

## Prepare SWE environments for the frozen selection

SWE jobs need task-specific images and the appropriate grading harness. Missing
prerequisites appear as blocked/errors. Producing a patch is not a successful solve.

For Verified, prepare exactly the tasks selected in the all-source plan:

    uv run veritas swe image-map --tasks runs/model-pilot/tasks --source swe_verified --split all --output artifacts/comparison/swe_verified.json
    uv run veritas swe pull-images artifacts/comparison/swe_verified.json

Repeat for swe_test where supported. Original swe_train and swe_dev tasks can lack
official recipes; they need repository-specific images and matching evaluation
support. A downloaded training corpus is not necessarily an executable benchmark.

SWE-rebench requires the separately installed pinned authors' fork documented in
RUNBOOK.md. Set swe.swe_rebench.python in configs/comparison.yaml to that environment's
Python. Windows: .venv-rebench/Scripts/python.exe. Linux/macOS: .venv-rebench/bin/python.

Using that environment's veritas executable:

    veritas swe image-map --tasks runs/model-pilot/tasks --source swe_rebench --split all --namespace "" --output artifacts/comparison/swe_rebench.json
    veritas swe build-images artifacts/comparison/swe_rebench.tasks.jsonl

An image map is metadata, not a build. Historical dependencies may fail.
The comparison records failures rather than discarding hard tasks.
The grader uses the configured harness Python, runs real tests, and retains its log
and report per task. Empty patches count as unsuccessful. Missing/errored test
reports remain ungraded.

## Run, resume, report

    uv run veritas compare --output runs/model-pilot --resume
    uv run veritas compare --output runs/model-pilot --report

Execution is sequential to avoid loading several large models simultaneously.
Job failures do not terminate the matrix. Each attempt has its own directory;
completed results survive interruption. Existing successes are not rerun.
Previously failed/blocked jobs require an explicit retry:

    uv run veritas compare --output runs/model-pilot --resume --retry-failed

Retries are preserved and flagged in JSON/CSV. Terminal cost columns cover latest
attempts only, not cumulative retries. Do not publish them as total project compute.
A killed process can leave .running; remove it only after checking the old process
has ended. Never launch two workers against the same output directory.

Plans are frozen. Changes to model digests, task selection, runner implementation,
or already-used image mappings require a new plan.

Terminal columns:
- Graded/N: tasks with actual outcomes versus selected tasks.
- Correct: successful tasks among those graded.
- Score: shown only when every selected task has an outcome.
- Tokens/task: shown only when the complete row has measured token usage.
- Sec/task: end-to-end job time, including SWE environment setup/grading.
- Err/Block/Pend: failed jobs, missing prerequisites, and not-yet-run jobs.

Saved files: comparison.txt, comparison.csv, comparison.json, and jobs/*/result.json.
JSON/CSV include Wilson success intervals. There is no cross-dataset average ranking:
task definitions, grading and tokenizers differ. Small pilots are diagnostics, not
reliable estimates of model superiority. APIs without weight digests cannot provide
the same identity guarantee as Ollama.

## Full scale, after the pilot works

    uv run veritas compare --output runs/all-models-full --all-tasks

Inspect the printed job count, prepare environments against runs/all-models-full/tasks,
then execute with --resume. For 50,897 prepared tasks and four models, this means
203,588 task runs before retries. Dataset availability does not imply every historical
environment runs on your hardware. No additional models or fabricated data are created.
