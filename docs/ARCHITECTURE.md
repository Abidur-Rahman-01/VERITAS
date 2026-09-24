# VERITAS source architecture

This explains the current source, including limitations discovered in the supplied
SWE pilot transcript. There are 26 Python files under src/veritas. VERITAS is an
experiment framework around existing local language models. It is not a new pretrained
language model and does not automatically make a benchmark result scientifically valid.

## How the parts connect

    Terminal command
        |
        v
    cli.py + config.py + schema.py
        |
        +--> data.py: original tasks, provenance and frozen partitions
        |
        +--> runtime.py: one task, repeated proposed actions
        |      |
        |      +--> models.py: policy proposes a tool action
        |      +--> contracts.py: schema, paths and allowed operations
        |      +--> critic.py OR models.py: estimate action error
        |      +--> calibration.py: calibrated probability + verifier statistics
        |      +--> controller.py: decide whether to spend verification credits
        |      +--> verifier.py: configured probes and/or semantic checking
        |      +--> sandbox.py --> worker.py: execute an accepted action in Docker
        |      +--> state.py: checkpoint/restore and workspace integrity
        |      +--> sanitize.py: prepare untrusted observations for the next step
        |      +--> store.py: append the action, decision, outcome and usage
        |
        +--> labels.py: independently adjudicated correctness
        +--> calibration.py: fit only on the designated calibration roles
        +--> replay.py: tune on validation and analyze fixed test trajectories
        +--> swe.py: independent repository environment setup and final grading
        +--> report.py / comparison.py / diagnostics.py: inspect and compare results

The policy, critic and verifier are different roles. They can use the same local
model weights, but their outputs are not independent ground truth. Ground truth
comes from the task's evaluator, applicable executable evidence, or independent review.

## Entry points and shared definitions

| File | What it does | Contribution |
|---|---|---|
| [__init__.py](../src/veritas/__init__.py) | Declares the package version and the error-label convention: error=1, correct=0. | Makes the package importable and documents label meaning. |
| [__main__.py](../src/veritas/__main__.py) | Calls the CLI main function. | Supports running the package through Python's module entry point. |
| [cli.py](../src/veritas/cli.py) | Parses commands such as data, collect, labels, critic, calibrate, tune, replay, swe, compare and diagnose-run. Dispatches to the corresponding modules. | The terminal interface, not the research algorithm. It also checks the tuning/calibration hash relationship. |
| [config.py](../src/veritas/config.py) | Defines model, sandbox, run and full configuration objects; loads YAML with an optional override. | Makes experiment settings explicit and validates supported ranges and budget units. |
| [schema.py](../src/veritas/schema.py) | Defines Task, Proposal, ActionContract, Usage, Verification, StepRecord and action classes using Pydantic. | Gives every module a consistent data contract. Unknown correctness stays null; labeled records need a scope and evidence source. |
| [provenance.py](../src/veritas/provenance.py) | Fingerprints critic/verifier configuration and their implementations, including prompts and parsers. | Detects stale calibration after relevant code changes. |
| [io.py](../src/veritas/io.py) | Canonical JSON serialization, SHA-256 hashing, atomic JSON/JSONL writes, and JSONL/Parquet record readers. | Reproducible data interchange and integrity checking. A hash proves identity relative to a recorded value, not truth of the contents. |

## Tasks, models and action execution

