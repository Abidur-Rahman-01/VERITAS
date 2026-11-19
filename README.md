# VERITAS

**Actor-relative evidence value for coding-agent harnesses.** VERITAS measures how much each
piece of harness evidence (test failures, tracebacks, contrast pairs, runtime values, localization
findings, plans, rubrics) helps or hurts a *specific* repair agent at a *specific* state. It
predicts that value from the agent's own hidden states and uses the prediction to decide what to
deliver. The research design, literature review and analysis plan are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

This README has two parts:
- **Experimental setup:** what is measured and how; read it first.
- **Runbook (§1–§13):** takes a fresh machine from nothing to the final report. Follow the steps
  in order, running every command from the repository root.

---

## 0. What the experiment uses

Everything is downloaded from public sources at pinned commits, so every machine gets
byte-identical inputs.

| Input | Source (Hugging Face / Docker Hub) | Pinned revision | Licence |
|---|---|---|---|
| Task dataset | `nebius/SWE-rebench-V2`, split `train`, Python tasks only | `d7608f017a29ab256400ad4b73d5248d97204966` | CC-BY-4.0 (per-repository licences apply) |
| Actor 1 | `Lego-X/SWE-Lego-Qwen3-8B` | `00f37992485b78e9579a2674161d512781aee21e` | Apache-2.0 |
| Actor 2 (optional, RQ5) | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | `b2cff646eb4bb1d68355c01b18ae02e7cf42d120` | Apache-2.0 |
| Actor 1 training tasks (excluded) | `Lego-X/SWE-Lego-Real-Data`, `Lego-X/SWE-Lego-Synthetic-Data` | `879c96b…`, `3e74554…` (full hashes in `configs/study.yaml`) | — |
| Task environments | `docker.io/swerebenchv2/*`, one image per task | named in the dataset | — |

**Why this dataset.** Tasks must be newer than the actor's training data, or the gold patch may
be memorized and the measurements inflated. SWE-Lego was fine-tuned on SWE-rebench tasks created
up to 2025-04-30. In the older SWE-rebench (V1) snapshot, 273 of the 307 tasks that pass the
other filters are SWE-Lego training tasks. SWE-rebench-V2 has Python tasks from after that date,
so the study uses V2 tasks created on or after **2025-05-01**. It also removes every SWE-Lego
training id explicitly.

**Task filters** (`configs/study.yaml`, `data:`):
- Python;
- created on or after 2025-05-01;
- a pre-built image;
- a pytest log parser;
- at least one FAIL_TO_PASS test;
- 1 to 3 changed source files.

