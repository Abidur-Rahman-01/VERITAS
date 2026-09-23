# Run VERITAS step by step

The code and real datasets are prepared. **You supply and start the local models.**
No command that performs model inference or neural training was run during development.
Start with a few tasks, verify the environment, then remove `--limit` to scale.

## 1. Install and validate

Use Python 3.12. Linux with Docker is the most straightforward SWE execution environment;
macOS can use Docker Desktop. Choose CPU/GPU resources according to your local models.

```bash
cd "/Users/sadik/AAI Project/Veritas"
uv sync --frozen --extra dev --extra swe
source .venv/bin/activate
veritas doctor
pytest -q
```

On another machine, copy the repository and use its directory instead. `uv.lock` is the
dependency lock; do not silently upgrade packages during an experiment.

Start Docker Desktop or the Linux Docker service. Then:

```bash
docker build -f Dockerfile.sandbox -t veritas-sandbox:local .
VERITAS_DOCKER_TESTS=1 pytest -m integration
```

This integration test uses ordinary program assertions, not an LLM or research dataset.
The developer machine had no running Docker daemon, so this remains a required local
runtime check before collecting experimental trajectories.

## 2. Point the adapters at your local models

Edit `configs/experiment.yaml`. There are separate `model`, `critic`, and `verifier`
sections. You may use the same local server for multiple roles. A shared critic and
verifier still need independent ground-truth adjudication; they are not independent judges.

For vLLM, llama.cpp or LM Studio with a compatible endpoint:

```yaml
model:
  backend: openai_compatible
  base_url: http://127.0.0.1:8000/v1
  name: local-policy
  api_key_env: VERITAS_API_KEY
  max_tokens: 2048
  timeout_seconds: 180
  temperature: 0.0
```

The served model name must match exactly. An optional `VERITAS_API_KEY` is read only from
your environment. No paid/cloud-model client or service is required. Start your existing
model server using its own installation. For an already installed vLLM server, an example is:

```bash
vllm serve /absolute/path/to/policy-model --served-model-name local-policy --port 8000
# In another terminal, if hardware permits a separate critic:
vllm serve /absolute/path/to/critic-model --served-model-name local-critic --port 8001
```

For Ollama, use `backend: ollama`, `base_url: http://127.0.0.1:11434` and a model name
already installed in your Ollama instance. `configs/ollama.yaml` shows all three roles;
copy those values into your experiment configuration. Do not add `/v1` for this backend.

For direct Transformers, install `uv sync --frozen --extra dev --extra swe --extra train`,
use `backend: transformers`, and set `name` to an absolute local model directory. Model
loading uses `local_files_only=True`. Hardware-heavy dependencies are optional and
were not loaded/tested against real weights here.

Check HTTP metadata without inference:

```bash
veritas doctor --check-models
```

Model context limits still apply. Reduce `run.history_chars`, select a model with adequate
context, or increase `max_tokens` if JSON is truncated. Malformed proposals are rejected
by the floor and fed back for replanning.

## 3. Use the downloaded real datasets

The project already contains `data/raw`, `data/prepared` and source checksum manifests.
Validate them:

```bash
python scripts/validate_real_data.py
```

To reproduce the data preparation on a fresh machine:

```bash
veritas data download
veritas data prepare --research-pool swe_test swe_rebench
```

Downloading with no `--limit` fetches full pinned releases. Preparation refuses to
overwrite an existing frozen manifest. For a different seed/protocol, choose a new
`--output` directory and pass it with `--tasks` on subsequent commands.

The declared research pool enables the five-way split for non-Verified SWE issues and
SWE-rebench. Verified, official GSM8K test and MATH-500 remain held out. Do not call a result
on this repartitioned corpus an official full-SWE-bench or SWE-rebench leaderboard score.
For the conservative alternative, omit `--research-pool`; a prebuilt copy exists at
`data/prepared-conservative`. See [the protocol](RESEARCH_PROTOCOL.md).

## 4. First local inference check

This is the first command that actually runs your model:

```bash
veritas collect --config configs/experiment.yaml --override configs/collection.yaml \
  --source gsm8k_train --split dev --limit 3 --output runs/dev-smoke
veritas online-report runs/dev-smoke/summaries.jsonl --output runs/dev-smoke/metrics.json
```

Inspect `runs/dev-smoke/*/summary.json` and the event export. Development outcomes are
for debugging, not reported final results. Collection mode audits all actions but does
not let the optional verifier change the policy's baseline trajectory. These audit calls
cost local compute; their tokens are accounted separately.

## 5. Collect calibration, validation and test trajectories

For a first complete math experiment:

