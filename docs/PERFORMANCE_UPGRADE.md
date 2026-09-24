# Performance improvements and the next experiment

The code now supports a more efficient, auditable test of the VERITAS hypothesis:
**does selective verification improve task success or avoid more consequential errors
at a declared cost, compared with strong baselines?** No success-rate improvement has
been measured by this upgrade: the local language models have not been invoked.

## What changed

- `edit_file` replaces one exact, unique text block. The model need not regenerate a
  complete source file for a small fix. Resulting Python syntax is checked before writing.
- Ordinary online actions no longer copy a checkpoint before execution. Verification
  runs before execution; configured probes use separate clones. Audit collection still
  copies/restores states to measure recovery. A rejected, unexecuted action is no longer
  logged as a measured restoration.
- The matrix skips the critic for never/always/random/impact-only policies, which do not
  need it. Scored policies include their real critic cost. This compares deployment
  efficiency against cheaper baselines; it does not give them artificial critic overhead.
- Invalid critic output is recorded with its cost and missing score. Score-dependent
  policies use an explicit verification fallback within the same credit cap. If that cap
  is exhausted, the task stops with a blocked event. Collection continues ungated with
  missing scores retained. Report fallback frequency; it is not evidence for RC-VoV.
- Verifier parse/truncation failures retain known token usage. A configured probe only
  directly rejects a **new** failing test; pre-existing failure evidence goes to the model.
- Calibration and tuning v2 keep evidence sidecars, reject overwrites, and recompute
  estimates/thresholds when loaded. Prompt/parser and relevant implementation changes
  change critic/verifier identities. Editing rates or replacing a hash cannot substitute
  for refitting on the saved evidence. These are reproducibility checks, not protection
  against an administrator rewriting the entire evidence chain.
- Validation tuning uses observed score quantiles and maximizes measured avoided impact
  minus verification credits and declared false-alarm costs. This is the declared utility
  proxy, **not** task success. The previous error-count-first objective could favor costly
  verification even with many false alarms. RC-VoV budget pacing defaults to zero; its
  optional nonzero setting is an explicit ablation, saved with tuning.
- The matrix freezes task IDs, code, settings, artifacts and available model digests;
  rotates policy order deterministically per task; preserves all attempts; grades SWE
  through the official harness; and prints missing scores/labels as N/A. Paired task
  bootstrap differences are saved in `policy_effects.json` when comparisons are complete.
- The old policy scripts now delegate to this matrix. They no longer delete run folders
  or quietly omit failed policies. Explicit `--execute` or `--resume` starts inference.

## 1. Run a small development baseline first

Start Docker and your local Ollama server. Change the model name/address in
`configs/experiment.yaml` and `configs/policy-baselines.yaml` if needed. Run from the
repository root:

```sh
uv sync --extra dev
uv run veritas doctor --config configs/experiment.yaml --check-models
docker build -f Dockerfile.sandbox -t veritas-sandbox:local .
uv run veritas compare --config configs/policy-baselines.yaml --output runs/baseline-v2
uv run veritas compare --output runs/baseline-v2 --resume
uv run veritas compare --output runs/baseline-v2 --report
```

Planning reads server metadata and freezes real tasks; it does not generate answers.
The example runs 10 GSM8K development tasks × 2 policies on one local model. Both get
the same actor, tools, task IDs, 12-step limit and verification cap. A never policy
spends zero verification credits. This pilot checks functionality, not superiority.
Use another output directory for changed settings; do not delete failed runs.

The table includes success, total online tokens/task, wall time including grading,
failures, pending jobs, known false rejections/catches and semantic label coverage.
JSON includes critic failures and fallback counts. Costs describe the latest attempt;
older attempts remain in `jobs/`. Report retries when publishing results. Latency
includes model-loading/cold-start effects; rotating order does not eliminate them.

## 2. Recollect calibration with the final configuration

Old manually edited artifacts and traces from old prompts are not valid inputs for
current online gating. Preserve them as historical diagnostics. Do not repair their IDs.

```sh
uv run veritas collect --config configs/experiment.yaml --override configs/profiles/math.yaml --override configs/collection.yaml --source gsm8k_train --split calib --limit 250 --output runs/gsm8k-calib-v2
uv run veritas collect --config configs/experiment.yaml --override configs/profiles/math.yaml --override configs/collection.yaml --source gsm8k_train --split val --limit 100 --output runs/gsm8k-val-v2
uv run veritas store export runs/gsm8k-calib-v2/events.sqlite --output artifacts/gsm8k-calib-v2-export
uv run veritas store export runs/gsm8k-val-v2/events.sqlite --output artifacts/gsm8k-val-v2-export
uv run python scripts/merge_records.py artifacts/gsm8k-calib-v2-export/events.jsonl artifacts/gsm8k-val-v2-export/events.jsonl --output artifacts/gsm8k-v2-raw.jsonl
uv run veritas labels queue artifacts/gsm8k-v2-raw.jsonl --output artifacts/gsm8k-v2-queue.jsonl
uv run python scripts/annotate_math.py --queue artifacts/gsm8k-v2-queue.jsonl --tasks data/prepared --output artifacts/gsm8k-v2-auto.jsonl
```

