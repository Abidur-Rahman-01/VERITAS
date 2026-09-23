# Research protocol

## 1. Hypothesis and units

The controller implements the supplied expression:

```text
delta = p_error * detection_rate * (1 - residual_loss) * impact
        - verifier_cost
        - (1 - p_error) * false_positive_rate * false_alarm_cost
verify iff delta / verifier_cost > threshold + dynamic_lambda * used / remaining
```

The dynamic term uses the fraction of the original budget spent; the actual formula
is in `controller.py`. A verification is reserved before a call and charged even if the
call fails. Decimal arithmetic avoids overspending through floating-point drift.

Impact and costs are normalized decision units specified by the experimenter. The
default verifier costs 0.02 credit units; a 0.20 budget permits at most ten calls. This
matches **credit caps**, not necessarily used credits, GPU FLOPs, wall time or tokens.
Report actual spend as well as the cap. The configured probe suite can have variable
runtime, so equal call credits must not be described as equal verification compute.

The target ordering RC-VoV > error×impact > confidence is a hypothesis. Reports retain
negative/zero differences. Establish an online success or token advantage using fresh
paired runs; offline replay alone cannot establish either.

## 2. Real data and partitions

The delivered `data/prepared` declares a new **research pool** for `swe_test` and
`swe_rebench`, then assigns task-disjoint 10% dev, 25% calib, 20% val, 35% test and
10% backbone partitions within domain/repository strata. These sources have upstream
Hugging Face splits named `test`, so this is a new research split, not an unchanged
official full-SWE-bench or SWE-rebench leaderboard protocol.

SWE-bench Verified, official GSM8K test and MATH-500 are always forced to test.
Duplicate tasks found in a reserved release remain reserved. Task overlap is removed
by issue identity and normalized prompt fingerprints, never by per-step random splits.
All repeated runs of a task inherit its partition. Rounding within small strata makes
the final proportions approximate. This is a five-way partition, **not** five-fold
cross-validation. Repositories may appear across partitions; this is not a held-out
repository generalization claim.

`data/prepared-conservative` preserves the alternative that keeps every upstream test
release entirely in test. Never combine records produced using different partition
manifests. The optional downloaded `swe_extra` exploration release is not included in
the default manifest, prepared task count, or experiments.

Within `calib`, group-disjoint subsets are reserved for:

1. `critic_train`: 50% of calibration task groups.
2. `probability`: 25%, for temperature fitting only.
3. `verifier_stats`: 25%, for verifier and restoration statistics only.

Thresholds are chosen on `val`. Test/backbone labels never fit critics, temperature,
verifier operating characteristics or thresholds. Pretrained-model contamination
cannot be ruled out by task splitting; disclose model provenance and dataset dates.

## 3. Labels and natural trajectories

Internal labels use **error_label=1 for error, 0 for correct**, the inverse of the
proposal's Y(correct)=1. This convention is consistent throughout the package.

Only original tasks are downloaded. Your policy's rollouts on those tasks are natural
experimental observations, not invented task data. There is no fault-injection or
synthetic-trajectory generator.

GSM8K final numeric answers have deterministic semantic labels. Intermediate steps
require independent tests with meaningful postconditions or expert adjudication.
`read_file` returning successfully does not mean it was the correct file to inspect.
Nonzero pytest can be an appropriate diagnostic action; its exit status is marked
operational, not semantic. A verifier FAIL is never automatically a ground-truth error.
MATH exact matches may be marked correct, but unmatched expressions are not automatically
semantic errors because an equivalent expression can have a different surface form.

Annotation queues hide critic/verifier outputs. Fill labels from independent evidence
and document the basis in `label_source`. Use two independent annotators and resolve
disagreements for publication; the software cannot supply expert truth automatically.
Fit/replay reject mixed scopes and unknown eligible labels. This prevents selective
exclusion of unlabeled actions after looking at their outcomes.

## 4. Calibration, verifier statistics and recovery

Raw prompted critic probabilities are **uncalibrated**. Temperature fitting occurs
only on the `probability` groups. `critic_train` is used only if you train the linear
or LoRA critic; rescoring a new critic invalidates old calibration.

Per-class detection and false-positive rates require both positive and negative labels
and complete verifier audit coverage. Counts and Wilson intervals are retained. These
intervals are action-level descriptive intervals, not a correction for within-task
dependence; the final policy comparison uses task-cluster bootstrap.