```bash
veritas collect --override configs/collection.yaml --source gsm8k_train --split calib \
  --output runs/math-calib
veritas collect --override configs/collection.yaml --source gsm8k_train --split val \
  --output runs/math-val
veritas collect --override configs/collection.yaml --source gsm8k_test --split test \
  --output runs/math-test

veritas store export runs/math-calib/events.sqlite --output artifacts/math-calib
veritas store export runs/math-val/events.sqlite --output artifacts/math-val
veritas store export runs/math-test/events.sqlite --output artifacts/math-test

python scripts/merge_records.py artifacts/math-calib/events.jsonl \
  artifacts/math-val/events.jsonl artifacts/math-test/events.jsonl \
  --output artifacts/math-actions.jsonl
```

Run SWE tasks as described in section 10, and merge their exported records similarly.
Collect enough **natural** correct and erroneous actions in each class. There is no
synthetic augmentation when a class is rare. `data/prepared/splits.json` contains each
task's outer partition and its group-disjoint inner calibration role.

Each run directory is immutable and intentionally refuses reuse. Use a new name for
another attempt. A failed run writes `failure.json`; completed task records remain in
the append-only database. Do not count an incomplete run as successful.

## 6. Adjudicate action correctness

GSM8K final answers can be labeled against the official answer. Intermediate actions,
and most SWE actions, need meaningful independent checks or expert review. A successful
command is not automatically a correct action. The program keeps these labels unknown.

```bash
veritas labels queue artifacts/math-actions.jsonl --output artifacts/annotation-queue.jsonl
```

Edit the queue or produce an annotation file from your adjudication process. For each
event set `error_label` to 0 or 1, `label_scope` to `semantic`, and `label_source` to an
evidence reference such as a test report plus reviewer ID. Do not label from the same
verifier output you are evaluating. Unknown entries remain null.

```bash
veritas labels apply artifacts/math-actions.jsonl artifacts/annotation-queue.jsonl \
  --output artifacts/labeled-actions.jsonl
```

Queues hide verifier/critic outputs to reduce confirmation bias. Ground-truth labels
already collected in the source records are preserved when queue entries remain null.
Review the task, action and prior context; failed test execution can be a useful action.

## 7. Fit the error estimator and calibrate it

**Option A — keep your prompted local critic.** Its raw scores are already recorded:

```bash
veritas calibrate artifacts/labeled-actions.jsonl --output artifacts/calibration.json
```

**Option B — train a small transparent baseline critic:**

```bash
veritas critic train-linear artifacts/labeled-actions.jsonl --output artifacts/linear-critic
veritas critic score artifacts/labeled-actions.jsonl --critic-dir artifacts/linear-critic \
  --output artifacts/scored-actions.jsonl
veritas calibrate artifacts/scored-actions.jsonl --output artifacts/calibration.json
```

**Option C — fine-tune your local sequence critic with LoRA:**

```bash
uv sync --frozen --extra dev --extra swe --extra train
veritas critic train-lora artifacts/labeled-actions.jsonl \
  --model-path /absolute/path/to/local/critic-model --output artifacts/lora-critic \
  --epochs 2 --batch-size 1 --accumulation 16 --max-length 2048
veritas critic score artifacts/labeled-actions.jsonl --critic-dir artifacts/lora-critic \
  --output artifacts/scored-actions.jsonl
veritas calibrate artifacts/scored-actions.jsonl --output artifacts/calibration.json
```

Training uses only `critic_train`; temperature uses `probability`; detection/false-alarm
and recovery fitting use `verifier_stats`. Fitting requires at least ten probability
records with both classes, plus at least five correct/five erroneous records and
restoration evidence for a verifier class. These are minimum guards, not a power analysis.

If a required class has no fitted statistics, collect and adjudicate more real traces.
The runtime does not silently invent d/f/rho values. Change `--min-class-samples` only
as a declared methodological choice. Models are loaded locally; nothing is uploaded.

Use `artifacts/scored-actions.jsonl` in the remaining commands if you trained a new critic;
otherwise use `artifacts/labeled-actions.jsonl`.

## 8. Tune, replay and plot

For the prompted-critic path:

```bash
veritas tune artifacts/labeled-actions.jsonl --artifact artifacts/calibration.json \
  --output artifacts/tuning.json --budgets 0.02 0.04 0.1 0.2 0.4
veritas replay artifacts/labeled-actions.jsonl --artifact artifacts/calibration.json \
  --tuning artifacts/tuning.json --output artifacts/test-replay \
  --budgets 0.02 0.04 0.1 0.2 0.4
veritas report artifacts/test-replay
```

Alternatively, `bash scripts/run_offline.sh artifacts/labeled-actions.jsonl artifacts/offline`
performs all three stages. It rejects incomplete labels, missing audit verdicts, fitting
overlap, changed critic/verifier identities and untuned budgets.

Outputs: `frontier.jsonl`, `per_task.jsonl`, `paired_bootstrap.json`, `frontier.png`,
`frontier.pdf`, `report.md` and a manifest. These are replay allocation results only.

## 9. Run the actual online comparisons

Reuse frozen validation thresholds and a matching calibration artifact:

