# VERITAS

An end-to-end research implementation of risk-calibrated value of verification for
local, tool-using models. The original proposal is preserved in
[docs/original-specification.md](docs/original-specification.md).

The pipeline downloads **original published datasets**, collects natural local-model
trajectories, supports independent action adjudication, fits a critic and calibration,
estimates verifier behavior, runs matched-credit policy replay, and evaluates online
tasks. It does not generate synthetic experimental datasets or inject artificial faults.

**Start with [the step-by-step run guide](docs/RUNBOOK.md).**

## What is already available

- **52,655 original source rows, 50,897 deduplicated tasks**, downloaded to `data/`.
- Pinned dataset revisions, source checksums, duplicate removal, and frozen task splits.
- A tested Python package, CLI, locked dependencies, Docker worker, and CI configuration.
- No local LLM inference, neural fine-tuning, or benchmark evaluation has been run.
- Docker integration is included but could not be executed here because its daemon was off.

These are **task counts**, not already labeled action trajectories. Run your local model
to obtain the trajectories needed to fit and test VERITAS.

## Quick start

From this project directory:

```bash
uv sync --frozen --extra dev --extra swe
uv run veritas doctor
uv run pytest -q
```

Start Docker Desktop, then:

```bash
docker build -f Dockerfile.sandbox -t veritas-sandbox:local .
VERITAS_DOCKER_TESTS=1 uv run pytest -m integration
```

Edit the three model sections in `configs/experiment.yaml` to use your existing local
policy, critic, and verifier servers. The model names must match the servers. They can
share one server if you cannot host separate models. Backends: OpenAI-compatible local
HTTP, Ollama, or Transformers reading local weight files.

The following command **starts inference**, so it has intentionally not been run:

```bash
uv run veritas collect --config configs/experiment.yaml \
  --override configs/collection.yaml --source gsm8k_train --split dev \
  --limit 3 --output runs/first-local-check
```

Continue with collection, labeling, fitting and evaluation in [RUNBOOK.md](docs/RUNBOOK.md).

## Implemented pipeline

| Stage | Implementation |
|---|---|
| Original datasets | Pinned Hugging Face releases, JSONL, checksummed manifests |
| Task splitting | Task deduplication; domain/repository strata; 10/25/20/35/10 research partitions |
| Policy adapter | Local HTTP, Ollama, local Transformers; explicit token accounting |
| Safety floor | Strict argument schemas, AST parsing, path boundaries, derived permissions |
| Sandbox | Disposable Docker containers, no host bind mounts, no network, bounded exports |
| Tools | Files, Python, pytest, local SQLite, final answers |
| State recovery | Complete workspace snapshots, mode-aware hashes, restoration checks |
| Critic | Prompted local critic; optional TF-IDF/logistic baseline or local LoRA sequence classifier |
| Calibration | Held-out temperature scaling, NLL, ECE, Brier score |
| Verifier | Semantic falsification plus optional configured tests on a copied candidate state |
| Empirical statistics | Class-specific detection/false-alarm rates and workspace restoration evidence |
| RC-VoV | Proposal equation, dynamic threshold, exact-decimal hard credit budget |
| Observations | Credential redaction, limited instruction quarantine, provenance tags |
| Logging | Append-only SQLite hash chain; JSONL/Parquet exports; optional Fernet encryption |
| Replay | Eight gating policies, validation tuning, frozen test replay, paired task bootstrap |
| Reports | Allocation plots, metric tables, online success, tokens, budget violations, paired recovery costs |
| SWE evaluation | Official image specifications, build/pull helpers, prediction patches, upstream grading |

## Research boundaries

Read [the protocol](docs/RESEARCH_PROTOCOL.md) before interpreting results.

- A verifier verdict is not a ground-truth action label. An exit code does not establish
  semantic correctness. Unknown labels remain unknown until adjudicated.
- Replay measures allocation along recorded trajectories. Online reruns measure changed
  agent behavior and final success. No favorable outcome is hard-coded.
- The hard budget uses **fixed verifier-call credits**, not a claim of equal GPU time or
  equal token counts. Actual tokens and timings are separate measurements.
- Rollback covers the workspace, including workspace SQLite files. It cannot undo
  external emails, network effects or arbitrary system state. Those tools are not enabled.
- Regex sanitization is defense in depth, not a guarantee against prompt injection.
- This implements the core architecture and concrete SWE/GSM8K/MATH data paths. Other
  benchmark names in the proposal are documented in the
  [coverage matrix](docs/BENCHMARKS.md); they are not falsely presented as integrated.

## Main files

```text
configs/                 Dataset snapshots and local experiment settings
src/veritas/data.py       Download, normalize, deduplicate and split
src/veritas/runtime.py    Online controller/policy/tool loop
src/veritas/controller.py RC-VoV and baseline controllers
src/veritas/sandbox.py    Docker isolation and SWE workspace/patch handling
src/veritas/critic.py     Local critic training and scoring
src/veritas/calibration.py Temperature and operating-characteristic fitting
src/veritas/replay.py     Strict audit-based allocation evaluation
src/veritas/store.py      Event ledger and immutable exports
tests/                   Unit, contract, pipeline and Docker integration checks
scripts/                 Real-data validation and offline orchestration
docs/                    Run guide, sources, protocol and implementation limits
```

The small fixtures inside `tests/` are software assertions only. They are never included
in downloaded datasets, calibration artifacts, reported research results or task counts.
# VERITAS

## Local model comparison and interrupted-run diagnostics

See [COMPARISON.md](docs/COMPARISON.md) for paired, resumable terminal comparisons.
They discover installed models, retain failures, and export CSV/JSON/text.
The initial comparison measures model baselines without an unused critic; RC-VoV
policy evaluation follows once calibration evidence is adequate.

    uv run veritas diagnose-run runs/calib-pilot-v1 --artifact artifacts/calibration.json
    uv run veritas compare --output runs/math-model-pilot --sources gsm8k_train --limit 5 --execute
    uv run veritas compare --output runs/math-model-pilot --report