| File | What it does | Contribution |
|---|---|---|
| [data.py](../src/veritas/data.py) | Downloads pinned original releases, checks row counts and receipts, normalizes tasks, deduplicates by identity/exact normalized prompt, assigns research partitions, and loads validated prepared data. | Supplies real tasks and controls direct train/evaluation overlap. It cannot exclude near duplicates or model pretraining contamination. |
| [models.py](../src/veritas/models.py) | Implements Ollama, OpenAI-compatible local-server and direct local Transformers calls. Contains policy/critic/verifier prompts, token accounting, JSON parsing and limited tool-argument normalization. | Connects local models to the agent protocol. The prompted critic lives here; trained critics live in critic.py. |
| [contracts.py](../src/veritas/contracts.py) | Validates arguments, relative paths, tool names, Python AST restrictions and test-command structure. Derives the action class, permissions and mutation category. | Deterministic constraints before optional model verification. Passing a contract does not mean an action solves the task. |
| [runtime.py](../src/veritas/runtime.py) | collect prepares run/task directories, models, ledgers and images. run_task builds context, proposes actions, validates, scores, gates, verifies, executes, logs, and stops on a final answer or step limit. Exports SWE patches and task summaries. | The central orchestration loop; most components meet here. |
| [sandbox.py](../src/veritas/sandbox.py) | Runs each tool action in a disposable Docker container without network or host bind mounts; transfers and validates workspace archives; initializes SWE checkouts; produces Git patches. | Separates model-written code from direct host execution. Only the workspace persists between actions; it is not a full persistent machine snapshot. |
| [worker.py](../src/veritas/worker.py) | Small standard-library tool executor copied into the container. Lists/reads/writes files, runs Python/pytest, performs local SQLite operations, and returns exit codes/output. | Performs the requested action inside Docker. It does not decide whether the action was semantically correct. |

A raw dataset task has private evaluation fields such as answers and reference patches.
The runtime gives models the public prompt and observations; private gold answers are
used for grading, not supplied as policy or verifier context.

## Verification, risk and recovery

| File | What it does | Contribution |
|---|---|---|
| [critic.py](../src/veritas/critic.py) | Builds features from pre-action context/action only; trains a TF-IDF/logistic classifier or a local LoRA sequence classifier; loads and checks saved weights; scores records. Training is restricted to the critic_train calibration role. | An optional learned error estimator. It is not the final verifier, and it does not train the policy model to solve SWE tasks. |
| [calibration.py](../src/veritas/calibration.py) | Fits temperature scaling on probability-role labels; estimates detection, false-positive and workspace-restoration rates on separate verifier_stats records; computes ECE, Brier, NLL and Wilson intervals; applies the artifact to actions. | Converts scores and measured verifier behavior into controller inputs. Versioned artifacts are checked against saved evidence; validate-calibration reports held-out probability quality. Missing classes cause replay errors and explicit budgeted fallback online. The saved before/after fit metrics alone are not validation. |
| [controller.py](../src/veritas/controller.py) | Defines the Risk value calculation, Decimal-based budget accounting and eight policies: never, always, random, confidence, risk, error_impact, bavar_style and rcvov. Reserves credits before verification. | Chooses where to spend optional verification effort. It does not execute models or label correctness. |
| [verifier.py](../src/veritas/verifier.py) | Optionally applies a candidate mutation and configured test probes in a cloned sandbox, then invokes the semantic verifier. | Searches for a defect before the real workspace action is accepted. An LLM verdict remains a fallible measurement. |
| [state.py](../src/veritas/state.py) | Hashes workspace files/directories/modes, copies checkpoints, restores and checks their hashes, and safely extracts bounded archives. | Workspace integrity and local recovery. It cannot undo external API effects or establish that recovered content is semantically correct. |
| [sanitize.py](../src/veritas/sanitize.py) | Redacts known secret patterns, quarantines some instruction-like lines, truncates observations and attaches provenance/untrusted markers. | Defense in depth for observations and logs. It is not complete prompt-injection prevention. |

The controller's value expression is:

    delta = p_error * detection_rate * (1 - residual_loss) * impact
            - verifier_cost
            - (1 - p_error) * false_positive_rate * false_alarm_cost

The first term estimates benefit from catching an error; the other terms penalize
verification expense and false alarms. In the current implementation these use
experiment-defined impact weights and fixed verifier-call credits, not measured
monetary damage or an enforced total model-token budget. RC-VoV compares a normalized
score to a threshold with dynamic pacing. The bavar_style policy is a simplified
heuristic, not a reproduction of the published BAVAR system.