```bash
for policy in confidence risk error_impact bavar_style rcvov; do
  veritas collect --source gsm8k_test --split test \
    --artifact artifacts/calibration.json --tuning artifacts/tuning.json \
    --policy "$policy" --budget 0.2 --output "runs/online-$policy"
  veritas online-report "runs/online-$policy/summaries.jsonl" \
    --output "runs/online-$policy/metrics.json"
done
```

If you trained a critic, include `--critic-dir artifacts/linear-critic` or your LoRA
directory on every online collection. Calibration checks the scorer/verifier identity.
Do not use `configs/collection.yaml` for online comparisons; it turns gating off.

For a recovery ablation, run the same policy/tasks/budget once in default checkpoint
mode and once with `--override configs/restart.yaml`, then:

```bash
veritas recovery-report runs/online-rcvov/summaries.jsonl \
  runs/online-rcvov-restart/summaries.jsonl --output artifacts/recovery-comparison.json
```

For backbone transfer, change only the policy model, collect actual `--split backbone`
trajectories, and keep calibration/critic/verifier fixed. Use new output directories.

## 10. SWE-bench: real repository tasks and official grading

Prepare a small Verified smoke batch first:

```bash
veritas swe image-map --source swe_verified --split test --limit 2 \
  --output artifacts/verified-images.json
veritas swe pull-images artifacts/verified-images.json
veritas collect --override configs/collection.yaml --source swe_verified --split test \
  --limit 2 --images artifacts/verified-images.json --output runs/swe-smoke
```

Public SWE images generally use x86_64. On Apple Silicon set
`sandbox.platform: linux/amd64` in your config when using those images. Native builds
can instead use `--arch arm64`, where upstream dependencies support it.

For calibration from the declared **non-Verified** `swe_test` research pool, map and
collect `--source swe_test --split calib`. Repeat for `val`; this does not use the
reserved Verified tasks for fitting. All runs need the corresponding image map.

For local builds instead of public pulls:

```bash
veritas swe image-map --source swe_test --split calib --limit 2 --namespace '' \
  --output artifacts/swe-calib-local.json
veritas swe build-images artifacts/swe-calib-local.tasks.jsonl --workers 2
veritas collect --override configs/collection.yaml --source swe_test --split calib \
  --limit 2 --images artifacts/swe-calib-local.json --output runs/swe-calib
```

The original 19,008-row `swe_train` corpus is valid source data but its repository
environments are not included in the installed official harness. It needs supplied
repository-specific image recipes before online use; the CLI reports this explicitly.
Do not use the generic math image to claim SWE issue resolution.

Predictions are exported to `runs/swe-smoke/predictions.jsonl` in official format.
First inspect the grading command, then execute it:

```bash
veritas swe evaluate --dataset artifacts/verified-images.tasks.jsonl \
  --predictions runs/swe-smoke/predictions.jsonl --run-id swe-smoke-eval
veritas swe evaluate --dataset artifacts/verified-images.tasks.jsonl \
  --predictions runs/swe-smoke/predictions.jsonl --run-id swe-smoke-eval --execute
```

For locally built images add `--namespace ''`. Use a new grading `--run-id` for changed
predictions because the official harness caches results. Supply the resulting upstream
summary JSON to `veritas online-report ... --swe-report PATH`. SWE success remains null
until this grading step. The official harness evaluates gold test patches out of the
policy's view; the policy is never given reference solution patches.

## 11. SWE-rebench at larger scale

The 21,336 original issues include task-specific installation recipes. Use the authors'
pinned fork in a separate environment; it shares the package name `swebench`:

```bash
bash scripts/setup_rebench.sh
.venv-rebench/bin/veritas swe image-map --source swe_rebench --split calib --limit 2 \
  --namespace '' --output artifacts/rebench-images.json
.venv-rebench/bin/veritas swe build-images artifacts/rebench-images.tasks.jsonl --workers 2
.venv-rebench/bin/veritas collect --override configs/collection.yaml \
  --source swe_rebench --split calib --limit 2 --images artifacts/rebench-images.json \
  --output runs/rebench-calib
```

If a task provides an upstream prebuilt image, `image-map` uses it; pull that image instead
of building a local name. Run grading using the same fork/environment and matching
namespace. Docker builds can be large and upstream historical dependencies can fail;
build success is checked explicitly. The fork's source integration was prepared, but
its actual image builds and evaluations were not executed on this machine.

## 12. Freeze and encrypt records when needed

```bash
veritas store verify artifacts/math-calib
export VERITAS_EXPORT_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
veritas store export runs/math-calib/events.sqlite --output artifacts/encrypted-calib \
  --encrypt-env VERITAS_EXPORT_KEY
veritas store decrypt artifacts/encrypted-calib/events.jsonl.fernet \
  --output artifacts/decrypted-calib.jsonl
```

Save the key securely outside exported data. Encryption does not retroactively encrypt
the original SQLite event store. Preserve config, source revision/hash, image digest,
model identity, annotation evidence, calibration artifact and tuning artifact for each
experiment. Full troubleshooting and implementation limits are in the other docs.
