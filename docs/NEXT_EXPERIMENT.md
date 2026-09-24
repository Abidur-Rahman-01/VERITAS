# Recommended next experiment after the Qwen 7B pilot

This assessment is based on the user's pasted Windows outputs. The Windows event
database itself is not accessible from the current macOS workspace.

## What the pilot establishes

- Local Ollama, Docker, action execution, final-answer grading and event logging worked
  together on one original GSM8K development task.
- The supplied test log reports 52 passing tests and 58% statement coverage. It does
  not establish that every runtime path or security property has been validated.
- The pilot used `policy=never`, zero verification budget, and audit-only verification.
  It therefore does not measure the benefit of RC-VoV.
- Total collection model tokens were 1,937 + 1,041 = **2,978**. The 1,937 figure is the
  deployment-accounting subtotal, excluding offline audit work.
- The critic consumed 841 tokens compared with 1,096 policy tokens: about **77%** additional
  tokens relative to policy-only operation on this task. This is one observation, not a
  population estimate. The reported 9.39 seconds includes collection/audit work.
- Printing a number and submitting it do not demonstrate recovery from a damaging
  mutation. A 0.016-second successful restore is an integrity check, not a measured
  token-saving advantage.

## Priority 1: make the main claim testable

Use this initial claim:

> On real repository tasks, does estimating verifier effectiveness and action consequence
> improve verification allocation over calibrated error×impact at the same declared
> resource budget, and does that advantage persist in independent online runs?

Treat full transactional-recovery benefits as a separate claim until a nontrivial
recovery experiment exists. In the current normal runtime, failed verification blocks
the candidate before execution. Restore on that branch is normally a no-op. Audit
collection does exercise post-action workspace restoration, but it does not show that
recovery improves deployment outcomes.

Do not predeclare a desired 30–60% saving or require p<0.01 as an acceptance criterion.
Choose a practical effect size and analysis plan before final evaluation; retain null
or negative results. No particular figure or p-value guarantees a conference acceptance.

## Priority 2: remove comparison confounds before spending more compute

1. Choose a common budget scheduler for RC-VoV and error×impact, and separately ablate
   adaptive pacing. Currently only RC-VoV has the dynamic threshold term.
2. The current `bavar_style = p_error * impact / verifier_cost` is the same ranking as
   error×impact when cost is constant. It is not a reproduced published BAVAR baseline.
   Different threshold grids must not be presented as algorithmic evidence.
3. Fixed call-credit caps are not matched actual tokens or GPU compute. Either make
   the claim explicitly about call budgets, or add real compute/token accounting and
   a corresponding reservation policy. Always report actual spend and utilization.
4. Include both common-instrumentation comparisons and a deployment-efficient never-verify
   baseline that does not invoke an unused critic. Otherwise baseline cost is inflated.
5. Add evaluation of calibration on held-out validation/test groups. The artifact's
   before/after calibration metrics are currently measured on the probability-fitting
   subset. They are not a held-out reliability result. Report discrimination too; good
   calibration alone does not establish useful error ranking.
6. Separate the conservative execution taxonomy from claims about consequence. The
   current Python tool gets environment-mutation impact even for a pure calculation.
   Report this as a surrogate weight and test sensitivity rather than claiming actual
   high-impact damage was observed.

For fixed d, f, rho, impact and cost, the proposed score is affine in p_error:

```text
delta = p_error * [d * (1-rho) * impact + f * false_alarm_cost]
        - verifier_cost - f * false_alarm_cost
```

Consequently, experiments need real variation in verifier usefulness, impact or cost
to identify an allocation advantage over confidence. Do not artificially manufacture
variation. Use naturally diverse real repository actions and measure it.

## Priority 3: a small, labeled development pilot

Start with 3–5 supported SWE tasks to check historical environment setup and official
grading. Then expand to approximately 20–30 development tasks across several repositories,
with GSM8K retained as a simple secondary check. These are planning sizes, not guarantees
of statistical power. Predeclare selection, keep failures, and do not cherry-pick favorable
tasks. Keep the policy model fixed initially.

Use the already working Qwen2.5-Coder 7B policy. A 14B verifier is an optional candidate
to test on development data if its measured latency and memory use are acceptable; its
presence in Ollama does not establish that it is better or practical. Avoid changing
policy, critic and verifier together. Independent test/human labels remain necessary
even if separate models are used.

Record these pilot diagnostics before deciding batch size:

- Task completion, action counts and action-class distribution.
- Correct/error/unknown semantic labels by class, including naturally occurring errors.
- Verifier detection and false-rejection counts, including uncertainty intervals.
- Policy, critic, verifier and audit costs separately; latency and failure rates.
- Accepted mutations with real pre/post state changes and restoration evidence.
- Budget utilization and whether the proposed caps actually constrain verification.

For two-step trajectories with 0.02 credits per verifier call, a budget of 0.04 already
permits all actions to be checked. Larger caps add little information. Choose the grid
from development trajectory lengths, not from final test outcomes.

Ground-truth adjudication is the immediate data bottleneck. A final correct GSM8K answer
does not automatically label all preceding actions correct. A successful shell command
does not prove semantic correctness. A failing pytest run can be a useful diagnostic.
Label these separately, and use reviewers blinded to critic/verifier outputs where possible.

## Priority 4: then collect the correct partitions

`dev` is for development. The pasted suggestion to collect 100 dev tasks and then fit
calibration is not sufficient: the implementation fits only `calib` tasks with the
appropriate inner role.

After the pilot issues are resolved, start with roughly 100–200 calibration tasks and
50–100 disjoint validation tasks, then grow according to actual per-class error counts
and uncertainty. Use task-level clusters; action count is not independent sample count.
The code's minimum of five errors/five correct actions is a runtime guard, not a
publication-level sample-size justification. Natural errors may require more collection.

For the current math collection path, this is a **future inference command**:

```text
uv run veritas collect --config configs/experiment.yaml --override configs/collection.yaml --source gsm8k_train --split calib --limit 100 --output runs/calib-pilot-v1
```

For SWE, prepare the matching image map and use the documented research-pool split.
Keep Verified reserved. Export, adjudicate, fit temperature/verifier statistics, then tune
thresholds on validation. Leave neural fine-tuning until a prompted/linear-critic baseline
shows that the measurement and allocation setup is informative.

## Priority 5: freeze and evaluate

Only after the setup and primary hypotheses are frozen:

1. Run chronological audit replay with complete independent labels and verdict coverage.
2. Run actual matched-task online baselines; do not infer task success from fixed traces.
3. Grade SWE patches with the official harness.
4. Use paired task-cluster confidence intervals and a prespecified primary budget/endpoint.
5. Use pilot variance to plan final evaluation size and backbone-transfer runs.
6. If the value calculation adds no benefit beyond calibration and common budget pacing,
   report that result and revise the hypothesis before increasing experimental scale.

A useful first deliverable is a pilot-quality table with measured errors, false alarms,
costs and task outcomes. It is more decision-relevant now than a polished frontier based
on weak labels or confounded baselines.

The pasted recovery CLI flags do not exist in this version. Restart is configured with
`--override configs/restart.yaml`; default mode is checkpoint. That comparison alone
does not resolve the substantive recovery-design issue described above.