Verification usually precedes execution in the live loop. Restoring after a rejected
proposal therefore normally makes no substantive change. Audit collection can measure
post-action hash restoration, but that alone does not demonstrate recovery utility.

## Evidence, evaluation and results

| File | What it does | Contribution |
|---|---|---|
| [store.py](../src/veritas/store.py) | Maintains an append-only SQLite event table with a hash chain; exports JSONL/Parquet and checks manifests; supports optional encrypted exports. | Auditable records. Someone who controls the files can still replace files and recompute hashes; external provenance anchors are needed for stronger guarantees. |
| [labels.py](../src/veritas/labels.py) | Grades GSM8K final numbers and MATH normalized exact strings; creates blinded review queues; conservatively labels final submissions; applies evidence-backed annotations. | Provides labels separately from critic/verifier opinions. Intermediate execution success is not automatically semantic correctness; MATH string mismatch may still be mathematically equivalent. |
| [replay.py](../src/veritas/replay.py) | Requires fully labeled, ungated audited traces. Tunes thresholds on validation, replays policies under credit caps, computes caught/missed errors and false rejections, and creates paired task-cluster bootstrap intervals. | Measures allocation on fixed traces. It cannot infer online task success after a verifier changes an action and therefore the subsequent trajectory. |
| [swe.py](../src/veritas/swe.py) | Produces task-to-image mappings with the installed SWE harness, pulls/builds environments, and creates/runs official grading commands. Handles the authors' SWE-rebench fork. | Repository environment and final patch evaluation integration. Calling the harness is not evidence that tests passed; inspect its reports and logs. |
| [report.py](../src/veritas/report.py) | Writes replay plots/tables, summarizes online success with optional SWE report joins, and compares paired checkpoint/restart token totals. | Turns recorded measurements into reports. It cannot repair weak labels or invalid calibration. |
| [comparison.py](../src/veritas/comparison.py) | Discovers installed completion-capable models, freezes paired real-task selections, runs one model/task at a time, preserves attempts, grades SWE patches, and prints/saves comparison tables. | Compares model baselines with no optional critic/verifier overhead. It is separate from the additional scripts/run_swe_online_comparison.py policy runner. |
| [diagnostics.py](../src/veritas/diagnostics.py) | Reads a run's metadata, summaries and SQLite events; distinguishes label scopes; checks critic variation, failure status and missing calibrated classes. | Helps identify incomplete experiments and misleading calibration interpretations without inference. |

## The three experiment paths

1. **Baseline model comparison:** comparison.py freezes identical tasks and runs the
   runtime with policy=never, audit_all=false and score_critic=false. This establishes
   model capability/cost under the common agent interface.
2. **Audit and offline research:** collection uses policy=never with audit_all=true;
   verifier results are recorded without changing baseline actions. Independent labels
   permit critic fitting, calibration and validation-tuned replay.
3. **Online verification experiment:** freeze the actor/critic/verifier/protocol,
   load valid calibrated statistics and validation thresholds, run each policy on
   matched tasks, then grade final outcomes independently. Report all overhead.

## Changes after the SWE pilot review

The issues in the historical SWE review are addressed by the performance upgrade:
invalid critic output remains missing, component identities include implementation
hashes, empirical artifacts are checked against evidence, and the matrix preserves
failed attempts and joins official grades. The unsafe resource-module shim was removed.

Online pre-execution rejection now avoids unnecessary checkpoint copies. Audit mode
still measures restoration. Exact-block edit_file actions reduce whole-file generation,
and configured probes compare baseline and candidate test outcomes.

See [PERFORMANCE_UPGRADE.md](PERFORMANCE_UPGRADE.md) for migration, commands, current
limitations, and the experiments still needed to establish an empirical advantage.