These leave **193 tasks in 115 repositories** (measured). Expect roughly 40% to survive gold
validation and the difficulty screen. That is enough for RQ1–RQ3, but RQ4 (the gating
experiment) can only be reported as an estimate with confidence intervals; see
[Limitations](#13-known-limitations).

---

## Experimental setup

This section specifies the whole experiment: what is measured, on what, with which treatments,
how it is scored and how it is tested. Each item names the config field that sets it
(`configs/study.yaml`) and the phase that runs it (§8). The rationale and the literature behind
each choice are in docs/ARCHITECTURE.md §1–§8.

### S1. Research questions and hypotheses

| RQ | Question | Hypothesis (decision rule) | Answered by |
|---|---|---|---|
| RQ1 Measurement | How is evidence value distributed across items, and does it depend on the actor? | **H1a** ≥ 30% of fresh, correct evidence items have AEV ≤ 0. **H1b** set value is non-monotone in the number of families. **H1c** cross-actor Spearman ρ of item AEV < 0.6 | `label` → `analyze` (RQ1) |
| RQ2 Validity | Does the cheap likelihood estimator agree with real rollouts? | **H2** Spearman ρ(AEV_LL, AEV_RO) ≥ 0.3, and the top item beats the bottom item in paired resolution. **Go/no-go:** ρ < 0.2 → rollout-only labels (docs §3) | `validate` → `analyze` (RQ2) |
| RQ3 Prediction | Can value be predicted at runtime without reference data? | **H3** hidden-state + item + state features beat item-only and log-probability-only predictors on repository-held-out AUROC | `train` (RQ3 table) |
| RQ4 Control | Does gating delivery on predicted value improve repair at matched budget? | **H4** GATE beats ALL on resolved-per-credit and recovery, with regressions non-inferior (2-point margin) | `parents` + `confirm` → `analyze` (RQ4) |
| RQ5 Generalization | Is evidence value actor-specific? | Cross-actor label correlation (H1c) | second actor (§9) + `cross-label` |

### S2. Units of analysis

| Unit | Definition |
|---|---|
| Task | One SWE-rebench-V2 issue with its image, gold patch, hidden test patch and FAIL_TO_PASS / PASS_TO_PASS tests |
| Rollout | One seeded agent attempt on a task, graded by the hidden tests |
| Checkpoint | A state inside a rollout where the agent's patch has changed (new tree hash, not the base tree); at most `agent.max_checkpoints` = 3 per rollout. Evidence is produced and delivered only here |
| Evidence item | One rendered finding of one family (S5), valid only for the exact tree and environment hash it was produced on |
| Block (RQ4) | One confirmation task × one seed: a common parent checkpoint branched into every arm |

### S3. Tasks, filters and split

- **Dataset:** `nebius/SWE-rebench-V2@d7608f0` (§0). The Python tasks used were created on or
  after 2025-05-01, which is after actor 1's training data. Actor 1's training ids are also
  removed explicitly (`data.exclude_hf_datasets`).
- **Eligibility:**
  - pytest log parser;
  - at least one FAIL_TO_PASS test;
  - 1–3 changed non-test source files (`data.max_patch_files`).

  This gives **193 tasks in 115 repositories**.
- **Gold validation (`validate-gold`):** every gold patch is applied and graded in its image.
  Tasks whose gold patch does not resolve are dropped.
- **Difficulty screen (`screen`, ZPD filter):**
  - the bare actor (no evidence) makes 4 attempts per task, seeds `screen.seeds` = 0–3;
  - only tasks it solves 1–3 times are kept;
  - this removes tasks that are always or never solved, which carry no paired signal.
- **Split (`split`):**
  - whole repositories are assigned to train / dev / confirm in the proportions 45 / 10 / 45%;
  - the assignment uses a salted hash and balances task counts;
  - no repository appears in two splits;
  - confirmation repositories never contribute labels, features or tuning.

### S4. Actors and agent harness

| Setting | Value (config field) |
|---|---|
| Actor 1 | SWE-Lego-Qwen3-8B, bf16, SDPA attention, context 24,576 tokens (`server.*`); thinking disabled |
| Actor 2 | Qwen3-Coder-30B-A3B-Instruct, 4-bit NF4 (bitsandbytes), context 16,384 |
| Serving | One process on one GPU serves generation, teacher-forced scoring and hidden states from the same weights and precision (`veritas serve`) |
| Sampling | temperature 0.7, top-p 0.95, ≤ 1,024 new tokens per turn; seed = rollout seed × 100003 + step (`backend.*`) |
| Tools | `execute_bash`, `str_replace_editor` (view / create / str_replace / insert), `finish`; one tool call per turn |
| Limits | 40 steps, 2,400 s wall, 400 credits, observations truncated to 6,000 chars; 3 consecutive unparseable turns end the run (`agent.*`) |
| Workspace | One Docker container per rollout or branch, `--network none`, 8 GB RAM, 2 CPUs, git history replaced by a single base commit (hack-free) |
| Credits | 0.002 per token + 0.05 per sandbox second, covering the agent, the producers and the gate (`cost.*`) |
| Grading | The final diff is applied to a fresh container with the hidden test patch, then FAIL_TO_PASS and PASS_TO_PASS are run with pytest. Resolved = all pass. Infrastructure failures are graded *unknown* and excluded from every rate |

### S5. Evidence families (the shared catalog for every arm)

At each checkpoint the producers first run the related tests (`pytest -rA`). They then emit at
most `evidence.max_items_per_family` = 2 items per family, each truncated to 1,500 characters:

| Family | Content | Basis |
|---|---|---|
| F1 failing-check | Which tests fail or error on the current tree | observed |
| F2 traceback | Last frames and error message of a failure | observed |
| F3 contrast-pair | A failing test next to the nearest passing test | observed |
| F4 runtime-state | Local variable values on the failing path (`--showlocals`) | observed |
| F5 localization | Suspected location, produced by the resident actor (temperature 0, JSON) | model opinion |
| F6 plan | Suggested next steps, produced by the resident actor | model opinion |
| F7 rubric | Repository-grounded acceptance criteria, produced by the resident actor | model opinion |

- **Packet:** the delivered items are rendered by one common renderer into a single user
  message, capped at `evidence.packet_token_cap` = 1,500 tokens as counted by the actor's
  tokenizer. When nothing is delivered, a fixed neutral packet is sent instead, so every arm gets
  a message.
- **Validity:** an item is valid only while the tree hash and environment hash it was produced on
  are unchanged.
- **Cost:** producer cost is charged identically in every arm.

### S6. Measurement: actor-relative evidence value

- **AEV_LL (dense label, `label`):**
  `AEV_LL(S) = max_{r ∈ R} [log p(r | h ⊕ packet(S)) − log p(r | h ⊕ neutral)] / |r|`.
  - `h` is the conversation at the checkpoint.
  - `R` is the reference set: the gold patch plus every hidden-test-passing patch from any
    rollout on the task (`label.reference_set: all_passing`).
  - Each reference is rendered as the edit actions the actor itself would type
    (`label.reference_format: edit`) and normalised per token.
  - It is computed for every subset of the available families (up to 2⁷ = 128), for each single
    item, and for each item left out.
- **Attribution (per checkpoint):**
  - exact Shapley value of each family;
  - interaction = AEV(all) − Σ AEV(single family);
  - *non-monotone* = the best subset is a strict subset of the available families.
- **Bug discrimination (`bsg/`):** each observed check is replayed on the buggy and on the gold
  checkout to label whether it distinguishes the bug.
- **AEV_RO (causal check, `validate`):**
  - the sample is 150 checkpoints (`validate.n_checkpoints`), stratified into 5 quintiles of
    top-item AEV_LL;
  - each is restored from its snapshot (the tree hash must match);
  - it is continued under four arms: NONE, TOP item, BOTTOM item and ALL;
  - each arm runs 3 seeds (`validate.seeds_per_arm`);
  - AEV_RO = resolve rate under the arm − resolve rate under NONE.

### S7. Predictors (runtime-legal)

- **Features, only what a deployed harness can compute:**

  | Group | Content |
  |---|---|
  | `item` | family (one-hot), observed vs. opinion, rendered tokens, severity, number of tests, whether it touches a file in the current diff, observed-output size, whether it names a location |
  | `state` | checkpoint index, step, remaining credits, history length, number of items, diff size |
  | `logprob` | mean and minimum token log-probabilities and entropy of the actor's recent turns |
  | `hidden` | the change in the actor's final-token hidden state at layers L/4, L/2 and 3L/4 when the item is added to the prompt |

- **Feature sets compared:** `item`, `logprob`, `hidden`, `full`, `full_no_state`, `no_hidden`
  and `item_state`.
- **Models:**
  - logistic regression;
  - a 2-layer MLP;
  - gradient-boosted trees;
  - PCA is applied first when there are more than 512 features.
- **Target:** sign(AEV_single > 0), using `probe.positive_threshold` = 0. A paired regressor
  predicts magnitude.
- **Validation:** 5-fold cross-validation grouped by repository on train + dev, followed by
  isotonic calibration.
- **Metrics:** AUROC, AUPRC, Spearman, within-checkpoint pairwise accuracy and calibrated ECE.
- **Baselines:**
  - shuffled labels (expected AUROC ≈ 0.5);
  - task difficulty only (screen pass rate).
- **Frozen artifacts:**
  - GATE uses logistic regression on `full`;
  - MANIPLE uses GBT on `item_state`;
  - LinUCB is trained offline on the labelled subset values, then frozen.

  Each artifact's SHA-256 is recorded in `train/report.json` and checked before use.

### S8. Treatments (arms) for RQ4

- **Parents (`parents`):** for every confirmation task and each seed in `confirm.seeds`
  (20, 21, 22), the actor runs with the NONE harness until its first checkpoint. That checkpoint
  is snapshotted and its patch is graded privately.
- **Branches (`confirm`):** every arm restarts from the same snapshot with:
  - the same evidence items, produced once at that checkpoint;
  - the same renderer and token cap;
  - the same remaining budget;
  - the same seed.
- **Blocks without a checkpoint:** if a parent never reaches a checkpoint, no treatment is
  possible. Every arm then takes the parent's outcome.

| Arm | Delivery rule | Role |
|---|---|---|
| NONE | Neutral packet (checks still run and are charged) | Lower anchor |
| RESAMPLE | A fresh attempt from the clean checkout under the NONE harness, full budget | Resampling vs. feedback |
| ALL | Every valid item in canonical family order, capped | Deliver-everything default (primary comparator) |
| FIX | F1 + F2 only | Fixed actionable template |
| MANIPLE | Items the GBT (no hidden states) predicts as positive | Strongest prior selector |
| QUALITY | Observed families always; F5–F7 only if a patch-free verifier (the actor) scores them ≥ 0.6 | Quality-gate baseline |
| LINUCB | One of five family groups (none; F1+F2; F3+F4; F5–F7; all) chosen by the frozen LinUCB from state, confidence and per-family item counts | Bandit baseline |
| **GATE** | Items in order of predicted value, kept while value − λ·(items of the same family already chosen) > τ (τ = 0). Delivers nothing if no item passes | **Proposed** |
| ORACLE | Best family subset by AEV_LL (uses reference fixes) | Upper bound, not deployable |
| RANDOM_SAME_SIZE | As many items as GATE delivers, chosen at random | Which items vs. how many |
| SHUFFLED | Same families and format as ALL, but items from another task | Format / length / "any hint" control |

### S9. Outcomes and metrics

| Level | Metric | Definition |
|---|---|---|
| Block | Resolved rate | Resolved ÷ graded (unknown excluded) |
| Block | Recovery | Resolved rate on blocks whose parent was wrong |
| Block | Regression | Unresolved rate on blocks whose parent was right (guardrail) |
| Block | Resolved per credit | Resolved ÷ credits of the whole attempt (the parent's share is identical across branched arms) |
| Item | Harm rate | Share of items with AEV ≤ 0 |
| Checkpoint | Shapley, interaction, non-monotone share | S6 |
| Item | ρ(AEV_LL, AEV_RO), top − bottom resolution | S6 |
| Item | AUROC, AUPRC, Spearman, pairwise accuracy, ECE | S7 |
| Run | Tokens, steps, wall time, GPU energy (Wh, sampled from `nvidia-smi`) | recorded per rollout in the phase `.jsonl` files |

### S10. Statistical analysis (fixed before confirmation)

- **Paired contrasts:**
  - exact McNemar test on the discordant blocks;
  - paired risk difference with a 95% bootstrap CI that resamples repositories, with 5,000
    resamples (`confirm.bootstrap_samples`).
- **Primary contrast:** GATE − ALL, on all blocks, the recovery cohort and the regression cohort.
  - Regression is non-inferior if the CI's bound stays within 2 points (`confirm.regression_margin`).
  - Resolved-per-credit uses a repository-clustered ratio CI.
- **Secondary contrasts:** GATE − FIX, GATE − MANIPLE, GATE − QUALITY and GATE − RESAMPLE, with
  Holm correction.
- **RQ1–RQ3:** reported as estimates with repository-clustered bootstrap CIs, not significance
  tests.
- **Power:** the report gives the number of pairs a decisive McNemar test would need at the
  observed discordance (`pairs_needed`). With ≈ 105 blocks, a 12-point difference is detectable
  at 20% discordance, so RQ4 is an estimation result (§13).
- **Preregistration:** the config, split and trained artifacts (with their hashes) are committed
  before `parents` runs (§8, step 9).

### S11. Ablations: what runs and what does not

docs/ARCHITECTURE.md §8 lists 26 ablations. Status in this code base:

| ID | Ablation | Status |
|---|---|---|
| R1, R2, R4, R5 | item-only, log-probability-only, full and full-without-state predictors | **Automated** in `train` (feature sets in the RQ3 table) |
| R3 | hidden states only | **Automated** for the three layers together (`hidden`). Per-layer: not automated |
| R7 | logistic vs. MLP vs. GBT | **Automated** in `train` |
| R8 | shuffled labels; difficulty-only | **Automated** in `train` (baselines) |
| G1 | GATE vs. random same size | **Automated** as the RANDOM_SAME_SIZE arm |
| G3 | shuffled evidence | **Automated** as the SHUFFLED arm |
| G5 | τ ∈ {−0.05, 0, 0.05} | **Automated** offline (out-of-fold) in `train/report.json` → `tau_sensitivity` |
| E4 | prefix-KV reuse equals full recompute | **Automated** as a test (`tests/test_hfserver.py`); no runtime audit on the real actor |
| E1, E2, E3 | gold-only reference set; summed log-probability; unified-diff references | **Config options** (`label.reference_set`, `label.normalize_per_token`, `label.reference_format`). Each needs its own `study_id`, so it re-runs the whole pipeline. Not automated as within-run variants |
| E5 | k = 2 / 4 / 8 AEV_RO seeds | Only k = `validate.seeds_per_arm` (3). Not automated |
| E6 | pre- vs. post-cutoff contamination audit | **Not implemented** |
| R6 | Δ-state vs. absolute state | **Not implemented** (Δ-state only) |
| R9 | actor self-judge baseline | **Not implemented** |
| R10 | predictor trained on one actor, tested on the other | **Not implemented**. H1c compares labels, not predictors |
| G2, G4, G6–G10 | no-threshold ordering, length-matched padding, no redundancy penalty, no abstention, timing, observed-only families, leave-one-family-out | **Not implemented** as arms |
| — | mixed-effects robustness model; NDCG@k; uptake | **Not implemented** |

The paper should report only the automated rows, unless the missing ones are added. See
[Known limitations](#13-known-limitations).

### S12. Design-to-command map

| Design element | Phase (§8) | Seeds | Main output |
|---|---|---|---|
| Gold validation | `validate-gold` | — | `gold.jsonl` |
| Difficulty screen | `screen` | 0–3 | `screen.jsonl`, `traces/` |
| Repository split | `split` | — | `split.json` |
| Neutral-harness rollouts + evidence at checkpoints | `collect` | 10–12 | `checkpoints/` |
| AEV_LL, Shapley, BSG, features | `label` | — | `labels/`, `features/`, `bsg/` |
| AEV_RO | `validate` | 1000 + | `validate.jsonl` |
| Predictors, baselines, frozen policies | `train` | — | `train/report.json`, `artifacts/` |
| Preregistration | git commit | — | — |
| Common parents | `parents` | 20–22 | `parents/` |
| Arms | `confirm` | 20–22 | `confirm.jsonl` |
| RQ1–RQ4 report | `analyze` | — | `analysis/report.md`, `report.json` |
| Cross-actor (H1c) | `cross-label` + `analyze --other` | — | RQ1 section of actor 2's report |

---

## 1. Machine requirements

| | Required | Notes |
|---|---|---|
| GPU | One NVIDIA GPU with 24 GB (RTX 3090/4090, A5000, L4…) | Only the model server uses it; task containers run on the CPU |
| RAM | 64 GB | |
| Disk | ≥ 600 GB free (SSD) | ~0.3 TB task images, 16 GB actor 1 (+61 GB actor 2), 3 GB dataset, checkpoint snapshots |
| OS | Ubuntu 22.04/24.04 (or WSL2 with the NVIDIA WSL driver) | Task images are x86-64 |
| Network | Needed for downloads and image pulls | Task containers themselves run with `--network none` |
| Accounts | Free Docker Hub account (recommended) | Anonymous Docker Hub pulls are rate-limited; ~200 images are needed |

macOS works for development, tests and analysis only (no CUDA; x86 images).

## 2. Install system software (once per machine)

1. **NVIDIA driver.** `nvidia-smi` must list the GPU. On WSL2, install the Windows NVIDIA driver;
   do not install a Linux driver inside WSL.
2. **Docker Engine.**
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker "$USER"     # then log out and back in
   docker run --rm hello-world         # must work without sudo
   docker login                        # raises the Docker Hub pull limit
   ```
   The NVIDIA container toolkit is **not** needed: containers never use the GPU.
3. **git** and **uv**:
   ```bash
   sudo apt-get install -y git
   curl -LsSf https://astral.sh/uv/install.sh | sh    # then open a new shell
   ```

## 3. Install VERITAS and run the tests

The GPU machine needs the current code. On the development machine, commit and push it first
(`git push`). Then, on the GPU machine:

```bash
git clone https://github.com/Abidur-Rahman-01/VERITAS.git veritas && cd veritas
git log -1 --oneline        # must show the commit you just pushed
uv sync --extra dev --extra gpu --extra data
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # must print True
uv run ruff check .
uv run pytest -q
```

- **Expected test result:** `36 passed`.
- **What the tests cover:** the end-to-end pipeline on real git repositories with a scripted
  model, plus the model server on a tiny real Qwen model. The tiny model's checkpoint is
  downloaded the first time; offline, those 4 tests are skipped.
- **If `cuda.is_available()` prints `False`:** the installed torch does not match your driver. Install a CUDA build
  that matches the driver (`nvidia-smi` shows the CUDA version) from pytorch.org, e.g.
  `uv pip install torch --index-url https://download.pytorch.org/whl/cu126`. Then check again.
- **Extras:** `--extra gpu` adds torch, transformers, accelerate and, on Linux, bitsandbytes
  (needed for actor 2). `--extra data` adds the Hugging Face downloader. Pass all three extras
  to every `uv sync`, because `uv sync` removes packages it was not asked for.

## 4. Download the dataset

```bash
uv run veritas fetch-data --config configs/study.yaml
```

It takes 5–15 minutes and writes:

| File | Content | Check |
|---|---|---|
| `data/raw/swe_rebench_v2.jsonl` | All 32,079 SWE-rebench-V2 rows (2.6 GB) | — |
| `data/raw/swe_rebench_v2.manifest.json` | Repo, revision, row count, SHA-256 | `"rows": 32079`, `"sha256": "8e7864a8e7e7cd9d6521208cbe9af4f189a8094079c82b794dbbd35c746e12d8"` |
| `data/raw/exclude_swelego_ids.txt` | SWE-Lego training ids | 29,507 lines |

Re-running skips the download if the manifest matches. Use `--force` to download again.
Transient Hugging Face timeouts are retried automatically.

## 5. Download the actor model

```bash
sudo mkdir -p /models && sudo chown "$USER" /models
uv run hf download Lego-X/SWE-Lego-Qwen3-8B --revision 00f37992485b78e9579a2674161d512781aee21e \
    --local-dir /models/SWE-Lego-Qwen3-8B
```

The download is about 16 GB. If you put the model elsewhere, change `server.model_path` in
`configs/study.yaml` and `configs/smoke.yaml` *before* the first phase. A run directory refuses a
changed config.

## 6. Build the task list and pull the images

```bash
uv run veritas prepare --config configs/study.yaml
```

Expected output: `"eligible": 193`, plus these exclusion counts:
- `"before_cutoff": 31004`
- `"not_python": 766`
- `"too_many_files": 116`

It writes `runs/actor1-swelego8b-v1/tasks.jsonl`. Then pull every task image:

```bash
uv run python -c "import json; print('\n'.join(sorted({json.loads(l)['image'] for l in open('runs/actor1-swelego8b-v1/tasks.jsonl')})))" > images.txt
wc -l images.txt                          # one image per task
xargs -n1 -P4 docker pull < images.txt    # re-run until every pull succeeds
```

## 7. Start the model server and run the smoke test

**Terminal 1** (keep it running for every GPU phase):

```bash
uv run veritas serve --config configs/study.yaml
```

The model takes 1–3 minutes to load. **Terminal 2:**

```bash
curl -s localhost:8765/info
```

The reply must show:
- `"model": "/models/SWE-Lego-Qwen3-8B"`;
- `"n_layers": 36`;
- `"feature_layers": [9, 18, 27]`;
- `"max_context_tokens": 24576`.

**Smoke test.** This runs the real Docker and GPU path on 5 tasks before anything long starts.
`configs/smoke.yaml` is the main config with only the study id, the task count and the screening
seeds changed:

```bash
uv run veritas prepare       --config configs/smoke.yaml
uv run veritas validate-gold --config configs/smoke.yaml
uv run veritas screen        --config configs/smoke.yaml --workers 2
uv run veritas status        --config configs/smoke.yaml
```

Pass criteria:
- **`validate-gold`:** at least 4 of the 5 gold patches are `resolved`. Look at
  `runs/actor1-smoke/gold.jsonl`.
- **`screen`:** reports `"failed": 0`, and each line of `runs/actor1-smoke/screen.jsonl` has a
  `grade` and a termination reason. Expect `finished` or `max_steps`, not `format_errors`.
- **`status`:** reports `"ledger": "verified"` and no `errors`.
- **Timing:** one screen unit takes about 5–10 minutes. Note it, because it calibrates the
  budget in docs §9.2.

If any check fails, see [Troubleshooting](#11-troubleshooting). Once everything passes, remove
the smoke run:
```bash
rm -rf runs/actor1-smoke
```

## 8. Run the study

**Keep long runs alive.** Several phases run for days, and the server must stay up throughout.
Run everything inside `tmux`, so a dropped SSH connection or a closed terminal does not stop it:

```bash
sudo apt-get install -y tmux
tmux new -s veritas        # window 0: the server (§7); Ctrl-b c opens window 1 for the phases
# detach: Ctrl-b d      re-attach later: tmux attach -t veritas
```

To keep a log of a phase, append `2>&1 | tee -a runs/phase.log` to its command.

**Back up `runs/` daily.** It holds weeks of results and exists only on this machine. Snapshot
images are not included and can be re-created. Use another disk or machine:

```bash
rsync -a --delete runs/ /path/to/backup/veritas-runs/
```


Run the phases in order, in terminal 2, with the server running in terminal 1. `C` stands for
`configs/study.yaml`, and every command starts with `uv run`.

Each phase prints a JSON summary and is **resumable**. If it is interrupted (Ctrl-C, reboot,
crash), run the same command again: units already recorded in
`runs/actor1-swelego8b-v1/ledger.jsonl` are skipped, and failed ones are retried. The approximate
times assume one 24 GB GPU and `--workers 3`.

| Step | Command | Output (under `runs/actor1-swelego8b-v1/`) | Check before continuing | Approx. time |
|---|---|---|---|---|
| 1 | `veritas prepare --config C` | `tasks.jsonl`, `tasks_manifest.json` | done in §6 (`eligible: 193`) | seconds |
| 2 | `veritas validate-gold --config C --workers 3` | `gold.jsonl` | most gold patches `resolved`; the rest are dropped automatically | 2–4 h |
| 3 | `veritas screen --config C --workers 3` | `screen.jsonl`, `traces/` | `failed: 0` | 2–4 days |
| 4 | `veritas split --config C` | `split.json` | counts for train/dev/confirm; ≥ 2 repositories in train | seconds |
| 5 | `veritas collect --config C --workers 3` | `collect.jsonl`, `checkpoints/*.json` | most checkpoints have ≥ 4 evidence items | ~1 day |
| 6 | `veritas label --config C --workers 2` | `labels/`, `features/`, `bsg/`, `base_files/` | no `unit_error` in `status` | ~1 day |
| 7 | `veritas validate --config C --workers 3` | `validate_plan.json`, `validate.jsonl` | **H2 gate** (below) | 3–4 days |
| 8 | `veritas train --config C` | `train/report.json`, `artifacts/` | `gate`, `maniple`, `linucb` artifacts listed in the report | < 1 h (CPU) |
| 9 | **Preregister** (below) | git commit | — | — |
| 10 | `veritas parents --config C --workers 3` | `parents.jsonl`, `parents/*.json` | `has_checkpoint: true` for most blocks | ~1 day |
| 11 | `veritas confirm --config C --workers 3` | `confirm.jsonl` | every block × arm present | 2–3 days |
| 12 | `veritas analyze --config C` | `analysis/report.md`, `analysis/report.json` | — | minutes |

**What each phase does.**
- **validate-gold:** grades every gold patch with the task's tests, so tasks the grader cannot
  reproduce are never used.
- **screen:** runs the bare actor 4 times per task. Only tasks it solves 1–3 times out of 4 are
  kept (the ZPD filter).
- **split:** assigns whole repositories to train, dev or confirm.
- **collect:** runs the actor with a neutral harness and saves a checkpoint at each new patch
  state, together with all seven evidence families produced there.
- **label:** scores the actor's likelihood of reaching a correct fix under every evidence subset
  (AEV_LL), and extracts hidden-state features.
- **validate:** branches real rollouts from a sample of checkpoints (AEV_RO) to check the cheap
  estimator.
- **train:** fits the predictors and freezes the GATE, MANIPLE and LinUCB policies.
- **parents** and **confirm:** run fresh tasks to their first checkpoint, then continue each one
  under every arm with matched budgets.

**H2 gate (after step 7).** Run `uv run veritas analyze --config C` and read
`Spearman(AEV_LL, AEV_RO)` in the RQ2 section of `analysis/report.md`.
- **ρ ≥ 0.2:** continue.
- **ρ < 0.2:** the likelihood estimator does not track real outcomes. Follow the pivot in
  docs/ARCHITECTURE.md §3, which uses rollout labels only, on fewer checkpoints.

**Preregistration (step 9).** Before any confirmation run, freeze the analysis inputs in git:

```bash
git add -f runs/actor1-swelego8b-v1/config.json runs/actor1-swelego8b-v1/split.json \
          runs/actor1-swelego8b-v1/train/report.json
git commit -m "Preregister actor 1: config, split, trained artifacts (hashes in train/report.json)"
```

`train/report.json` records the SHA-256 of every artifact. The confirm phase refuses an artifact
whose hash differs, so the commit fixes exactly what is tested.

## 9. Second actor (optional: H1c cross-actor, RQ5)

```bash
uv run hf download Qwen/Qwen3-Coder-30B-A3B-Instruct --revision b2cff646eb4bb1d68355c01b18ae02e7cf42d120 \
    --local-dir /models/Qwen3-Coder-30B-A3B-Instruct      # ~61 GB; served in 4-bit (bnb4)
```

1. Stop the actor 1 server (Ctrl-C in terminal 1), then start
   `uv run veritas serve --config configs/study_actor2.yaml`. `/info` must show
   `"quantization": "bnb4"`.
2. Run steps 1–3 of §8 with `configs/study_actor2.yaml`. The dataset is already downloaded.
3. Reuse actor 1's repository split:
   `uv run veritas split --config configs/study_actor2.yaml --reuse-split runs/actor1-swelego8b-v1/split.json`.
4. Run steps 5–12 with `configs/study_actor2.yaml`.
5. Score actor 1's checkpoints with actor 2, then analyze:
   ```bash
   uv run veritas cross-label --config configs/study_actor2.yaml --source runs/actor1-swelego8b-v1
   uv run veritas analyze --config configs/study_actor2.yaml --other runs/actor1-swelego8b-v1
   ```

Qwen3-Coder emits tool calls in its XML format (`<function=…><parameter=…>`). The parser accepts
both that format and SWE-Lego's JSON format. Both are tested by round trips through the real
chat templates.

## 10. Evaluate the results

`veritas analyze` writes `analysis/report.md` (human-readable) and `analysis/report.json` (every
number, for tables and plots). It can be re-run at any time; it only reads files. The sections map
to the hypotheses in docs/ARCHITECTURE.md §2 as follows.

| Report section | What it shows | Hypothesis and how to read it |
|---|---|---|
| **RQ1 Measurement** | Items labelled; harm rate (share of items with AEV ≤ 0) with a repository-clustered 95% CI; per-family table (n, mean AEV, harm rate, mean Shapley value) | **H1a** holds if the harm rate's CI lies above 0.30 |
| | Non-monotone checkpoints; mean interaction | **H1b**: the share of checkpoints where adding a family lowers value. A clearly non-zero share supports non-monotonicity |
| | Discriminative × valuable 2×2 table and Haldane odds ratio | Whether evidence that discriminates the bug (BSG) is also evidence the actor can use. An odds ratio near 1 means it is not |
| | Cross-actor Spearman (actor 2 report only, with `--other`) | **H1c** holds if ρ < 0.6, meaning evidence value depends on the actor |
| **RQ2 Validity** | Spearman(AEV_LL, AEV_RO); top-item minus bottom-item resolution with CI and exact McNemar p | **H2** holds if ρ ≥ 0.3 and top − bottom > 0 with p < 0.05 |
| **RQ3 Prediction** | Repository-grouped cross-validation for every model × feature set (AUROC, AUPRC, Spearman, pairwise accuracy, calibrated ECE); baselines (shuffled labels, task difficulty only) | **H3** holds if `full` (hidden states + item + state) beats `item` and `logprob` (AgentStop-style) on AUROC. Shuffled labels should give AUROC ≈ 0.5 |
| **RQ4 Control** | Resolved rate and mean credits per arm; paired contrasts GATE−ALL (primary), then GATE−FIX, GATE−MANIPLE, GATE−QUALITY and GATE−RESAMPLE, each on all blocks, on blocks whose parent was wrong (*recovery*) and on blocks whose parent was right (*regression*); Holm-adjusted secondary p-values; resolved-per-credit ratio | **H4** holds if GATE−ALL resolved-per-credit > 0 with a CI excluding 0, and the regression cohort is non-inferior (margin 2 points). `pairs_needed` gives the sample size a decisive test would need at the observed discordance |

More outputs:
- **`train/report.json`:** the GATE redundancy penalty λ, the τ-sensitivity table (out-of-fold
  value of the items GATE would deliver at each threshold) and the artifact hashes.
- **ORACLE, RANDOM_SAME_SIZE and SHUFFLED:** upper-bound and sanity arms in the RQ4 table. GATE
  should land between RANDOM_SAME_SIZE and ORACLE.
- **Unknown grades:** grades that are neither `resolved` nor `unresolved` (infrastructure or
  grader errors) are excluded from every rate and counted in the ledger.

## 11. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `uv run veritas status` shows `errors` | `grep unit_error runs/<id>/ledger.jsonl \| tail -1 \| python3 -m json.tool` shows the traceback. Fix the cause and re-run the phase; only failed and missing units run again |
| `docker: permission denied` | Your user is not in the `docker` group (§2), or you have not logged in again since adding it |
| `toomanyrequests` while pulling | Docker Hub rate limit: `docker login`, then re-run the pull |
| `workspace preparation failed` | The image is missing or broken. `docker pull <image>` and re-run. Persistent failures are dropped by `validate-gold` |
| Many screen units end with `format_errors` | The actor's output is not being parsed as tool calls. Open `runs/<id>/traces/<task>__<seed>.json`: the assistant turns before each format reminder hold the raw text. Check that `server.chat_template_kwargs` is `{enable_thinking: false}` for SWE-Lego |
| `context_exceeded` terminations or HTTP 413 | The conversation outgrew `server.max_context_tokens`. Lowering `agent.max_steps` or `agent.max_observation_chars` needs a new `study_id` |
| CUDA out of memory in the server | Another process is using the GPU (check `nvidia-smi`), or `max_context_tokens` is too high for your card. Lower it under a new `study_id` |
| `… was created with a different configuration; use a new study_id` | The config differs from the one the run directory was created with. Restore it, or use a new `study_id` |
| `LedgerCorrupt` | The ledger was edited or truncated. Restore it from a backup; never edit it by hand |

## 12. Disk hygiene

Checkpoint snapshots are Docker images tagged `veritas-snap:*`. They are needed until `validate`
and `confirm` finish. Check the space used with `docker system df`. After `confirm`, remove them:

```bash
docker images 'veritas-snap' -q | xargs -r docker rmi -f
```

## 13. Known limitations

- **Ablations and baselines not automated.** See the status table in S11: E5, E6, R6, R9, R10,
  G2, G4, G6–G10 and the mixed-effects robustness model have no command yet. E1–E3 need
  separate runs.
- **Pool size.** 193 eligible tasks (≈ 77 after gold validation and the ZPD screen) give about
  105 confirmation blocks. That is enough to detect a difference of about 12 points at 20%
  discordance, below the ≥ 400 tasks the power analysis asks for. Report RQ4 as an estimate with
  CIs. To enlarge the pool, point `data.hf_revision` at a newer SWE-rebench-V2 commit, use a new
  `study_id`, and re-run from step 1.
- **Actor 2 contamination.** Qwen3-Coder-30B-A3B was released on 2025-07-31, after the start of
  the task window (2025-05-01). Report its results with that caveat.
- **Hardware verification.** The Docker and CUDA paths are exercised for the first time by the
  smoke test in §7. Throughput numbers in docs §9.2 are planning estimates until then.

## Rules the code enforces

- **The configuration is frozen per run directory.** A changed config is refused; use a new `study_id`.
- **The runtime never reads outcome-plane files:** `gold.jsonl`, `labels/`, `bsg/`, `base_files/`
  and grades. Feature names are checked against outcome-plane words in the tests.
- **Artifacts are hash-pinned.** A predictor whose file hash differs from `train/report.json` is refused.
- **Unknown grades are never counted as passes or failures.**
- **Every arm sees the same evidence,** produced once at the branching checkpoint and charged
  equally. Arms are rendered by one renderer under one token cap.
- **Hack-free workspaces.** Each container starts with its git history removed and a single base
  commit. It has no network access.

## Code map

| Module | Role |
|---|---|
| `datafetch.py`, `tasks.py` | Pinned dataset download and exclusion ids; eligibility filters; repository-disjoint split |
| `sandbox.py` | Network-less Docker workspace per branch (per-image WORKDIR, git history removed); snapshot/restore. `LocalSandbox` for tests |
| `tools.py`, `agent.py` | `execute_bash` / `str_replace_editor` / `finish` agent loop (JSON and Qwen3-Coder XML tool calls); checkpoint on every new patch state (max K) |
| `producers.py`, `evidence.py` | Evidence families F1–F7, exact-hash validity rule, common renderer with a tokenizer-measured cap |
| `policies.py` | Arms NONE, ALL, FIX, MANIPLE, QUALITY, LINUCB, GATE, ORACLE, RANDOM_SAME_SIZE, SHUFFLED (RESAMPLE in `study.py`) |
| `hfserver.py`, `backend.py` | One GPU process serving generation, teacher-forced scoring (shared-prefix KV reuse) and hidden states |
| `refset.py`, `aev.py` | Reference fixes in the actor's edit format; AEV_LL over all family subsets, item singletons/LOO, exact Shapley |
| `grading.py`, `bsg.py` | Independent SWE-bench-semantics grading; bug-discrimination labels |
| `features.py`, `probe.py` | Runtime-legal features; grouped-CV predictors, calibration, hash-pinned artifacts |
| `study.py`, `analysis.py`, `stats.py` | Resumable phases, hash-chained ledger, RQ1–RQ4 report (exact McNemar, cluster bootstrap, Holm) |