Restoration trials use observed natural state changes. Audit collection snapshots the
post-action state, restores the pre-action workspace and verifies its hash, then restores
the post-action state to continue the original trajectory. No fault is planted.

The estimated residual loss is **workspace-hash restoration failure**, not the full
economic/semantic consequence of a bad action. For pre-execution verifier rejection,
restoring an unchanged workspace gives particularly weak recovery evidence. The
artifact explicitly records `recovery_scope=workspace_hash_only`. Report this limit;
do not claim empirical external-side-effect recovery. Classes without sufficient
evidence fail fitting/use rather than receiving made-up rates. The minimum count of
five per outcome is an engineering guard, not a statistical-power guarantee.

The supplied equation itself assigns little avoided loss to rho≈1 actions even when
pre-execution verification could prevent an irreversible effect. This is a modeling
limitation of that equation, not silently corrected in code. External tools are disabled.

## 5. Replay and baselines

Use collection mode: `policy=never`, `audit_all=true`. Every allowed action receives
a verifier verdict, but the verdict does not gate the behavior policy. Offline audit
costs are recorded separately from deployment cost. Shared safety-floor blocks are
excluded from optional-verifier allocation and counted separately.

Replay traverses each recorded trajectory chronologically. It does not sort the whole
trace using future knowledge. Eight policies are provided: never, always, random,
confidence, impact-only risk, error×impact, `bavar_style`, and RC-VoV. `bavar_style`
is an explicitly named probability×impact/cost heuristic, **not a reproduction of a
specific BAVAR paper**. The proposal did not provide a reproducible BAVAR/BEAVER algorithm.

Metrics distinguish errors selected for verification, errors actually caught by FAIL,
false rejections and consequential catches at impact≥0.5. Precision follows the proposal's
selection definition; detection recall is reported separately. Policies can differ in
budget utilization even at identical caps; always inspect the spend column.

Paired bootstrap resamples task groups, keeping repeated runs clustered. Tests on other
backbones require actual rollouts from another model. A `backbone` split name alone
does not demonstrate transfer. Keep critic/verifier configurations fixed for transfer.

## 6. Online evaluation and failure reporting

All baselines share floor, sandbox, tools, action budget, observation sanitation and
stopping rules. Compare identical task IDs with the same policy model and seed. Audit
mode should be off for deployment comparisons. Critic overhead is included in total
online tokens even for baselines that do not use the score, yielding a controlled
gating comparison rather than an optimized-baseline deployment comparison.

SWE results remain null until the upstream harness grades predicted patches. Reaching
`final_answer`, an exit code of zero or a PASS verifier is not a resolved SWE issue.
Unfinished math tasks are counted as failures for final-answer accuracy. Infrastructure
errors are separately saved in `failure.json`; incomplete runs are not successful runs.
When an API omits usage, measured-token completeness is false rather than fabricated.

Recovery comparison requires actual paired checkpoint and restart runs. The package
does not fabricate a restart cost by multiplying step counts. Context and successful
work are reset in restart mode after verifier rejection, while the total step limit
and spent verification budget persist.

## 7. Isolation and reproducibility

The durable transaction boundary is the workspace filesystem. SQLite is allowed only
there, and connections close per action. Container-root changes outside that workspace
are discarded between actions. Package-install persistence and external APIs are not
supported. Containers receive no host bind mounts, user credentials or network access.

Dataset preparation/building may use network access. Only inference execution is
network-isolated. Upstream image setup and evaluation execute repository code in Docker;
build on a dedicated research machine. Images containing symlinks or special files
are rejected by this implementation rather than allowing an escaping extraction.

Snapshots verify paths, contents, empty directories and permission modes. Ownership,
timestamps, xattrs, process state and distributed services are not restored. The Docker
filesystem export limit is 256 MiB; large repositories may need a deliberate adjustment.
The container provides CPU/memory/process limits, but Docker storage must also have a
host-side quota for adversarial workloads. The sanitizer is best-effort; it is not an
air-gap proof and does not implement a complete AgentDojo defense.

SQLite triggers and SHA-256 chains detect ordinary mutation. A filesystem administrator
can still rewrite files and manifests. Anchor hashes externally or use WORM storage if
you require tamper resistance. Optional Fernet encryption is whole-file and needs memory
proportional to export size; keep keys outside the dataset directory.