**Annotation is a required research step.** Auto-annotation can independently grade
GSM8K final numeric answers. It deliberately leaves intermediate Python/file actions
unknown. Independently adjudicate those queue entries and produce
`artifacts/gsm8k-v2-reviewed.jsonl` in the same annotation format before continuing.
Do not equate successful execution with semantic correctness, compare an intermediate
number with the final gold answer, or use the verifier's verdict as truth. Keep unknowns
unknown if you cannot establish a label; primary replay must wait for adequate coverage.

Apply reviewed annotations to the **raw** export, not the old incorrectly labeled file:

```sh
uv run veritas labels apply artifacts/gsm8k-v2-raw.jsonl artifacts/gsm8k-v2-reviewed.jsonl --output artifacts/gsm8k-v2-labeled.jsonl
uv run veritas calibrate artifacts/gsm8k-v2-labeled.jsonl --output artifacts/gsm8k-v2.json --min-class-samples 20
uv run veritas validate-calibration artifacts/gsm8k-v2-labeled.jsonl --artifact artifacts/gsm8k-v2.json --output artifacts/gsm8k-v2-validation.json
uv run veritas tune artifacts/gsm8k-v2-labeled.jsonl --artifact artifacts/gsm8k-v2.json --budgets 0.02 0.04 0.1 0.2 --output artifacts/gsm8k-tuning-v2.json
```

The counts above are starting batch sizes, not guarantees: each action class needs
correct and erroneous examples in the designated verifier-statistics role, plus measured
restoration. Collect more natural tasks if needed. Low-count Wilson intervals remain
wide. No script creates errors to meet the quota. Classes without sufficient evidence
use an explicit online fallback; replay rejects them. A final-answer-only artifact is
insufficient for a general action-level claim.

Check held-out AUROC, average precision, ECE, Brier, NLL, distinct scores, label/score
coverage and missing classes. Constant scores can have low ECE and no ranking value.
Do not advance on the strength of fitting-set ECE alone. A cheap optional linear critic
is supported through `critic train-linear`, `critic score`, and comparison `critic_dir`;
train only on critic_train groups, recalibrate the new scores and compare held-out
quality before assuming that its lower inference cost is a useful tradeoff.

## 3. Run the real paired policy comparison

Once the new artifacts and validation evidence pass:

```sh
uv run veritas compare --config configs/policy-comparison.yaml --output runs/policy-v2
uv run veritas compare --output runs/policy-v2 --resume
uv run veritas compare --output runs/policy-v2 --report
```

This compares never, always, confidence, error×impact and RC-VoV on development tasks.
Change the config's verification budget to each **already tuned** budget and use a new
output directory to trace the cost/quality frontier. `models: []` discovers all installed
completion models. For initial debugging keep one actor fixed; cross-model transfer of
one critic/calibration is an additional experiment, and needs held-out quality checks
on each actor's trajectories. Models unavailable on your server are not downloadable
or runnable simply because they exist publicly.

For SWE, use `configs/profiles/swe.yaml` consistently during collection and evaluation.
It gives every policy 60 steps, a 4096-token action cap and longer sandbox timeout.
These are starting limits, not an empirically optimal setting. Collect/adjudicate SWE
calibration separately, configure `configs/policy-comparison-swe.yaml`, and prepare
images for the exact frozen task selection. On Windows run the harness and preparation
inside Linux/WSL2; remove user-created fake `resource`/`sitecustomize` shims from that
new environment. No host-global Python modules are patched by VERITAS.

For a saved SWE plan whose image mapping has not yet been created:

```sh
uv run veritas swe image-map --tasks runs/swe-policy-v2/tasks --source swe_test --split dev --output artifacts/swe-policy-dev-map.json
uv run veritas swe pull-images artifacts/swe-policy-dev-map.json
```

Some releases require building supported images first; follow RUNBOOK.md. A patch's
existence or length never establishes success. Missing official grades stay ungraded.

## 4. Decide whether the research goal was met

Fix settings using development/validation only. Then predeclare the task selection,
budgets, primary endpoint, acceptable quality tradeoff and stopping rule before testing
untouched groups. Compare identical tasks, include critic/verifier/replanning tokens and
all failures, and inspect actual spend as well as the common cap.

A defensible positive result is higher independently graded success at comparable total
cost, or lower total cost at a predeclared acceptable success difference, with adequate
paired task uncertainty. Fewer verifier calls alone is not enough. A 10–20 task pilot
is insufficient for a broad superiority claim. Use more real tasks and, where relevant,
repeated model seeds. Do not choose models/prompts/thresholds from test-set scores.

SWE resolution and GSM8K numeric accuracy remain separate metrics; MATH currently uses
conservative exact-string grading and can undercount equivalent answers. There is no
scientific justification for an unqualified overall rank across them.

## Verification of this upgrade

Software tests cover invalid/truncated model responses and their costs, budgeted missing
score fallback, removal of online checkpoint copies, preservation of audit restoration,
exact edits, differential test probes, artifact/tuning modification detection, held-out
calibration checks, paired matrix execution/resume, official-grade requirements and
unknown-label reporting. Test fixtures are not experimental datasets.

The installed original-data files were revalidated: 52,655 source rows, 50,897 unique
tasks; source hashes and research partitions passed; no synthetic experimental records
were generated. Docker's daemon was unavailable in this workspace, so the real Docker
integration test and local model runs remain to be executed on your machine.
