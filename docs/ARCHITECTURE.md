# VERITAS: long-horizon LLM problem solving with iterative verification

This is the main guide to the VERITAS research program and software. The primary paper direction
is long-horizon LLM problem solving with an explicit verifier-and-repair loop across code and
reasoning tasks. The repository also contains a separate evaluation-awareness study and an older
dependency-verification line; those are distinct projects and do not define the main paper question.
Distinguish completed runs and measured results from designs and planned work.

**Research direction:** evaluate whether iterative verifier feedback and bounded autonomous repair
improve end-task success, and characterize their quality, compute, and failure modes over
long-horizon tasks. The awareness factorial documented later is a separate exploratory study,
not the central claim of this paper.

**Evidence status:** README and the run reports record completed benchmark and calibration work,
while the awareness factorial has its own separate report and artifacts. This guide does not
independently verify those runs. For every headline number, retain the exact source record, task
denominator, model/runtime identity, and grading procedure; mark plans and exploratory studies as
such.

### Prior awareness study: design review notes

| Proposed assumption | Verified finding / design correction |
|---|---|
| Add disclosure to `build_context()` | That helper is unused by the active runtime. Update both active prompt branches through `context.py`. |
| `controller.py` already assigns experimental `A` | It makes per-action, budget-dependent selections. Add a frozen task-run assignment independently of the existing controller. |
| No runtime-loop change is needed | Existing non-PASS reviews block actions and trigger replanning; PASS is not explicitly delivered. Use one draft review followed by equal revision allowances. |
| Shadow mode is new | `audit_all` / `StepRecord.audit_only` already suppress feedback and track audit tokens. They also run probes/checkpoint restoration online. Use deferred audits for this experiment. |
| Shadow verdict gives counterfactual correction value | It measures findings, not whether the actor would successfully repair them. Correction requires randomized feedback and independently graded continuations. |
| Reuse dependency analysis unchanged | Its `group_id` is generally a deduplicated task ID, not a repository. It checks dependency execution modes and aggregates different inputs. Reuse helpers with new joins, weights, missingness rules and repository clusters. |
| `labels.py` already supplies SWE `Y` | `grade_answer()` returns `None` for SWE. `comparison.grade_swe()` / `swe.py` supply the harness path and need an outcome adapter. |
| Stage 0 traces determine success ICC | Ungraded behavioral proxies cannot estimate the intraclass correlation of binary repair success. Add a graded pilot on the intended actors. |
| Nonzero awareness necessarily violates a gate's target | The sign and magnitude depend on the calibration and deployment populations. Test transfer empirically; a change can improve risk, worsen it, or leave it unchanged. |

The repository contains benchmark runners, verifier/controller workflows, model comparisons,
full-dataset execution scripts, and a separately implemented awareness-study pipeline. Check each
run's records and reports before using its outcomes as evidence; a runner or passing software test
does not establish a scientific result.

## Quick decision sheet

| Item | Current recommendation |
|---|---|
| Main paper direction | Long-horizon LLM problem solving with iterative verifier feedback and bounded autonomous repair. |
| Core question | When does a verifier-guided draft → review → repair loop improve end-task success, and what compute and failure costs does it add? |
| Evidence base | Full-split runs across GSM8K, MBPP, HumanEval, and MATH-500, plus repository-level SWE studies and multi-model comparisons; report each track with its own protocol and denominator. |
| Primary outcomes | Independently graded task success, successful repairs from initially failing drafts, regressions, compute, and runtime. |
| Main design improvement | Add matched no-feedback controls, hold inference budgets constant, and report per-task transitions to isolate verifier benefit from extra attempts or tokens. |
| Awareness study | Separate exploratory line. Preserve its protocol, code, and records as a distinct study; do not make it the main paper framing. |
| Immediate priority | Freeze one primary question, reconcile reported counts against source artifacts, and run a controlled comparison that isolates feedback from extra effort. |

For the related-work audit and claim-by-claim novelty status, see [NOVELTY_AUDIT.md](NOVELTY_AUDIT.md).

## Main paper opportunity: measure verifier-attributable recovery

The full benchmark results are a useful starting point, but a high pass rate and a count of
successful repairs do not by themselves show that verifier feedback caused the repairs. A stronger
paper would estimate the **incremental value of verifier feedback under a fixed inference budget**.

For each task, retain the initial answer, verifier result, revision, final independent grade, token
use, and runtime. Compare matched randomized arms:

| Arm | Draft | Additional allowance | Feedback |
|---|---|---|---|
| Draft-only | One initial attempt | None | None |
| Self-revision | One initial attempt | One revision with the same token/step cap as the treatment | No verifier findings |
| Verifier-guided repair | One initial attempt | One revision with the same token/step cap | Standardized verifier findings |

The primary causal contrast is verifier-guided repair minus self-revision on independently graded
final success. Also report recovery among initially failing tasks, regressions among initially
passing tasks, and added compute per additional task solved. Use a frozen task set, randomize within
task/model blocks, and show task-family and model-specific estimates with uncertainty intervals.
Keep GSM8K, MATH, HumanEval, MBPP, and repository repair as separate strata; they have different
graders and failure modes.

This design can make the existing results more informative without inferring a new capability from
the aggregate repair count alone. The potential contribution is a **large-scale, trajectory-level
measurement of verifier-attributable recovery and its cost across long-horizon task families**.
That is a direction to develop, not a settled novelty claim: compare it with current literature,
and do not claim causal gains until these matched comparisons exist.

## Main paper research questions

Keep one primary estimand and treat the remaining questions as secondary or separate studies.

| ID | Status | Research question | Primary evidence needed |
|---|---|---|---|
| RQ1 | Primary | On independently graded repository repairs, how much does actionable verifier feedback improve final success over an equally costly generic retry? | Randomized, task/model-blocked comparison; independent SWE grading; total cost measured for actor, reviewer, and tools. |
| RQ2 | Secondary | How does verifier value vary by task family and initial answer state? | Separate task-family results; recovery on initially failing tasks; regression on initially passing tasks. Do not pool incompatible graders into one accuracy estimate. |
| RQ3 | Secondary | Which failure types are recoverable, and does repository localization explain failures beyond semantic repair quality? | Blinded trajectory and patch coding on a representative sample; inter-rater agreement; held-out randomized localization intervention before causal claims. |
| RQ4 | Secondary | What success, regression, and compute tradeoff does the repair loop produce as the number of steps or available budget grows? | Budget sweeps with matched total system cost and fixed task/model cohorts; report success-cost curves and stopping behavior. |
| RQ5 | Secondary | Does the result replicate across model families, scales, and task families? | Same frozen protocol across actors; report model-by-treatment and task-family interaction intervals, not only pooled averages. |
| RQ6 | Separate awareness study | Does an advance evaluation cue change persistence or repair outcomes, and does it interact with actual verifier feedback? | Separate randomized D × A study, informative non-floor tasks, adequate power, and reconciled cohort ledger. Do not merge its runs into RQ1. |
| RQ7 | Deferred | Does a frozen verification gate calibrated in one setting transfer to held-out tasks, repositories, or awareness conditions? | A preregistered gate-transfer study with separate development, calibration, and untouched confirmation pools. No result is established by architecture alone. |

**Scope decision:** RQ1 is the paper's primary claim. RQ2–RQ5 explain where and why it holds. RQ6 is a separate study line; RQ7 is deferred until a gate and valid transfer data exist. A single paper should not claim all seven as equally tested contributions.

## How to test the full benchmark suite

The supplied full-scale report is broad coverage evidence, but its current loop result does not isolate verifier value. Preserve it as the existing system-performance result, then use saved task records where possible and rerun only the missing counterfactual conditions.

### 1. Freeze and validate the task ledger

For every item record dataset/version, task ID, model tag and revision, prompt/config hash, sandbox image, assigned condition, random seed or decoding settings, start/end time, per-role token use, verifier call and output, each draft/revision, and each independent grade. Verify that tasks are unique and that every benchmark denominator equals its official split. Store the initial attempt and final attempt separately.

### 2. Run matched conditions

Use these conditions on the same task/model blocks, randomize execution order, and start each arm from a clean task state:

| Condition | Use | Budget handling |
|---|---|---|
| Initial draft | Establish one-shot baseline and starting correctness. | One fixed actor allowance. |
| Generic self-retry | Measures the value of another chance without verifier findings. | Same total system allowance as the feedback arm. |
| Verifier-guided repair | Tests actionable feedback. | Count verifier and actor usage; use the same total cost cap as generic self-retry. |

Report two comparisons: (a) **equal total budget**, where reviewer cost is charged against the same total budget available to the retry control; and (b) **equal actor revision budget**, where the reviewer cost is reported as additional deployment overhead. Token counts alone do not equal compute across model sizes, so also report wall time and local hardware/energy information when available. Draft-only remains a useful baseline but is not the main causal comparator.

When a common initial draft can be safely reused across revision conditions, freeze and hash it before randomizing feedback. Otherwise randomize the whole trial within task/model blocks and analyze the task as the unit. Never give the control arm hidden verifier findings, hidden gold labels, or grader internals.

### 3. Use task-appropriate independent graders

| Task family | Final success grade | Feedback allowed to the actor | Leakage and validity checks |
|---|---|---|---|
| GSM8K | Exact normalized numeric answer, using a frozen parser and official answer key. | Only the prespecified verifier feedback; never expose the gold answer or exact hidden test result unless that is the treatment being tested. | Manually audit parser edge cases, units, equivalent forms, and failed parses. |
| MATH-500 | Exact normalized answer under a frozen answer parser; separately audit symbolic equivalence where the parser supports it. | Frozen, reproducible diagnostic/check output. | Audit parser correctness and ambiguity; do not treat an LLM judge as ground truth without calibration. |
| HumanEval | Official harness and hidden unit tests in the isolated sandbox. | Only allowed test/verification diagnostics; keep hidden tests and expected outputs private. | Pin harness/runtime; verify no test or reference solution exposure. |
| MBPP sanitized | Pinned sanitized split and official test execution. | Same policy as HumanEval. | Record sanitized version, exact test IDs, harness, and exclusions. |
| SWE repository repair | Pinned repository commit and independent SWE-bench-compatible grading harness. | The assigned feedback arm receives the frozen patch-review or test diagnostic; control receives no verifier findings. | Verify base commit, patch application, test-image identity, grading retries, and hidden test isolation. |

For every task family, report the first-draft score and post-intervention score. Define success before running: no post hoc acceptance rules. A verifier may be fallible; retain its raw verdict and independently grade the final artifact.

### 4. Analyze recovery, regression, and cost

Report final success difference between verifier feedback and equal-budget retry as the primary effect, with a confidence interval. Also report: recovery rate among initially failing drafts; regression rate among initially passing drafts; net change over all tasks; verifier false-positive/false-negative rates where labels permit; tool calls; actor and verifier tokens; elapsed time; and cost per additional resolved task. Use task-paired randomization inference or paired bootstrap, with clustering by repository for SWE and by task for fixed benchmark items. Report all model/task strata and missing/failed runs; do not drop inconvenient failures.

Use a graded pilot on the exact tasks and models to estimate baseline success, variance, within-task correlation, repository clustering, and missingness. Set a minimum meaningful effect and simulate power before selecting confirmation size. Freeze the task manifest, analysis, test family, exclusion rules, budget cap, and stopping rule before confirmation. The 2,240-task suite provides useful pilot data, but not a substitute for randomized equal-budget controls.

## Recent-paper comparison and current VERITAS values

The following literature figures were checked against publisher, conference, or primary paper records on 2026-10-19. VERITAS numbers in the second column are **reported in the supplied project summary and have not been reconciled here against raw artifacts**. These studies use different tasks and endpoints; the table is a novelty comparison, not a leaderboard.

| Work / value reported | VERITAS reported value | Interpretation for novelty |
|---|---|---|
| *Which quality gates actually improve agentic software maintenance?* ([IST article](https://www.sciencedirect.com/science/article/pii/S0950584926003526)): 458 paired TAM-Eval tasks, five Qwen2.5-Coder sizes, 30,524 model-policy-task observations, matched generic-retry control; command-content acceptance without repository execution. Feedback value varied by model/policy. | 2,240 tasks, 1,894 final resolutions (84.55%), 101 recorded draft-to-pass repairs; 2,036,367 tokens; 12.07 hours. No equal-budget generic-retry comparator in the supplied master table. | Prior work already isolates feedback from retry opportunity. VERITAS's possible extension is real repository patch execution and independent task grading under matched total budgets. The supplied result is not yet evidence for that extension. |
| ASE APR 2026 ([feedback granularity study](https://conf.researchr.org/details/ase-2026/apr-2026-papers/8/Evaluating-Symbolic-Feedback-Granularity-for-LLM-Based-Program-Repair)): 540 HumanEval+/MBPP+-derived tasks, five feedback modalities, token-matched and redundant-feedback controls; counterexamples strongest. | HumanEval: 137/164 resolved (83.54%), one reported verifier repair. MBPP: 215/257 (83.66%), six reported repairs. | Function-level repair and feedback modality are already studied. VERITAS should focus on multi-step/repository repair, transitions, and task-level heterogeneity, not claim first iterative code repair. |
| *VeriHarness* ([primary paper](https://arxiv.org/abs/2610.00972)): five long-horizon workspace benchmarks, two frontier models, ~26,000 rollouts; evidence-backed revision improved over one rollout by 6.2 points for Gemini 3.5 Flash and 6.4 for Claude Opus 4.8 (as reported in its abstract). | GSM8K: 1,196/1,319 resolved (90.67%), 50 repairs. MATH-500: 346/500 (69.20%), 44 repairs. These are final loop results, not a matched causal feedback contrast. | Long-horizon verification and revision are occupied. VERITAS needs the equal-budget causal estimate and its task-family/recovery analysis. GSM8K/MATH outcome percentages are not directly comparable to workspace artifact scores. |
| Anthropic coding-audit realism ([study](https://alignment.anthropic.com/2026/coding-audit-realism/)): audit realism win rate rose 4.6% → 32.8% for reward-hacking scenarios after giving auditors real deployment resources; endpoint is realism, not repair success. | Awareness inventory: 128 runs across 12 studies; 4.77M tokens, 2,365 tool calls, 40.52 hours. `cmd2` report: surrender 4/4 without cue versus 0/4 with cue; tokens 23,631 versus 75,084 in that cohort. | Awareness in coding contexts is active prior work. VERITAS may offer a different randomized behavioral endpoint, but the cohort size and protocol accounting must be audited; do not equate realism measurements with causal repair outcomes. |
| IEEE TSE [SOSRepair](https://ieeexplore.ieee.org/document/8854217): 22/65 ManyBugs defects patched; improved localization raised patches passing independent tests to 16/23 among manually localized cases. | One cmd2-744 example shows a plausible directory-creation idiom placed in a new file rather than the target module. | The general localization bottleneck is established. VERITAS's value would be quantitative trajectory classification plus a held-out intervention, not the single anecdote. |
| — | Full benchmark detail: GSM8K 1,196/1,319 (90.67%, 50 repairs); MBPP 215/257 (83.66%, 6); HumanEval 137/164 (83.54%, 1); MATH-500 346/500 (69.20%, 44); total 1,894/2,240 (84.55%, 101). | These are reported post-loop scores. Reconcile denominator, harness, and repair transitions before publication; no control effect can be inferred from the totals. |
| — | Llama 3.1 8B multi-task factorial, N=16: Arm 00 44,048 mean tokens / 20 calls / 25% surrender; Arm 01 35,824 / 15 / 25%; Arm 10 46,356 / 20.25 / 0%; Arm 11 46,638 / 21 / 0%. Reported valid patch rate is 100% on CLI, while SWE resolution remains a different endpoint. | Descriptive small-cohort arm summaries. They do not establish differences in repair success; preserve per-task uncertainty and specify which trial records are included. |
| — | Cross-dataset cue pilot: domains mostly N=2; Meta Synthesis N=10, reported 90% pass in arms 00/01 versus 100% in arms 10/11, 1.10× token ratio, 8 repairs and 0 regressions. | Useful hypothesis-generating result only. Tiny strata do not establish cross-domain generalization. |
| — | Local model calibration, seven tasks/model: Qwen2.5-Coder 30B 6/7; Qwen2.5-Coder 14B and DeepCoder 14B 4/7; DeepSeek-Coder-V2 16B 2/7; Granite-Code 20B and StarCoder2 15B 0/7. | Pilot calibration only; too small for definitive model ranking or parameter-scale claims. |

**Interpretation:** VERITAS has a substantial reported benchmark inventory, but breadth and task count are not the same as novelty. The distinguishing value must come from auditable task transitions, matched cost controls, independent grades, repository-level external validity, and a tested explanation of when feedback helps or harms.

**Cohort reconciliation required:** `RESULTS.md` reports a 32-run primary SWE factorial cohort with 0 resolved tasks, while the supplied executive summary presents a 128-run inventory and 4/4 versus 0/4 CLI surrender comparison. These can coexist if they are different cohorts, but every table and inferential test must identify the exact included studies, tasks, assignment records, and preregistration status. Recompute the p-values and FDR family from row-level data before using “all tests remain significant.”

## Venue fit and two paper routes

“Transactions-level” can mean different editorial goals. TMLR is **Transactions on Machine Learning
Research**. Its current published criteria ask whether claims have accurate, convincing, clear
evidence, whether the findings interest some part of its audience, and whether the paper explains
the work clearly; it is not accurate to describe it as judging correctness alone or as having no
interest criterion. See the [TMLR Editors-in-Chief criteria update](https://blog.tmlr.org/2026/increasing-emphasis-on-clear-writing-in-acceptance-criteria/).
IEEE TSE's stated scope seeks well-defined theoretical results and empirical studies with potential
impact on software construction, analysis, or management. See the [official TSE scope](https://www.computer.org/digital-library/journals/ts/cfp-ieee-transactions-on-software-engineering).

| Target route | Strongest fit | Evidence and framing required | Current position |
|---|---|---|---|
| TMLR | A general lesson about how LLM agents use external verification, how feedback changes recovery versus generic retries, and the cost/quality tradeoff across task families. | A preregistered, powered experiment; transparent nulls and uncertainty; task-family/model heterogeneity; convincing evaluation; clear relevance to ML researchers beyond a system score. The full multi-benchmark track can support breadth only if task-specific effects and graders are handled correctly. | Plausible first target after evidence repair. The current post-loop suite is not enough because it has no equal-cost retry contrast. The awareness study is not ready because of small/floor cohorts and accounting conflicts. |
| IEEE TSE | A substantive software-engineering result about repository-level repair, quality gates, patch correctness, or where repair pipelines fail. | Real repository tasks; independent SWE grading; matched retry/feedback budgets; at least two actor families for robustness; trajectory and patch analysis; meaningful engineering implications and reproducibility. Use HumanEval/MBPP as secondary evidence, not the main TSE contribution. | Higher empirical and software-engineering contribution bar. The present 2,240-task suite is useful context, but a controlled SWE-ReBench-style study and validated failure analysis are still needed. |

The awareness D × A factorial may be the project's **most distinctive candidate question**, because it asks whether advance disclosure changes behavior separately from delivered feedback. That is a novelty hypothesis, not an established result. A separate awareness paper becomes plausible only after the full randomization ledger is reconciled, tasks have non-floor resolution rates, the trial is powered, and the effect replicates beyond the 4-versus-4 `cmd2` cohort. Do not combine its exploratory 128-run inventory with the main equal-budget repair study to inflate sample size.

### Submission-quality sequence

1. Reconcile all records and rewrite the claims table so every number points to an exact run set and endpoint.
2. Decide whether the first manuscript targets a general ML audience (TMLR route) or a software-engineering audience (TSE route); do not submit the same broad framing unchanged to both.
3. Run a graded pilot for the selected primary estimand and use it to power a frozen confirmation study.
4. Complete the equal-cost retry control, independent grading, model/task stratification, and preregistered failure analysis before writing causal conclusions.
5. Report null or small effects with the same care as positive results. A well-powered finding that feedback adds little beyond retry can be useful if the measurements and limits are clear.

## Separate study record: evaluation awareness and verifier feedback

The following sections retain the awareness-study design, literature notes, and implementation
details for reproducibility. They are not the main paper direction described above.

The numbered awareness sections below are retained as a distinct study record. Their hypotheses,
power plan, D × A analysis, and gate-transfer proposal are not evidence for main-paper RQ1 unless
the shared task/protocol linkage is explicitly justified and preregistered.

#### 1. The core concept (awareness study)

**A coding agent may behave differently when it expects its work to be checked. That behavioral
change can happen before any verifier runs or gives feedback. A normal “verify versus do not
verify” comparison mixes this anticipatory effect with the verifier's direct ability to find
errors and help fix them. VERITAS will separate those two effects.**

The core concept is a controlled decomposition of verification into:

1. **Evaluation awareness / anticipation:** the agent is told that an independent reviewer may
   inspect its work. Does this change what it does or the quality of its final repair when no
   verifier feedback is delivered?
2. **Feedback / correction:** an independent verifier actually reviews the proposed work and
   returns a fixed kind of feedback. Does that improve final repair quality?
3. **Their interaction:** does feedback help more, or less, when the agent knew review was
   possible?

The main endpoint is **independently graded coding-task success**. Tests added, diff size,
number of tool calls, repair attempts, regressions, time, tokens, and verifier findings help
explain the outcome. They are secondary measures and cannot replace the final task grade.

Use “evaluation awareness” or “anticipatory effort” for the first mechanism. “Deterrence” would
imply a credible penalty for failure; the proposed experiment only makes review salient. The
experiment tests the effect of an assigned cue. It cannot directly observe an LLM's private
belief or prove intentional deception.

#### 2. The research goal and paper question (awareness study)

### Main question

> When a coding agent is told that its work may be reviewed, does its repair behavior or final
> success change even without verifier feedback, and how does that compare with the causal
> effect of actually delivering verifier feedback?

### Secondary question

> If a verification policy is calibrated or evaluated under one awareness condition, does its
> measured call yield, repair risk, or cost-quality tradeoff change under another awareness
> condition?

This secondary question gives the study a systems and deployment implication. The paper should
not claim that existing policies make a particular formal guarantee unless the original policy
actually promises that guarantee and the experiment tests its assumptions. The paper should
measure the policy consequence directly: for example, a difference in predicted versus observed
repair success, verification yield, or success per unit cost across cue conditions.

### What the paper is not claiming

- It is not claiming that audit awareness, monitoring, deception, or selective verification are
  new concepts in general.
- It is not primarily a paper about the target/caller dependency graph or the old four-arm
  dependency pilot.
- It is not claiming a conformal or distribution-free safety guarantee.
- It is not assuming a verifier is correct. The verifier is another fallible measurement system.
- It is not equating an agent saying “I am confident” with correctness or with private belief.
- It is not claiming a result or A* acceptance before the experiment exists.

The novelty is provisional: the potential contribution is the combined causal study of an
awareness cue and actual verifier feedback on coding repairs, with independent task grading, plus
a measured consequence for evaluating verification policies. A focused literature review must
still confirm that this exact combination is not already published.

#### 3. Experiment design: the four conditions

Randomize two factors at the task-run level, blocked by task and model:

- `D` = whether the actor receives the evaluation-awareness cue.
- `A` = assignment to receive one independent draft-patch review before revision. Actual review
  success and delivery are recorded separately; a failed review does not change the assignment.

| Arm | Cue `D` | Feedback `A` | Scientific interpretation |
|---|---:|---:|---|
| `00` | No | No | Baseline repair with no review cue and no verifier feedback |
| `10` | Yes | No | Anticipation: cue is present, but no verifier feedback is delivered |
| `01` | No | Yes | Correction: verifier feedback is delivered without an advance cue |
| `11` | Yes | Yes | Combined awareness and feedback condition |

Let `Yda` be the probability of final repair success in arm `da`. Pre-register these contrasts on
the probability scale:

```text
Anticipation when no feedback is delivered = Y10 - Y00
Feedback effect without an advance cue      = Y01 - Y00
Feedback effect when cued                   = Y11 - Y10
Interaction                                 = Y11 - Y10 - Y01 + Y00
Combined effect                             = Y11 - Y00
```

The combined effect can be written as anticipation + feedback-without-cue + interaction. Report
these absolute effects and uncertainty intervals. A percentage “share of verification value”
can be unstable when the combined effect is small or changes sign; treat any ratio decomposition
as secondary and report its interval.

### What counts as feedback? The v2 decision

Use **one review at the draft-patch boundary**, then give every arm the same revision allowance.
This replaces the earlier suggestion of reviewing each action. A single boundary bounds cost,
allows the reviewer to see an actual patch, and separates pre-feedback behavior from revision.
Action-level gating remains a later policy experiment.

In `A=1`, deliver one bounded review message, including a PASS/no-findings message when applicable.
In `A=0`, deliver the fixed neutral continuation message. All arms can keep their draft or edit
and test it using the same tools and revision budget. A verifier cannot reject an action, choose
the final patch, or grant additional attempts in v2. A review error produces a fixed unavailable
message and consumes the same review opportunity; never relabel it as PASS or move it to `A=0`.

The primary analysis is intention-to-treat by assigned `A`, including review failures. It
estimates the effect of offering this review package under fixed actor allowances. It does not
isolate helpful diagnostic content from reassurance, review salience, or the extra input text.
That narrower mechanism would require another control condition.

Consequently, “correction” is shorthand for the **effect of assigned verifier feedback**.
Receiving feedback can itself make review salient in `D=0,A=1`. The factorial identifies the
advance-disclosure effect and the feedback-package effect; it does not identify two pure
psychological mechanisms or assume `D=0` models have no prior expectation of evaluation.

For `A=0`, the online path has no verifier call. A prespecified sample of saved drafts can be
audited **after actor execution has finished**, with results written outside the workspace and
never returned to the actor. Record audit selection probability, usage, latency, verdict, and
errors. This also avoids hidden audits competing with actor inference for a local GPU.

Sample both `D=0,A=0` and `D=1,A=0`, with known inclusion probabilities. This allows a comparison
of reviewer finding rates under disclosure. A shadow FAIL is neither ground truth nor a
measurement of the unobserved repaired outcome. Use independent draft grading on a prespecified
subset if draft correctness is needed; keep its cost and labels outside actor execution.

### Make the cue a clean treatment

The cue should communicate possible independent review without adding task guidance such as “be
careful,” “write more tests,” or “avoid risky changes.” The primary `D=0` arm keeps the common
task prompt without a review sentence. Hold constant tools, system prompt, model parameters,
actor allowances and repair rules. A length-matched neutral sentence is a separate sensitivity
control: it answers a slightly different question and must not silently replace this baseline.

Define three distinct quantities:

- `D`: disclosure assignment; `disclosed_probability=null` for `D=0`, `p*` for `D=1`.
- `p_assign`: probability of assignment to the online review opportunity, irrespective of
  disclosure. Main study uses `p_assign=p*=0.5` in both disclosure groups.
- `q_shadow`: independent sampling probability for a deferred research audit. It is not the
  disclosed probability and is not counted as online feedback.

Candidate `D=1` wording: “At the draft boundary, this session has a 50% chance of being selected
for an independent patch review. If selected and the review completes, its result will be
provided before revision.” This refers to selection, not guaranteed successful delivery, and
does not refer to the final hidden grader. Freeze the wording after development. The common
instructions describe draft and revision phases without mentioning review in `D=0`.

A complete four-arm block gives `P(A=1 | D=d, block)=0.5` for a randomly assigned slot. General
numeric doses cannot be paired with an unchanged 50/50 execution schedule while being described
as truthful probabilities. Stage 0 may use `p in {0.1,0.5,0.9}` with matching assignment
probabilities, but must examine **pre-feedback** behavior to avoid mixing dose with delivered
feedback. Alternatively test hypothetical wording explicitly as a wording experiment. Do not
pool the dose pilot with the balanced main factorial.

The enforceable isolation rule is that `A` does not affect actor inputs or execution before the
boundary. Feedback necessarily reveals that a review occurred afterwards. Neither independence
nor any `DisclosurePolicy` can guarantee that the actor never updates its beliefs within a run.

The assigned message is the causal treatment. A post-task question about how likely the model
thought it would be checked is only a manipulation check, not direct measurement of internal
belief. Prefer a separate manipulation-check sample or ask only after the repair is complete so
the question cannot change the primary behavior.
For a prospective expectation check, use a separate sample exposed only to the initial prompt;
a post-task response may already reflect whether feedback arrived and is therefore retrospective.

### Randomization and independence

- Randomize complete task runs, not individual steps in one shared trajectory.
- For stronger within-task precision, run the same task in all four arms using fresh workspaces,
  fresh contexts, reset model memory, and randomized run order. Preserve each task's pairing
  inside repository clusters; four runs of one task are not four independent tasks.
- Block randomization by actor model and task/repository group. Keep each task's four arms paired
  where practical.
- Persist `repository_id=task.repo` separately from task/deduplication `group_id`. Existing
  `data.prepare()` stratifies tasks within repositories; it does not create repository-disjoint
  splits. The study planner must freeze its own repository partition and check all aliases.
- Keep the grader blind to arm and model identity where feasible.
- Freeze task IDs, actor/verifier revisions, prompts, parameters, test harness, retry policy,
  random seeds, exclusions, and analysis before confirmation.
- Retain failed, timed-out, incomplete, invalid-action, and missing-grade runs. Report their
  counts and handling rules.
- Avoid task leakage between pilot and confirmatory analysis. Repository-disjoint confirmation
  is stronger for transfer, but may reduce sample size; decide from the power analysis.

### Measurement plan

| Measure | Role | How to interpret |
|---|---|---|
| Official/independent task resolved result | Primary outcome | Whether the submitted patch satisfies the task's independent grading procedure |
| Verifier call, verdict, feedback delivery | Treatment fidelity / secondary | Separate “called,” “verdict produced,” and “feedback shown” |
| Draft-review verdict / deferred audit | Secondary | Whether the verifier flags a draft patch; not equivalent to task success |
| Tests run/added, tool calls, edit size/scope, retries | Mechanism outcomes | Whether the cue changes the repair process |
| Regressions and test outcomes | Mechanism and quality | Use the task's independent test harness; report its known limitations |
| Actor self-confidence / verbal hedging | Exploratory | Language is not a validated measure of private belief or deception |
| Tokens, verifier calls, wall time, retries | Cost outcomes | Measure actual use; do not treat hidden audits or sampling as free |
| Cue-belief manipulation check | Separate or post-task | Indicates whether the cue changed reported expectation; not proof of cognition |

## 4. What is genuinely unique here?

### Existing concepts that are not new

Audit-sensitive behavior, strategic response to monitoring, verifier feedback, selective
verification, cost-aware verifier allocation, and coding-agent benchmarks all have prior work.
The paper should not claim any of these as new in isolation.

### Potential contribution

The paper can contribute a direct, experimentally identified answer to a missing cross-question:

1. Does awareness of possible evaluation change **coding-agent repair behavior or final repair
   quality before feedback**?
2. What is the separate effect of **actually providing verifier feedback**?
3. Does their interaction change how we estimate the benefit of a verification policy?
4. Does this pattern replicate across model families and a realistic review cue?

The differentiator is not “audit makes models careful.” It is the **same coding task and
independent final grader across four randomized conditions**, so anticipation and feedback can
be estimated separately. The system implication is to test whether verification-yield or
quality/cost evaluations transfer across awareness conditions.

### How to make the novelty defensible

- Cite audit-awareness/game-theory work prominently and define the boundary: different outcome
  (repair success), domain (repository changes), and randomized feedback factor.
- Cite selective-verification and verifier-allocation work as baselines, not as straw targets.
- Demonstrate the policy consequence in numbers. Pick a documented gate, replicate its relevant
  decision rule, and report how call yield, error rate, task success, or cost-quality frontier
  differs by awareness condition.
- Test an implicit/ordinary workflow cue as well as a controlled explicit cue. Explicit-only
  results support an existence/upper-bound claim, not broad deployment generalization.
- Replicate on multiple actor model families and report model-specific effects. The effect may be
  different for reasoning and non-reasoning modes; treat that as a result, not an inconvenience.
- Keep mechanism measures secondary and pre-register them. “More tests” or “smaller diff” alone
  does not establish better repair quality.
- Report null, negative, heterogeneous, and prompt-sensitive outcomes. Do not promise A* status.

## 5. Related papers: concept and relation to VERITAS

The table summarizes the role of each work in the argument. It is a focused map, not a systematic
review. The v2 audit checked the cited arXiv records/full text and indexed OpenReview manuscripts
on 2026-09-28. OpenReview's live forum/attachment endpoints presented a browser challenge; indexed
manuscript headers support the status descriptions below, but do not establish current editorial
decisions. The arXiv entries are cited as preprints unless a publication record is established.
Other benchmark/background references are retained from the existing guide.

| Paper | Main concept / what it contributes | What it means for this paper |
|---|---|---|
| [Deception in Large Language Models: An Audit Game-Theoretic Analysis](https://openreview.net/pdf?id=x8WlNCQL4s) | Insurance-claim audit game; reports stronger explicit-probability responses from reasoning models, and analyzes economic auditing burden. Indexed manuscript is marked under review at ICLR 2026; current decision unverified. | Prior art for both audit-sensitive behavior and auditing economics. Do not claim it has “no cost accounting”; VERITAS measures coding-repair outcomes and inference/tool costs under separately assigned feedback. |
| [AI Alignment via Incentives and Correction, v3](https://arxiv.org/html/2605.01643v3) | Solver–auditor incentive theory **and coding experiments**, including GRPO co-training and adaptive reward design. | Closer prior art than the submitted plan suggests. The proposed distinction is frozen-model, inference-time disclosure × feedback on repository repair, not “theory versus empirical coding.” |
| [Sherlock: Reliable and Efficient Agentic Workflow Execution](https://arxiv.org/html/2511.00330) | Uses counterfactual workflow analysis, verifier selection and speculative execution/rollback. Reports overhead of **up to** 28.9× latency and 53.2× cost for a verifier on one output. | Workflow allocation baseline. These are maxima under its measurements, not universal VERITAS sizing factors. Its allocation study does not establish the proposed disclosure contrast. |
| [Language Model Cascades: Token-Level Uncertainty and Beyond (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/11f5520daf9132775e8604e89f53925a-Abstract-Conference.html) | Studies learned deferral from a cheaper to a stronger language model using uncertainty features to trade off cost and quality. | Shows uncertainty-driven escalation is established. It is a baseline family, not evidence about agent behavioral response to review disclosure. |
| [Anytime Verified Agents](https://openreview.net/attachment?id=JMDCMf7mlF&name=pdf) | Indexed manuscript header states published in TMLR, April 2026. Allocates search/sampling/verification budgets on GSM8K, MATH, HotpotQA and HumanEval. | Rules out a broad novelty pitch of adaptive budgeted verification. The reviewed description is not a repository-repair disclosure factorial; live venue metadata was inaccessible during this audit. |
| [Verify What Matters: Budgeted Verification for Tool-Using Agents under Counterfactual Downstream Harm](https://openreview.net/pdf?id=nv1jzr0FaZ) | Frames tool-agent verification as intervention allocation using local error probability, verifier efficacy, downstream harm, and cost. The accessible manuscript is labeled under review. | Very close to the prior selective-verification direction. It does not, based on the reviewed abstract, answer the `D × A` coding-repair question. Treat as under-review related work, not accepted prior art. |
| [Engineering Reliable Commit Gates for Agentic AI / VP-CONTROL](https://arxiv.org/html/2609.10969) | Verifier/guard/deferral portfolios. Reports 1.9% unsafe execution at a nominal 5% target, with approximate cluster-adjusted calibration and explicit transfer limitations. | Relevant policy inspiration. Its loss is unsafe execution per task, not SWE unresolved rate; its reported result is not a transferable finite-sample safety certificate. |
| [Look Before You Leap: Pre-Action Verification for LLM Agents](https://arxiv.org/abs/2609.11957) | Studies deterministic checks before shell commands or code edits take effect, including silent action failures. | Distinct problem: whether an action is valid/applied correctly, rather than whether the agent anticipates later review. |
| [SIEVE](https://arxiv.org/abs/2512.06716) | Intent Graph checks tool transitions and argument sources; ambiguous actions escalate to semantic review for indirect prompt-injection defense. | Selective integrity verification, with a different task and outcome. Avoid presenting all selective verifiers as repair-correction systems. |
| [ExecCritic](https://arxiv.org/abs/2609.09133) | Separates test construction from repair and trains those roles; feedback utility depends on test quality. | Supports reviewer qualification and independent final grading. A poor reviewer can reduce repair success; a null feedback contrast need not mean awareness dominates. |
| [Conformal Risk Control](https://arxiv.org/abs/2208.02814) | Controls expected monotone loss under its stated assumptions. | Statistical tool, not a VERITAS contribution. CRC and high-probability learn-then-test certification are distinct procedures; name the chosen bound and its assumptions. |
| [Improving Evaluation Realism with Inference-Time Compute and Deployment Scaffolds](https://arxiv.org/abs/2609.02302) | Studies evaluation awareness and realism, including a coding-agent deployment scaffold. | Additional nearby work: awareness in coding environments is not itself an unoccupied research area. Contrast intervention, endpoint and feedback randomization explicitly. |
| [SWE-bench (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html) | Benchmark of real GitHub issue resolution by language models, requiring repository context and executable evaluation. | Establishes the repository-repair task format used by this project. Benchmark quality and contamination need explicit treatment. |
| [SWE-rebench](https://arxiv.org/abs/2505.20411) | Automated pipeline for over 21,000 interactive Python SWE tasks and a stream of fresher tasks intended to mitigate contamination. | Best fit among currently integrated sources for a large coding-agent study, with a manual quality audit and frozen snapshot. Automation does not guarantee every task is sound. |
| [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) and [OpenAI's 2026 reassessment](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) | Initially a 500-task human-screened subset; in 2026 OpenAI reported contamination and test/task issues in its audit and recommended moving away from it for frontier-capability measurement. | Keep it as a historical/comparability or sensitivity set, not the sole primary evidence for this paper. Its initial human screening is useful, but does not remove the later concerns. |

**Defensible gap statement:** the reviewed material does not establish this exact combination
of randomized advance disclosure, randomized feedback, independently graded repository repair,
measured resource use, and a held-out test of gate transfer across disclosure conditions. A
focused review cannot prove absence across all literature. Remove universal claims that every
gate assumes correction is its only value, and do not claim that this experiment refutes another
paper's reported risk result.

## 6. Dataset recommendation and task plan

### Primary recommendation: pinned SWE-ReBench already in this repository

The repository's `configs/datasets.yaml` pins `nebius/SWE-rebench` at a fixed revision and
expects **21,336** tasks. `data/prepared/manifest.json` records that source and its dataset
hash. This is the most practical primary starting point because it is already integrated into
the SWE adapter and provides far more candidate tasks than a 500-item benchmark.

Use a frozen snapshot, not a moving “latest” dataset. Before confirming results, audit a random
stratified sample of selected tasks for issue clarity, environment reproducibility, test quality,
and whether the expected fix is independently judgeable. Exclude only by predeclared rules, report
the audit and exclusions, and preserve the original IDs. SWE-ReBench's scale and freshness help;
its automated construction does not guarantee every task is valid. The repository currently has
an older pinned 21,336-task release; do not silently replace it with SWE-ReBench V2. A V2 switch
requires adapter validation, a new manifest/protocol, and a fresh split.

### Secondary sensitivity set: SWE-bench Verified

The repository pins the 500-task SWE-bench Verified release. Use it as a secondary historical
comparison or a sensitivity analysis with caveats. OpenAI's 2026 reassessment reported material
test/task problems and contamination in its audit, so it should not be the only evidence for a
frontier coding claim. State the exact snapshot and limits.

### Recent benchmark landscape relevant to this study

This is a focused inventory of recent benchmark families discussed in the project review, not
an exhaustive systematic review of every A* paper. “A*” depends on the field and ranking scheme;
the scope here is recent ICSE, FSE, ASE, ICLR, NeurIPS and ICML work plus clearly marked adjacent
resources. A paper may use a benchmark without introducing it. Subsets and variants are not
independent datasets, so their scores must not be pooled as independent replications.

| Benchmark / dataset family | Task and recent paper context | Relation to VERITAS / use decision |
|---|---|---|
| SWE-bench | Real GitHub issue resolution in repository context; ICLR 2024. | Core task family and historical baseline. |
| SWE-bench Lite | Smaller SWE-bench subset used for practical agent evaluation, including Agentless (FSE 2025). | Development or historical comparison; overlaps SWE-bench. |
| SWE-bench Lite-S | Revised Lite subset used in repair work. | Sensitivity only; document exact task IDs and overlap. |
| SWE-bench Verified | Human-screened 500-task subset, widely used in agent evaluations. | Secondary comparability/sensitivity set, not sole evidence; quality and contamination concerns need caveats. |
| SWE-rebench | NeurIPS 2025 Datasets & Benchmarks paper: over 21,000 interactive Python SWE tasks and fresh-task collection for less contamination-prone evaluation. | Preferred main source among integrated datasets; pin snapshot, audit tasks and freeze sample. [Paper](https://proceedings.nips.cc/paper_files/paper/2025/hash/21bec6ace947b1b58967b945c8ac0f10-Abstract-Datasets_and_Benchmarks_Track.html) |
| SWE-rebench V2 | Language-agnostic follow-up task-collection pipeline. | Do not silently replace the pinned source; requires a new adapter/version, manifest and split. |
| SWE-bench Multimodal | Repository issues where images are relevant to task understanding or tests; ICLR 2025. | Later robustness study; visual input changes the task and needs a separate protocol. |
| Rust-SWE-bench | 500 repository issue tasks from 34 Rust repositories; ICSE 2026. | Cross-language generalization after Python qualification; analyze separately by language. [Paper](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/67/Evaluating-and-Improving-Automated-Repository-Level-Rust-Issue-Resolution-with-LLM-ba) |
| USEbench | 1,271 repository-level tasks assembled from multiple sources and task types; ICSE 2026. | Potential generalization suite after provenance and overlap audit; stratify by task type. |
| SWE-bench Pro | More complex/long-horizon repository issue tasks; recent preprint/submission status should be checked at use time. | Optional stress test; verify status, access and protocol before adopting. |
| Multi-SWE-bench | Repository repair tasks across several programming languages. | Optional cross-language set; establish language-specific graders and report strata separately. |
| SWE-bench Live | Continuously updated tasks, including broader languages/platforms. | Later external validation; freeze a dated batch and retain provenance. |
| SWE-Gym | Interactive SWE environments and training data; ICML 2025. | Primarily a training/environment resource, not an independent holdout by default; enforce train/eval separation. |
| RACE-Bench | 528 repository-level feature-addition tasks from 12 repositories, with executable patch checks and structured reasoning; ASE 2026. | Adjacent task type, not issue repair; separate feature-addition study. [Paper](https://conf.researchr.org/details/ase-2026/ase-2026-research-track/130/RACE-Bench-A-Reasoning-Augmented-Benchmark-for-Repository-Level-Code-Agents-on-Featu) |
| Doc2Feat-Bench | Documentation-driven repository feature addition; ASE 2026. | Separate feature-addition study; documentation is an additional input condition. [ASE program](https://conf.researchr.org/track/ase-2026/ase-2026-research-track) |
| RealBench | Repository-level code generation from requirements plus UML design; FSE 2026. | Not bug repair; do not pool success outcomes with SWE issue resolution. [Paper](https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/187/RealBench-A-Repo-Level-Code-Generation-Benchmark-Aligned-with-Real-World-Software-De) |
| RepoReasoner | Repository-level reasoning, including output and call-chain prediction; FSE 2026. | Can study reasoning separately; it does not grade repair success. [Paper](https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/58/RepoReasoner-Evaluating-Repository-Level-Code-Reasoning-Ability-of-Long-Context-Lang) |
| ExplainBench | Accuracy and trustworthiness of agent-generated code/patch explanations; ASE 2026. | Optional explanation-quality study, not a repair benchmark. [Paper](https://conf.researchr.org/details/ase-2026/ase-2026-research-track/65/ExplainBench-Evaluating-Code-Explanations-from-Agents) |
| TDD-Bench Verified | SWE issue reproduction-test generation and selection; used in recent ICSE work. | Relevant to a later test-generation question, not a direct repair-success measure. [ICSE paper](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/309/Heterogeneous-Prompting-and-Execution-Feedback-for-SWE-Issue-Test-Generation-and-Sele) |
| SWE-fficiency | Software performance-optimization tasks; ICML 2026. | Different objective and grading; separate optimization study. [Paper](https://proceedings.mlr.press/v306/ma26l.html) |
| SWE-Lancer | Freelance software-engineering tasks, including tasks with monetary value. | Different task mix and grading; optional external validity, not directly comparable leaderboard evidence. [Overview](https://openai.com/index/swe-lancer/) |

Recent papers also analyze agents on existing datasets without introducing a new benchmark. An
ICSE 2026 process study examines thousands of trajectories and test logs from agents on 500
SWE-bench issues ([paper](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/98/Beyond-Final-Code-A-Process-Oriented-Error-Analysis-of-Software-Development-Agents-i)).
Another ICSE 2026 study finds that test-passing patches can still differ behaviorally from
developer patches ([paper](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/59/Are-Solved-Issues-in-SWE-bench-Really-Solved-Correctly-An-Empirical-Study)).
These motivate trajectory retention and independent patch-quality audits; they do not make raw
scores across different benchmarks comparable.

### Dataset work required for this paper

Do not attempt to run every benchmark family in one paper. Many are overlapping variants, and
others measure feature addition, explanation, test generation, reasoning or optimization rather
than repository repair. A mixed 20-benchmark score table would combine different populations
and research questions. The primary study should test the D × A causal question on repository
issue repair; adjacent task types are follow-up studies.

Before confirmation, complete these dataset tasks:

1. **Choose and pin the primary snapshot.** Prefer the already integrated 21,336-task SWE-rebench
   release. Record source revision, loader version, harness commit, task IDs and hashes.
2. **Audit task validity.** Review a preregistered stratified sample for issue clarity, runnable
   setup, meaningful fail-to-pass and pass-to-pass tests, patchability and independent grading.
   Publish audit counts, exclusion reasons and unresolved cases.
3. **Create fixed, non-overlapping pools.** Separate prompt development, graded power pilot, gate
   calibration and untouched confirmation. Freeze task and repository grouping before tuning;
   deduplicate aliases and benchmark overlap across pools.
4. **Select confirmation size from graded-pilot power.** Simulate task-paired four-arm runs with
   repository clustering, model-by-treatment variation, incomplete runs and planned contrasts.
   Do not use a generic fixed task count or the full 21K set as a sample-size argument.
5. **Use Verified only as secondary sensitivity/comparability evidence.** Record its exact
   version, overlap with the primary tasks and test-quality limitations.
6. **Add a second task family only after repair qualification.** Rust-SWE-bench or a multilingual
   repair set can test generality, but needs validated adapters/graders and language-stratified
   estimates. RACE-Bench, Doc2Feat-Bench, RealBench, RepoReasoner, ExplainBench, TDD-Bench and
   SWE-fficiency require separate research questions.
7. **Preserve provenance for every run.** Record source/task ID, repository/commit, issue and
   base-tree hashes, image digest, harness/test revision, patch hash, grader report, assignment,
   exclusions, retries and failures.

Compare treatment arms within the same benchmark and task/model block. Never compare one VERITAS
arm on one dataset with a published score on another and call it a treatment improvement:
models, scaffolding, budgets, task versions and graders differ. If multiple repair sets are
included, report each separately or use a prespecified stratified model that represents benchmark
and task heterogeneity.

### Do not use these as the primary paper dataset

- `swe_test` is the older original test split and has contamination/task-quality concerns.
- `GSM8K` and `MATH-500` are reasoning datasets. They are useful for generic runtime smoke tests
  or separate analysis, but they do not test repository repair and should not support the main
  paper claim.
- Do not mix math tasks into the SWE success rate.

### Splits and sampling

Make four task pools before looking at confirmatory outcomes:

1. **Development/prompt pool:** cue wording, control variants, runtime debugging. Never report
   these runs as confirmatory results.
2. **Pilot/power pool:** small randomized runs to verify manipulation, estimate variance and
   clustering, check task validity, and determine compute. Do not use these outcomes to claim
   confirmatory significance.
3. **Gate-calibration pool:** held-out repositories for selecting/certifying Stage 6 thresholds;
   reserve before confirmation and never use confirmation labels to fit a gate.
4. **Confirmation pool:** untouched task and preferably repository groups, frozen before the
   final run. Use the same issue/task in each arm only if all runs use isolated clean workspaces
   and a random run order; cluster all results from one task together.

The precise number of tasks must come from a power analysis after the pilot. Do not reuse generic
“N per cell” estimates without accounting for repository/task clustering, paired repeated tasks,
model-by-treatment interactions, failed runs, and multiple planned contrasts. A small pilot may
detect implementation failures but is not automatically powered for a modest task-success
difference.

**Split warning:** `configs/comparison.yaml` currently sets `split: null`, includes all prepared
sources by default, and selects five tasks per source. The prepared manifest forces official
holdouts into `test`. That default can consume held-out tasks and is not a confirmatory paper
plan. Create an experiment-specific, group-aware development/pilot/confirmation manifest before
prompt iteration; never tune on final confirmation tasks.

## 7. How many LLMs should be tested?

“How many LLMs?” can mean model families or model roles. They are different counts.

| Role | Minimum credible main study | Stronger study | Notes |
|---|---:|---:|---|
| Coding actor families | 2 | 3 | Each actor is run in all four arms. Do not assign a different model to each arm. Two families allow a basic replication check; three provide better evidence of generality. |
| Independent verifier families | 1 fixed verifier | 2 in a verifier-robustness extension | Keep the same verifier and exact version across the four arms for the primary factorial comparison. Prefer a verifier distinct from the actor family to reduce shared failure modes. |
| Critic | 0 required | 1 optional secondary component | The critic is not needed to identify the `D × A` effects. Do not add it to the main protocol unless a separate hypothesis requires it. |

Thus, the practical minimum is **two actor models plus one fixed independent verifier model** (three
distinct model identities if the verifier is separate). A stronger paper tests **three actor
families**, then checks a second verifier only as a prespecified robustness extension. Compute
and task coverage matter more than a long list of underpowered models.

Run every actor model across all four arms on matched task blocks, using fresh workspaces and
reset conversations. Freeze model name, provider revision/checkpoint hash, reasoning mode,
temperature, top-p if applicable, token cap, system prompt, tool schema, and retry policy.
For reasoning-capable systems, record whether reasoning mode is enabled; do not mix modes without
labeling them as separate settings.

**Current configuration warning:** `configs/experiment.yaml` sets the actor, critic, and verifier
to `qwen2.5-coder:7b`. This is acceptable for plumbing experiments, but it is not an independent
actor/verifier design and it is only one actor family. The awareness experiment should explicitly
configure and record roles rather than inherit this as evidence of cross-model robustness.

### Feasible model selection

Use the currently configured `qwen2.5-coder:7b` for initial plumbing **if the endpoint is available**.
Configuration alone does not establish availability or sufficient repair capability. Select the
study's two actor families after development runs measure valid tool output, repair success,
latency, memory and total cost under this scaffold. A model that cannot complete enough tasks
to measure a treatment difference should not enter confirmation merely because it fits locally.

Keep serving location interchangeable: local inference and a compatible hosted endpoint use
the same public task, tools and phase protocol. Fix limits within each actor across all arms;
if capacities require different limits between actors, estimate and report within-actor effects
first. A hosted model that silently changes version cannot support a claimed immutable model
identity; record the limitation and execution dates or choose a pinnable checkpoint.

Qualify the fixed reviewer on development-only **draft patches**, using human findings and
independent test evidence where available. Measure false alarms, actionable findings, malformed
responses, latency and cost; a failed final test alone does not label every reviewer finding.
Use a separate model family when feasible, while recognizing that a different family does not
guarantee statistically independent errors. A second verifier belongs in a later robustness study.

Specific large-model/API candidates are an execution decision after this capacity check, rather
than an architectural dependency. Freeze the chosen identities before the pilot whose variance
and cost estimates will determine the confirmatory plan.

## 8. Implementation architecture

### 8.1 One application with explicit boundaries

Build a **modular Python application** around the existing tool executor and model clients.
Start with one coordinator and one active trial. Use SQLite for job state and structured records,
and ordinary files for prompts, patches, reports, and snapshots. Docker contains task execution;
the SWE harness runs as a separate process after the patch is frozen. No service deployment is
needed for the first study.

This choice fits the repository and the initial workload: a finite experiment with slow model
and test calls, few database writers, and a need to inspect every result. SQLite's documentation
supports local analysis and low writer concurrency; keep each database on local storage rather
than a shared network filesystem. [SQLite usage guidance](https://sqlite.org/whentouse.html)

```mermaid
flowchart TD
  P[Freeze protocol, tasks, models, budgets and harness] --> Q[Plan all four arms and randomize run order]
  Q --> J[Coordinator claims one trial]
  J --> W[Fresh base workspace and actor session]
  W --> D[Draft phase with assigned cue or control]
  D --> S[Save draft patch, session and public review packet]
  S --> A{Assigned feedback A}
  A -->|1| V[One fixed reviewer call]
  V --> F[Bounded PASS, findings or unavailable message]
  A -->|0| N[Fixed neutral continuation]
  F --> R[Revision phase with equal actor allowance]
  N --> R
  R --> Z[Freeze final patch and end actor session]
  Z --> G[Independent SWE grader]
  Z --> H[Deferred sampled draft audit]
  Q -.-> L[Study ledger and private artifacts]
  S -.-> L
  V -.-> L
  G --> L
  H --> L
  L --> E[Validate joins, estimate contrasts and report cost]
```

`D` and `A` are assigned before inference. The `A` branch is first consulted at the review
boundary. The grader and deferred auditor have no path back into an actor session.

### 8.2 Exact lifecycle of one trial

| Stage | Required behavior |
|---|---|
| Prepare | Resolve frozen task/model identities; create a fresh base workspace; verify image and tree hashes. Give the actor only the public task and its cue/control. |
| Draft | Run ordinary read/edit/test tools without critic or action-level review. The first `final_answer`, draft step limit, or draft token/time limit closes this phase. |
| Freeze draft | Save the actual workspace patch, transcript, counters, termination reason and public review packet. An empty draft is valid input to review; it is not a reason to drop the trial. |
| Review boundary | For `A=1`, call the fixed reviewer once. For `A=0`, construct the neutral message without calling a reviewer. Persist the message and its hash before continuation. |
| Revise | Continue the same trial's workspace and actor history. Every arm receives the same additional allowance and can edit/test or immediately submit. Never transfer unused draft allowance into revision. |
| Freeze final | Save the workspace patch at submission or phase limit. On an actor crash, use the last durably completed workspace when available and record the failure; do not choose a patch using grader results. |
| Grade | Submit the frozen patch with an opaque identity to the pinned SWE harness. Save raw reports and an explicit resolved/unresolved/ungraded status. |
| Audit/report | Run sampled draft audits after the actor batch ends; join records by immutable IDs; report every assigned trial. |

The equal revision opportunity matters: comparing a reviewed two-stage agent with a baseline
that had only one chance would confound feedback with additional actor effort. Equal allowance
does not mean equal actual token use; use is an outcome. Before the boundary, prompts and tools
must be identical across `A` for a fixed `D`, task, actor and random seed.

### 8.3 Ownership and interfaces

The implementation uses the following modules under `src/veritas/`. Core records are typed;
coordinator entry points accept explicit study paths and injectable IO services for testing.

| Module | Owns | Interface / output |
|---|---|---|
| `awareness.py` | Protocol validation, repository pools, four-arm planning, immutable IDs, randomized schedule | `plan_study(protocol, tasks, splits)`, `create_study(config, output)`, `read_study(root)` |
| `awareness_runtime.py` | Job lifecycle, phase limits, continuation, feedback, deferred audits | `run_trial(root, spec, task, job, db, services)`, `run_study(root)`, `audit_study(root)` |
| `patch_review.py` | Public packet, one reviewer call, verdict parsing and bounded rendering | `make_packet(...)`, `review_patch(packet, patch_hash, model, limits)` |
| `awareness_store.py` | SQLite transitions, attempt history, immutable artifacts, request reservations | `StudyStore.claim()`, `append_event()`, `finish()`, `verify()` |
| `awareness_grading.py` | Pinned package fingerprint, opaque predictions, raw SWE report evidence | `harness_fingerprint()`, `grade_patch()`, `parse_grade()`; coordinator: `grade_study(root)` |
| `awareness_analysis.py` | Completeness, means, paired contrasts, intervals, costs, cue comprehension | `study_rows(root)`, `factorial_summary(rows)`, `report_study(root)`, `check_manipulation(root)` |
| `awareness_measurements.py` | Versioned draft/revision patch measurements and optional post-run elicitation | `measure_study(root)` and frozen feature extractors |
| `awareness_costs.py` | Token and elapsed-time summaries by trial, phase and role | Cost summaries; no inferred dollar/compute costs without provider accounting |
| `awareness_qualification.py`, `model_provenance.py` | Preflight declared model, image, grader and implementation identities | `qualify_protocol(config, output)`; preflight is not scientific validation |
| `awareness_power.py` | Graded binary-outcome cluster simulation with MDE/missingness scenarios | `pilot_power(root, ...)` |
| `awareness_gate.py` | Development scorer, reserved calibration, locked confirmation and transfer | `fit_gate()`, `calibrate_gate()`, `report_gate()` |
| `awareness_cli.py` | CLI arguments and dispatch | `veritas awareness ...` |

`runtime.py` now provides the `AgentSession` / `run_phase()` seam used by the study runner. The
session holds history, global step index, counters and phase state. `run_task()` remains the
existing single-phase wrapper. Both phases share action contracts, executor, prompt renderer and
event writer. Do not call `collect()` twice: it creates a new workspace and loses continuation
state.

Keep treatment authority in the coordinator. The draft runner receives the cue text and phase
limits, **not `A` or the arm ID**. The revision runner receives only the rendered boundary
message. The reviewer receives a public patch packet; the grader receives the patch and private
benchmark record. This prevents accidental serialization of the full assignment into prompts.

### 8.4 Prompt and reviewer contract

Assemble actor context through one renderer for standard and compact modes. Preserve task,
assigned cue/control, current phase and boundary message separately from trimmable history.
Include the cue once per request and retain the review/neutral message throughout revision.
Tell all actors about the draft/revision workflow in the same common instructions without
disclosing `A`; otherwise an unexpected second phase becomes another treatment difference.
Hash the exact system and user messages and tool schema. Store inspectable, redacted copies;
keep credentials out of prompts and record redaction metadata if bytes differ.

Use the numeric selection-probability wording from section 3 at one fixed location in the task
context. The primary control adds no review sentence; a neutral-text sensitivity control is
separately labeled. Freeze the actual strings and tokenizer counts after development. The
control must not assert that review is impossible. Additional cue input tokens are measured
deployment cost, even though prompt construction itself needs no model call.

The reviewer packet contains the issue text, base identity, draft diff, deterministically chosen
changed-file context, and public actor test observations. Fix ordering and input/output caps;
record omitted paths and truncation. It excludes cue, arm, actor identity, private gold patch,
hidden test patch, private grading labels, and the actor's full conversation. Code/comments and
test output are untrusted evidence. The reviewer cannot edit the workspace or run a tool loop.
Begin with an LLM review of this packet; adding probes or reviewer tools changes the protocol.

Return a typed record with `verdict`, bounded findings (`path`, optional line, explanation),
packet hash, prompt/model identity, usage, duration and error status. PASS means no issue found
by this reviewer, not independently established correctness. Invalid structured output becomes
ERROR; no repair-model call or repeated review in v2. Render both PASS and FAIL for `A=1`.
Every arm also gets the same continuation instruction: it may keep or revise the draft within
the remaining allowance. No adaptive “try again” loop depends on review severity.

### 8.5 Assignment, identity and persistence

For each `(task, actor, repetition)` block, create four fresh execution slots and randomly
permute `00, 10, 01, 11` onto them. Record the seed, permutation and order. Each slot has marginal
arm probability `1/4`; assignments within a complete block are dependent. Record this complete
block design explicitly rather than claiming four independent Bernoulli draws. Randomize block
order across repositories and actors; record dispatch times and any scheduling deviations.

Separate the planner seed from model sampling settings. The current model client does not send
a sampling seed, so do not claim bitwise reproducibility. Freeze supported settings and record
whether seeds, immutable model revisions and token accounting are actually available.

| Record | Minimum contents / constraint |
|---|---|
| `Protocol` | Schema/version, task/split hashes, model identities, prompt/tool hashes, phase/reviewer limits, `disclosure_probability`, `assignment_probability`, `shadow_sample_probability`, harness identity, retry and analysis rules; content hash is study ID. |
| `Assignment` | Study/block/trial IDs, task/deduplication/repository IDs, actor, repetition, `disclosure_assigned`, nullable `disclosed_probability`, `actual_assignment`, slot/order, marginal propensity; unique `(study, task, actor, repetition, arm)`. |
| `Attempt` | Trial ID, attempt number, state, timestamps, failure category, selected-attempt rule; failed attempts remain present. |
| `ReviewRecord` | Draft/packet hash, scheduled/called/valid flags, verdict, payload hash, delivery state (`yes/no/unknown`) and actor request ID, cost/usage completeness. |
| `TrialOutcome` | Assignment and attempt IDs, draft/final patch hashes, runtime status, grader status, nullable resolved flag, prompt/event/artifact references, usage by role and phase. |
| `ShadowAudit` | Trial/draft/packet hashes, selection probability/seed, audit status, nullable verdict, findings, reviewer identity, measurement usage; no actor-delivery route. |
| `BehavioralMetrics` | Trial/phase, extractor version, diff and transcript hashes, added/deleted lines, files touched, tests added/run, language counts and explicit missingness. |

Keep the requested `actual_assignment` name as the immutable assigned `A`; separately record
`verifier_attempted`, `verifier_completed`, and `feedback_delivered`. None is a substitute for
the others. `disclosed_probability` must be finite and in `[0,1]` when present; the main-study
validator requires `D=0 -> null`, `D=1 -> 0.5`, and assignment probability `0.5`. Legacy traces
have unknown assignment, never default `D=0,A=0`. The full private assignment must not be added
to `Task`, whose public prompt is shared across arms.

A small `DisclosurePolicy` value object in `awareness.py` may own the template and validation;
the planner owns randomization. Neither is a new `Controller` policy. Store per-trial treatment
once, and add nullable `trial_id`, `attempt_id` and `phase` to a versioned `StepRecord` when the
runtime is implemented. Do not overload its action-level `verification` with a patch verdict.
If an exported table needs `shadow_verifier_verdict`, derive it from `ShadowAudit` using the
draft hash; missing audit and ERROR must remain distinguishable. Event payload validation,
round-trip serialization and export compatibility still need checks even though the underlying
SQLite hash-chain storage can remain mechanically unchanged.

Use `study.sqlite` for assignments, attempts, phase/review events and outcomes. Existing
`EventStore` remains the writer for action `StepRecord`s in each attempt's `events.sqlite`.
The existing store accepts only `StepRecord`; study records need their own validated tables.
Extend action records only with versioned trial/phase linkage, not duplicated final grades.
One coordinator writes scheduling state; transactions enforce unique claims. Append transition
events and update the current-state projection in the same transaction.

```text
runs/awareness/<study_hash>/
  protocol.json              frozen settings and analysis rules
  assignments.jsonl          complete randomized plan
  study.sqlite               coordinator state and typed study records
  trials/<trial_id>/attempt-001/
    events.sqlite            existing action ledger
    draft.patch, final.patch
    draft-session.json       session metadata, tied to a workspace snapshot hash
    review.json              private reviewer record
    outcome.json
    grading/                 opaque prediction ID and raw harness outputs
  audit/                     deferred private draft reviews
  report/                    validated exports, estimates and figures
```

All metadata and grading files live outside the actor workspace. Cache immutable base images
and base trees by digest; create a fresh writable workspace for every arm. Never cache actor
answers across arms or fork a single observed draft into multiple primary arms. Keep evidence
files append-only or write once with hashes; local hashes detect changes but are not an external
proof against an operator replacing the entire study.

### 8.6 Failures, resume and independent grading

Persist transitions `planned -> running -> draft_frozen -> boundary_recorded -> final_frozen ->
graded`, with explicit failed/interrupted/ungraded outcomes. Write artifacts atomically before
committing references. A process crash can leave orphan files; recovery validates hashes and
never treats a partial write as a completed result.

Resume v2 at **trial or grading boundaries**. Completed trials are never rerun. A frozen final
patch can be regraded under a prespecified infrastructure retry rule without actor inference.
An interrupted actor attempt is retained and terminal by default; a development rerun gets a
new attempt ID. Confirmation must freeze an arm-independent retry/selection rule in advance.
Do not retry unsuccessful patches or select the best of multiple attempts. Mid-tool recovery
and exactly-once provider billing are out of scope; a lost response has unknown usage until
reconciled, not zero cost.

Grade with the source-compatible harness. SWE-ReBench uses the separate environment and pinned
fork in `scripts/setup_rebench.sh`; do not replace it with an arbitrary installed `swebench`.
Retain dataset/harness commit, image digest, platform, prediction hash and report hash. Each
grading attempt gets a unique opaque ID incorporating trial, patch, harness and grading attempt;
the coordinator keeps the arm mapping private. The upstream harness documents result caching
by run and instance, so a changed patch must never reuse a grading identity.
[SWE-bench evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)

Validate report parsing against the **pinned** harness. `comparison.grade_swe()` assumes a
particular report filename/schema and returns only a Boolean/source; factor out an adapter
that preserves full status and evidence rather than calling it unchanged. A process exit code
of zero does not establish repair success. Run hidden tests only in the grading environment.
Audit task images for gold artifacts or hidden test files before the study; removing `.git`
alone is not a complete leakage check.

Keep scientific and operational failure distinct. Empty/invalid patches count as unresolved by
the frozen submission rule. Provider, workspace and harness failures retain explicit status;
they must not disappear from denominators or silently turn into observed test failures. Report
completion and missingness by arm, a conservative end-to-end success measure, and uncertainty
or bounds for unknown repair outcomes as specified in section 15.

### 8.7 Resource envelope and feasible rollout

The default is local orchestration with backend-neutral model endpoints. Model API use, cloud
capacity and actual run spending are execution choices, not prerequisites to this design. The
development host reports `arm64`; qualify chosen benchmark images on that platform before
planning a local batch. Use a compatible Linux worker if images require it, keeping the same
plan and artifacts. The upstream Docker guide documents platform setup; compatibility with the
pinned SWE-ReBench fork must still be tested locally.
[SWE-bench Docker guide](https://www.swebench.com/SWE-bench/guides/docker_setup/)

Provisional **smoke-test limits**, to replace after development and freeze before the pilot:

| Resource | Starting setting |
|---|---|
| Concurrency | One active actor trial; grade and audit in separate batches to avoid local contention. |
| Actor phases | 24 draft tool/model steps plus 8 revision steps; same per-model limits in all arms. |
| Actor completion allowance | 24,000 draft plus 8,000 revision tokens, at most 2,048 per call; clamp each call to remaining allowance. |
| Actor context/time | Model-supported input cap with deterministic history trimming; 15 draft plus 5 revision active minutes. Review wait is accounted separately. |
| Review | One attempt, input within verifier context capacity, at most 768 output tokens, 180-second deadline. |
| Sandbox | Existing 2 CPU / 4 GiB / 60-second action settings as a smoke starting point; qualify tasks that need more before freezing selection. |
| Deferred audits | Seeded 20% sample of `A=0` drafts, balanced in expectation across cue conditions; record inclusion probability. |

These are proposed configuration values, not measured capacity or production defaults. The
current `max_online_tokens` mixes actor and verifier use and checks only before each step. Add
separate actor phase accounting and deadlines; charge the reviewer outside the actor allowance.
Include input, output, reasoning/cache usage where exposed, provider request costs, tools,
grading, retries and audits in reports. If usage is unavailable, mark it unknown. Maintain an
independent study spending cap, reserve estimated worst-case next-call cost, and mark any
cap-stopped study incomplete; resource stopping must not depend on favorable results.

Maintain separate cost views, with units kept explicit:

```text
C_deploy  = actor draft/revision + online review + online tools/orchestration
C_measure = shadow audits + independent grading + manipulation questions + offline scoring
C_total   = C_deploy + C_measure + separately allocated study setup costs
```

Report tokens by role, calls, elapsed/active seconds, CPU/GPU time where measured, and money only
when pricing or amortization is specified. Costs are not interchangeable scalar quantities;
any `Y - lambda*C` utility requires a frozen unit and lambda. Report mean and tail costs per
cell, and paired incremental costs for each contrast. A prompt's extra input and every revision
call count in `C_deploy`. Audit-only usage is measurement overhead, never a free bonus.

Do not adopt fixed VRAM estimates as capacity guarantees. Raw 4-bit weights alone require roughly
`parameters * 0.5 bytes`; serving adds quantization metadata, KV cache, runtime memory and batch
headroom. The current Transformers adapter uses `torch_dtype="auto"` without an explicit int4
configuration, and separate `LocalModel` objects can load separate copies. Weight sharing is a
server/configuration property that must be measured. A base model may also lack the chat template
and reliable JSON/tool behavior this adapter expects; it is an optional robustness study, not
a requirement or proof that an effect is unrelated to RLHF.

Docker may be material here: `DockerSandbox.execute()` creates a disposable container and copies
the workspace for each action. Image preparation, repository copies, checkpoint hashing and
grading tests can dominate some tasks. Measure model, tool, copy/setup and grader timings before
deciding which resource limits concurrency. For each split, estimate serial time as the sum of
measured per-cell online trial times (including review) plus grading/audit/setup times. Divide
only genuinely parallel portions by measured throughput. Repeat for every actor and sum all stages.

For `N` tasks, `M` actors, and `R` repetitions:

```text
Actor trials          = 4 * N * M * R
Online reviewer calls <= 2 * N * M * R
Expected audit calls  = q * 2 * N * M * R   (q = audit fraction)
Final grade jobs      <= 4 * N * M * R     (before infrastructure retries)
```

For example, a 20-task, two-actor, one-repetition pilot has 160 actor trials, at most 80 online
reviews and about 16 deferred reviews at `q=0.2`. This is an operations example, not a powered
sample size. At an assumed 10 minutes per actor trial, actor execution alone is about 26.7 serial
hours; grading/review/setup add time. Estimate money and the full duration from measured pilot
usage, throughput and current endpoint prices before confirmation.

Start with fake-model tests, then four development tasks × one actor × four arms (16 smoke
trials). Proceed to a pilot across two actor families only after patch grading, continuation and
delivery isolation work. Determine confirmatory task count from power and affordability. Scale
by partitioning the frozen trial list across independent workers with local ledgers and merging
validated outputs; central services are justified only if this becomes an actual bottleneck.

### 8.8 What is deferred and why

Keep the main study fixed: two actor families, one verifier, one review, one explicit cue,
independent grading. Critic fitting, dependency graphs, adaptive review allocation, multi-reviewer
debate, actor fine-tuning, dashboards and distributed queues are outside the first implementation.
Each adds another learned component, treatment or operating burden without being required to
estimate `Y10-Y00` and the feedback contrasts.

Stage 6 first evaluates a frozen **post-repair admission gate** as specified in section 15. This
can operate on frozen patches without changing actor behavior. An adaptive review-selection
policy at the draft boundary is a separate online extension: offline reviews alone cannot
measure final repair success under a changed feedback policy.

## 9. Runtime architectures

### 9.1 Existing action-verification workflow

```mermaid
flowchart LR
  CLI[veritas collect / compare] --> COL[collect: models, tasks, sandbox, store]
  COL --> LOOP[run_task loop]
  LOOP --> CTX[Build task + recent history context]
  CTX --> ACT[LocalModel.propose]
  ACT --> CONTRACT[Parse proposal and validate contract]
  CONTRACT --> CRITIC[Optional critic score]
  CRITIC --> CAL[Apply calibration artifact if configured]
  CAL --> CTRL[Controller decides under policy/budget]
  CTRL -->|selected| VER[Verifier.verify before execution]
  CTRL -->|not selected + audit_all| AUDIT[Verifier runs hidden; audit_only]
  CTRL -->|not selected| EXEC[Execute action]
  VER -->|FAIL/REVIEW| FEEDBACK[Record feedback and replan]
  VER -->|PASS| EXEC
  AUDIT --> EXEC
  FEEDBACK --> STORE[EventStore.append StepRecord]
  EXEC --> STORE
  STORE --> LOOP
  LOOP --> GRADE[Task summary / final patch]
  GRADE --> SWEGRADE[comparison.grade_swe and SWE harness]
```

The existing `collect` workflow implements action-level verification and policy comparison. It
remains separate from the factorial study; a `collect` run is not evidence for the paper.

### 9.2 Awareness study workflow

```mermaid
flowchart TD
  PLAN[Freeze protocol, split and blocked assignments] --> RUN[Sequential coordinator]
  RUN --> INIT[Fresh base workspace and actor session]
  INIT --> DRAFT[Draft phase with D cue or control]
  DRAFT --> SNAP[Freeze draft, prompt and public review packet]
  SNAP --> BRANCH{Assigned A}
  BRANCH -->|A=1| REVIEW[One bounded patch review]
  BRANCH -->|A=0| NEUTRAL[Fixed neutral continuation]
  REVIEW --> CONT[Same revision allowance]
  NEUTRAL --> CONT
  CONT --> FINAL[Freeze final patch and end actor session]
  FINAL --> GRADE[Independent pinned SWE grading]
  SNAP -. deferred, sampled .-> AUDIT[Shadow audit after actor batch]
  PLAN -.-> LEDGER[Study ledger and immutable artifacts]
  FINAL --> LEDGER
  GRADE --> LEDGER
  AUDIT --> LEDGER
  LEDGER --> REPORT[Factorial analysis and gate transfer]
```

The study runner assigns `D` and `A` before execution. `A` is not passed into the draft
phase; only its boundary message reaches revision. Shadow audits run after actor trials finish
and have no delivery path to an actor.

## 10. Current project condition

### What exists now

- Python package and CLI at `src/veritas/`, installed as the `veritas` command by
  `pyproject.toml`.
- Agent, optional critic, verifier, budget controller, sandbox execution, event store, calibration,
  baseline comparison, SWE task preparation/evaluation helpers, and a substantial test suite.
- Dataset definitions in `configs/datasets.yaml`; pinned prepared task manifests under
  `data/prepared/` and `data/prepared-conservative/`.
- The current prepared manifest records **50,897 unique tasks**, including a pinned SWE-ReBench
  snapshot (21,336 tasks), SWE-bench Verified (500), original SWE-bench splits, GSM8K, and
  MATH-500. The presence of tasks does not mean the paper's sample has been selected or audited.
- `configs/collection.yaml` is designed for uncensored collection: `policy: never`,
  `audit_all: true`, and uncalibrated collection enabled. It can provide hidden verifier traces
  for existing data workflows, but there is no awareness cue or randomized feedback delivery
  factor.
- `configs/comparison.yaml` defines a paired policy comparison. It has `limit: 5` per source by
  default and `split: null`, which includes held-out sources. Do not use that default as a
  confirmatory paper plan; it is broad exploratory configuration and can consume held-out tasks.
- The dependency cohort/graph/pilot code and dependency artifacts exist. That is older, separate
  work and not the new awareness experiment.

### V2 implementation and remaining validation

The awareness CLI now connects the frozen planner, durable single-coordinator ledger, isolated
two-phase actor runtime, bounded PASS/FAIL/error review, deferred audits, independent SWE
grading, factorial reporting, binary pilot-power simulation, and frozen static gate transfer.
Legacy action records retain unknown treatment unless explicitly linked by schema version 2.
Prompt copies, request hashes, base identities, patches, outcomes, and grading evidence are
recorded separately from the actor workspace. Interrupted actor attempts use the last committed
patch snapshot and are never silently rerun. Grade retries retain each prior attempt.

The focused `tests/test_awareness_*.py` suite covers treatment, persistence, measurement,
grading, analysis and gate invariants using local doubles, with no Docker or model dependencies.
**Those tests have not been run in this implementation change.** Runtime,
model, image, grader, and performance qualification still need execution. No implicit-cue
experiment, multi-family replication, powered confirmation, or scientific result is claimed.

Current explicit limits: input caps are Unicode-character caps; provider sampling seeds are not
sent; endpoint model revisions are declared configuration, not verified server attestations;
actor retries are disabled; money/CPU/GPU cost is not inferred from token counts. Language
metrics use final-answer prose, and defensive-test intent/confidence remain explicitly missing
without a separately validated extractor or elicitation protocol. Power is pilot-model dependent.
Fixed repository cohorts yield descriptive gate evidence; population certification additionally
requires an explicitly declared independent-repository sampling design.

## 11. Implementation map and remaining work

The core awareness architecture is present in the working tree. The map below identifies the
implemented ownership boundaries; it is not a list of modules still to create. Remaining work
is execution qualification, empirical study design, and any fixes revealed by the unrun focused
tests and runtime smoke trials.

Implement the five awareness/review modules described in section 8.3. Integrate through a small
session seam in the existing runtime. Keep the dependency pilot as a separate workflow.

| Goal | Change location | Engineering instruction |
|---|---|---|
| Define protocol and arms | `awareness.py`; `configs/awareness-pilot.example.yaml` | Protocol validation, exact task IDs, four arms, cue/control, phase/reviewer budgets, model identities, audit fraction, retries, endpoint and analysis rules. |
| Plan and randomize runs | `awareness.plan_study()` | Randomly permute four arms onto fresh slots in each task/model/repetition block; save assignments and schedule before inference. |
| Continue draft into revision | `runtime.AgentSession` / `run_phase()` | Preserve history/workspace within a trial, use global step IDs, return structured phase termination; preserve existing single-phase behavior. |
| Insert cue/control | Shared renderer in `context.py`, called by the active loop | Handle compact and ordinary prompts together; keep cue, phase and boundary message outside history trimming. `build_context()` is currently unused. |
| Control actual feedback | New `awareness_runtime.py` and `patch_review.py` | One review boundary, equal revision allowance, PASS/FAIL/error rendering, no pre-boundary `A` access and no reviewer action rejection. |
| Collect hidden audits | Deferred `patch_review.py` jobs over frozen draft packets | Select with a frozen seed; run after actor batch completion. Leave existing `audit_all` off in awareness runs. |
| Record assignment and outcomes | New `awareness_store.py`; small versioned `StepRecord` linkage extension | Keep assignments/reviews/outcomes in study tables and action traces in existing `EventStore`; enforce unique joins and retain all failures. |
| Configure model/protocol | `config.py`, `models.py`, `provenance.py` plus awareness protocol | Preserve model revisions and supported inference options; cap requests by remaining phase allowance; do not claim unsupported seed or usage fields. |
| Grade repository repair | Extract a grader adapter from `comparison.grade_swe()` / `swe.py` | Unique grading identity, full status/report evidence and patch hash join, validated against the pinned source-compatible harness. |
| Estimate effects | New `awareness_analysis.py` | Validate complete assignment ledger; compute paired contrasts, repository-aware uncertainty, missingness bounds and measured costs. |
| Evaluate gate transfer | Small Stage 6 adapter beside `awareness_analysis.py` | Fit a score on development, freeze candidate thresholds, calibrate on reserved repositories and evaluate admission risk/coverage on confirmation. Do not retrofit temperature scaling into a claimed CRC implementation. |
| Add command-line workflow | `cli.parser()` and `cli.dispatch()` | Add plan/run/resume/grade/report; pilot is a protocol/split choice. Existing `collect`/`compare` remain existing workflows. |
| Focused tests | `tests/test_awareness_*.py` | Tests use fake model/verifier/sandbox objects. Execute and resolve failures before model inference. |

Still outstanding before confirmation: run the focused suite; qualify selected provider endpoints,
container images and the pinned grader; run a bounded local smoke study; complete the independently
graded pilot and freeze its power-derived sample size; finalize audited task/repository splits;
then preregister and execute confirmation. None of these steps is represented by code presence
alone.

### Prompt insertion detail

The active loop does not call `build_context()`. In `run_task()`, the non-compact branch creates
JSON with `user_task` and `recent_history`; compact mode calls `compact_context(task, history,
...)`. Extract the common active prompt assembly so `D=1` receives the cue and `D=0` receives the
common undisclosed prompt in both modes. Then call `policy.propose()` with that rendered context.

`LocalModel.propose()` selects `POLICY_SYSTEM` or `POLICY_COMPACT_SYSTEM` as the system message;
it receives the context as the user message. For the first study, keep the actor system prompt
fixed and put the assigned cue into the context helper. Hash/log the exact rendered prompt but
sanitize secrets. Cue wording, placement, or model system prompt changes define a new protocol
version.

### Required runtime changes before inference

The awareness phase executor starts from the existing baseline settings: `policy: never`,
`score_critic: false`, `audit_all: false`, `allow_uncalibrated: true`, with no calibration artifact
or dependency observer. The explicit uncalibrated setting disables an irrelevant calibration
requirement; it makes no statistical claim. Do not encode `A=1` as `policy: always`.

Four changes are mandatory: return and continue session state; intercept draft `final_answer`
as a phase boundary; preserve treatment/boundary text during compression; enforce separate phase
allowances before model calls. The graph runtime's final-review path currently allows only a
revised `final_answer`, so it cannot perform patch revision using edit/test tools. It is not a
substitute for this session seam. Add the patch-review and grader adapters after that seam works.

## 12. Current file map: what each important file does

### Agent runtime and model calls

| File / functions | What the code currently does | Importance to this paper |
|---|---|---|
| `src/veritas/cli.py`: `parser()`, `dispatch()`, `main()`, `doctor()` | Defines the installed `veritas` subcommands, maps arguments to modules, and checks config/services. | Add awareness planning/running/reporting commands here. `doctor` checks setup; it does not establish experimental readiness. |
| `src/veritas/runtime.py`: `build_context()`, `run_task()`, `collect()` | `collect()` loads tasks, model clients, sandbox, verifier and store. `run_task()` loops over proposals, validation, optional critic, controller, verifier, execution and records. `build_context()` is unused by the active loop. | Main runtime integration point for cue, `D/A` arms, actual feedback, and task-level outcome links. |
| `src/veritas/models.py`: `LocalModel.complete()`, `propose()`, `score()`, `verify()`; parsers | Calls openai-compatible, Ollama, or local Transformers backend; `propose` gets actor output, `score` requests critic probability, `verify` requests verifier verdict. | Actor prompt and model behavior boundary. Freeze prompts/settings. |
| `src/veritas/controller.py`: `Risk`, `Budget`, `Controller.score()`, `decide()`, `reserve()` | Calculates current risk-value score, decides whether to verify, and enforces fixed verifier credits for existing policies. | Baselines for the later gate-policy implication. It does not assign experimental awareness or factorial feedback. |
| `src/veritas/verifier.py`: `Verifier.verify()` | Sends action/context to configured verifier and can probe candidate actions. | Preserve existing action verification. The new patch reviewer reuses model transport/usage, with its own packet and prompt. |
| `src/veritas/graph_verifier.py`: `GraphVerifier` methods | Runs prerequisite/graph-ordered evidence and semantic review. | Optional alternate policy; exclude from primary causal study unless it is the chosen verifier system. |
| `src/veritas/context.py`: `excerpt()`, `compact_entry()`, `compact_context()` | Condenses long agent history. | Ensure cue treatment is present exactly once in compact and ordinary prompt construction. |

### Data contracts, storage, and labels

| File / functions | Current job | Why it matters |
|---|---|---|
| `src/veritas/schema.py`: `Task`, `Usage`, `Verification`, `StepRecord` | Typed task, token/latency, verifier outcome, and event records. Task private fields are explicitly not passed to models. | Add trial/phase linkage; keep assignment, review and task outcome contracts in the awareness modules. Keep gold answers private. |
| `src/veritas/store.py`: `EventStore.append()`, `records()`, `export_ledger()`, `verify_export()` | Stores validated events and exports/verifies ledgers. | Ensure every assigned run is represented, including incomplete attempts; export arm metadata and outcome linkage. |
| `src/veritas/labels.py`: `grade_answer()`, `annotation_queue()`, `annotate_math_queue()`, `apply_annotations()` | Handles exact/numeric answers and annotations. | Current math grading is not an SWE patch grader. Use task-specific independent SWE evaluation for the paper. |
| `src/veritas/swe.py`: `image_map()`, `pull_images()`, `build_images()`, `evaluation_command()`, `evaluate_swe()` | Prepares Docker images and invokes official SWE evaluation. | Source for primary repo task grading, after validating runner configuration and harness. |
| `src/veritas/sanitize.py`: `redact()`, `sanitize()` | Redacts known secrets and bounds external observations. | Protect logs and feedback; preserve enough prompt hashes/evidence for reproducibility. |
| `src/veritas/io.py`: `canonical()`, `digest()`, `file_hash()`, JSON/JSONL functions | Stable encoding, hashes, and artifact IO. | Hash plan, protocol, prompts, models, task manifests, and outputs. |
| `src/veritas/provenance.py`: `implementation()`, `critic_identity()`, `verifier_identity()` | Computes implementation and model/config identities. | Extend identity manifest with actor revision, cue/control hash, system prompt, and grader. |

### Configuration, task preparation, and execution safety

| File / functions | Current job | Why it matters |
|---|---|---|
| `src/veritas/config.py`: `ModelConfig`, `SandboxConfig`, `RunConfig`, `GraphConfig`, `OpportunityConfig`, `Config`, `load_config()` | Validates YAML settings and override merging. | Add explicit experiment config rather than hiding `D/A` in general runtime flags. |
| `src/veritas/data.py`: `download()`, `normalize()`, `prepare()`, `load_tasks()` | Downloads pinned datasets, normalizes rows, creates task splits, loads task/assignment pairs. | Create separate awareness development/pilot/confirmation manifests, group-aware and frozen. |
| `src/veritas/eligibility.py`: `eligible_models()`, `verify_original_tasks()` | Filters models and validates original task metadata. | Ensure model inclusion/revision and task provenance are fixed before execution. |
| `src/veritas/contracts.py`: argument models, `valid_path()`, `contract()` | Validates tool schema and path scope. | Keeps tool behavior consistent; valid action syntax does not prove patch correctness. |
| `src/veritas/sandbox.py`: `DockerSandbox` and workspace helpers | Runs tools in Docker and prepares isolated workspaces/patches. | Reset workspace for each arm, record image digest, prevent treatment leakage through state. |
| `src/veritas/worker.py` | Worker/support routines for bounded execution. | Keep executor setup identical across treatment cells. |
| `src/veritas/config.py` / `src/veritas/models.py` | Backend config and generation/inference settings. | Record actor/verifier model identity and sampling settings exactly. |

### Existing calibration, comparison, and reporting

| File / functions | Current job | Relevance and limitation |
|---|---|---|
| `src/veritas/critic.py`: `training_rows()`, `train_linear()`, `TrainedCritic.score()`, `score_records()`, `train_lora()` | Trains/scores a critic for action-error prediction. | `train_lora()` adapts the critic, not the coding actor. Critic is optional for the awareness factorial. |
| `src/veritas/calibration.py`: `calibration_metrics()`, `fit_temperature()`, `_fit_artifact()`, `apply_artifact()`, `fit_artifact()`, `load_artifact()`, `assess_calibration()` | Temperature scaling and verifier/recovery statistic estimation with held-out checks. | Useful for current controller policies; not a factorial estimator or a conformal guarantee. |
| `src/veritas/comparison.py`: `create_plan()`, `run_comparison()`, `grade_swe()`, `comparison_rows()`, `policy_effects()`, `report_comparison()` | Plans model/policy comparisons, runs jobs, grades SWE patches, and reports paired policy effects. | Reuse grading and infrastructure carefully. Current plans set `audit_all=False`; no `D × A` randomization. |
| `src/veritas/replay.py`: `eligible_records()`, `evaluate()`, `tune()`, `load_tuning()`, `paired_bootstrap()`, `sweep()` | Replays saved traces and tunes/evaluates current policies. | Does not reproduce a changed actor trajectory after cue or verifier feedback. Not causal evidence for awareness. |
| `src/veritas/report.py`: `frontier_report()`, `online_report()`, `action_metrics()`, `recovery_comparison()` | Reports existing run/policy/frontier metrics. | Add factorial outcomes in a separate analysis/report with planned contrasts and clustered uncertainty. |
| `src/veritas/plots.py`: `plot_comparison()` | Plots current policy comparisons. | Can later visualize four cell means, contrasts, cost-quality, and model interactions. |
| `src/veritas/diagnostics.py`: `diagnose_run()` | Checks run/calibration evidence and failures. | Use before accepting any pilot ledger as complete. |
| `src/veritas/graph.py`: `Node`, `DAG` | Represents dependency/check ordering. | Not the awareness treatment. |

### Existing dependency pilot: separate line of work

| File / functions | Current job | Why it is secondary |
|---|---|---|
| `dependency_scope.py`: `scope_spec()`, `screen_row()`, `create_scope()` | Screens tasks for public-evidence target/caller reviews. | Candidate cohort construction only. |
| `dependency_cohort.py`: `verified_scope()`, `prepare_reviews()`, `validate_evidence()`, `finalize_cohort()`, `verify_cohort()` | Records evidence/reviews and freezes cohort/protocol. | Does not manipulate evaluation awareness. |
| `dependencies.py`: `Bindings`, `_bindings()`, `_dotted()`, `_module()`, `_imports()`, `_inventory()`, `compare_symbols()`, `extract_dependencies()`, `write_dependencies()` | Extracts conservative static Python call candidates and symbol changes. | A candidate edge is not proof of runtime or causal dependency. Optional feature only. |
| `opportunities.py`: `OpportunityTracker.observe()/handle()/finish()/report()`, `WorkspaceObserver.observe()/finish()` | Detects target/caller triggers in shadow mode. | Does not run factorial awareness treatment. |
| `state.py`: `tree_hash()`, `Checkpoint`, continuation checkpoint/restore/fork, branch transition/charge, `safe_extract()` | Hashes and snapshots/forks workspace state with budgets. | Potential reuse for state isolation; not a completed continuation experiment. |
| `dependency_pilot.py`: `create_pilot()`, `run_pilot()`, `pilot_rows()`, `report_pilot()` | Plans and reports the earlier dependency four-arm pilot. | Current arms are shadow observations, not this paper's `D/A` arms. |
| `dependency_analysis.py`: `analyze_pilot()`, bootstrap/power summaries | Bootstraps `group_id` averages and estimates dependency interaction; enables causal estimates only for active dependency intervention records. | Reuse resampling primitives, not the reader/estimand unchanged. `group_id` is generally a task ID; use explicit repository clusters and preserve planned task weights. Its normal-approximation power helper is not success-ICC estimation. |
| `dependency_models.py`: `_features()`, `_design()`, `_cluster_interval()`, `fit_benefit_models()` | Models target/caller benefit. | Separate hypothesis and features. |
| `dependency_allocation.py`: `create_allocation()`, `select_next()`, `record_result()`, `allocation_report()` | Allocates dependency pilot runs adaptively and records propensities. | Not a randomized factorial planner. |
| `conditional_planner.py`: `ConditionalVerificationPlanner` selection/resolve/feedback/snapshot | Prototype for planning conditional checks from estimates. | Not wired to awareness assignments. |
| `dependency_evaluation.py`: `freeze_evaluation()`, `report_evaluation()` | Freezes/reports dependency confirmation. | Separate from this paper. |
| `dependency_release.py`: `create_release_manifest()`, `verify_release_manifest()` | Creates/checks file hash manifest. | Useful for release integrity, not scientific validation. |
| `suite.py`: `variants()`, `create_suite()`, `run_suite()`, `report_suite()` | Orchestrates resumable configuration/model matrices. | May help launch jobs after adding explicit arms; cannot itself guarantee assignment validity. |

## 13. How to develop, trial, and run this safely

### A. Development and trial-and-error

1. **Use development tasks only.** Make a small task list from the experiment development pool.
   Do not use the final confirmation tasks to tune cue wording, prompts, stopping, or tools.
2. **Use fake models in unit tests.** Verify randomization, treatment labels, prompt construction,
   feedback suppression, hidden audit isolation, and record completeness without inference cost.
3. **Use one local model for initial smoke runs.** Inspect the exact prompt/log in every arm,
   confirm cue/control placement, test both compact and regular context, and check the four arm
   paths differ only as assigned.
4. **Separate manipulation from outcome pilots.** Stage 0 checks cue recognition and
   pre-feedback process measures. Stage 1 adds independent repair grades on the intended actors
   to estimate outcome variance, task/repository dependence, completion and harness failures.
   Ungraded Stage 0 traces cannot supply success ICC or justify the main sample size.
5. **Freeze a new protocol version after every design-changing iteration.** Cue text, model,
   verifier, tool, budget, grader, and randomization changes must get a new hash and output dir.
   Keep exploratory runs clearly marked.

### B. Confirmatory execution

1. Freeze task and repository split, model revisions, cue/control, verifier, token/time budgets,
   analysis, exclusions, and grader settings.
2. Create a run plan with all four arms for every selected task/model block and stored
   randomization probabilities.
3. Execute each arm in a new workspace initialized from the exact same base revision. Randomize
   run order. Do not share an agent transcript or writable state across arms.
4. Preserve every attempt and output. Resume only the exact frozen plan at the boundaries in
   section 8.6. Do not silently retry failed tasks with different settings.
5. Grade final patches independently and link task ID, arm, actor revision, patch hash, and grader
   record.
6. Analyze the locked outcomes once using the preregistered contrasts and clustered uncertainty.

### C. Runtime command map

Commands below are currently implemented, except where explicitly labeled planned. Run from the
repository root and inspect `veritas <command> --help` for required paths/options.

| What you need to do | Existing command | What it does / does not do |
|---|---|---|
| Check local config and services | `veritas doctor --config configs/experiment.yaml` | Validates configuration. Add `--check-models` to check model metadata. No task inference. |
| Download pinned datasets | `veritas data download --manifest configs/datasets.yaml ...` | Downloads declared releases. Preserve manifest/revision. |
| Prepare task rows/splits | `veritas data prepare --manifest configs/datasets.yaml ...` | Normalizes and splits supported sources. For this paper, make an experiment-specific group-aware split and freeze it. |
| Prepare SWE images | `veritas swe image-map`, then `veritas swe pull-images` or `build-images` | Prepares image mapping and container images; check command help for exact args. |
| Run one current workflow | `veritas collect --config ... --tasks ... --output ...` | Executes the existing actor/controller/verifier loop. Good for smoke tests, not the new factorial study. |
| Compare existing policies | `veritas compare --config ... --output ... --execute`; then `--report` | Runs a frozen policy comparison. It currently has no awareness assignment. Avoid `split: null` for confirmation. |
| Inspect current artifacts | `veritas report ...`, `veritas diagnose-run ...` | Summaries/diagnostics of existing runs. No causal awareness analysis. |
| Fit existing critic/controller calibration | `veritas critic ...`, `veritas calibrate ...`, `veritas validate-calibration ...`, `veritas tune ...`, `veritas replay ...` | Supports current error/risk policy workflow; this is not the new factorial analysis. |
| Run factorial study | `veritas awareness plan/run/resume/grade/report` | Code present, execution unvalidated. `run` executes actor trials; `grade` processes frozen outputs with the pinned harness. |
| Qualify local prerequisites | `veritas awareness qualify` | Records declared model, image, grader and code provenance; does not call actor inference or certify compatibility by execution. |
| Extract process measures | `veritas awareness measure` | Computes versioned patch/test/language measures and optional elicitation joins after actor runs. |
| Freeze repository pools | `veritas awareness split` | Saves four disjoint pools; planner also checks repository and task aliases. |
| Inspect integrity / deferred audits | `veritas awareness verify/audit` | `verify` checks frozen files and ledger projections; `audit` calls the reviewer only after actor execution ends. |
| Develop wording / plan power | `veritas awareness check-cue/power` | Separate comprehension sessions; graded-pilot binary cluster simulation with missingness/MDE scenarios. |
| Study gate transfer | `veritas awareness fit-gate/calibrate-gate/gate-report` | Development score, reserved calibration, locked confirmation, risk/coverage and paired transfer intervals. |

Configure `configs/awareness-pilot.example.yaml` with prepared task images, actual model identities,
and the dedicated grader Python. `plan` fingerprints the installed grader without running it;
SWE-ReBench requires commit `d307ff9f2168a0448843c0d5881d2cd498d9f73f`. Use one frozen split manifest
across all partitions. Run and grade development/pilot/calibration separately. Fit the static
scorer on development data, then freeze calibration into the confirmation plan before calling
confirmation `grade`. No command here has been executed as part of the code implementation.

Never launch an expensive confirmatory run directly from `configs/comparison.yaml` without
review: the default is `split: null`, all prepared sources, and five tasks per source. Make a
paper-specific config with frozen task IDs, actor models, verifier, arms, and output root.

## 14. Tests required before model runs

The focused awareness tests are present and use local doubles. Before model runs, execute them
and address failures. At minimum they should cover:

- Every selected task/model block receives all four arms and assignment is reproducible from the
  frozen seed.
- Assignments use one of each arm per block; slot propensities, schedule and seeds are recorded.
- Numeric disclosure matches assignment probability; `null` differs from explicit zero.
  Duplicate aliases and repositories cannot cross the frozen split boundary.
- `D=1` cue appears in every actor turn of that run; `D=0` adds no review sentence; prompt
  hashes match logs; compact and non-compact contexts behave consistently.
- Before the boundary, switching `A` cannot change actor inputs or tool behavior under fixed
  stub responses. `A=0` makes zero online verifier calls; deferred audits cannot change outputs.
- Every arm reaches the same revision allowance when execution is viable. Draft submission does
  not terminate the trial, PASS is delivered in `A=1`, and a review never grants extra attempts.
- Cue and boundary message survive long histories. Review packets exclude treatment fields and
  private benchmark records; truncation is deterministic and logged.
- Phase calls are capped by remaining output allowance; no negative remaining budgets or hidden
  retries. Verifier usage cannot consume actor allowance, and missing usage stays unknown.
- Verifier failure, model timeout, malformed actor output, sandbox failure, retry, and missing
  grade are recorded and do not silently become success or zero cost.
- Each arm starts from the same base commit in an isolated workspace; run order is randomized;
  task/run IDs and final patch hashes are linked.
- Interrupted attempts remain present. Resume skips finished trials; grading retry does not call
  the actor; changed patches and harness versions cannot reuse a grading identity.
- Fixture reports from the pinned grader distinguish unresolved, invalid-patch and infrastructure
  errors. Unknown grades are neither omitted nor silently marked as observed test failures.
- The report computes the four means and the predeclared contrasts from task-level outcomes, not
  action rows, and includes cluster-aware uncertainty and missingness.
- Synthetic outcome fixtures recover known disclosure, feedback and interaction contrasts;
  repository resampling preserves all paired arms and the specified task weights. Legacy records
  remain unknown treatment. Static-gate calibration uses no confirmation labels, grades declined
  patches too, and reports zero admission as zero coverage with undefined conditional risk.

Only after these tests pass should you run local-model smoke tests. Tests check code behavior, not
novelty, power, task validity, or the research result.

## 15. Statistical and scientific analysis

### Primary analysis

Estimate cell means for task-level success and the pre-registered contrasts. Use paired/block
design where all arms share tasks; preserve task pairing. Account for repository clustering and
actor model. Report absolute percentage-point differences, confidence intervals, sample sizes,
and missing/failure counts. Predefine the primary contrast (recommended: `Y10-Y00`, anticipation
without feedback) and a small family of secondary contrasts with multiplicity handling.

For a complete dataset, first compute each task/actor's paired arm difference, average repetitions
within that task/actor, then average tasks with frozen weights. Report per-actor effects and a
prespecified equal-weight average across actors. Resample repository clusters while retaining
all tasks, arms, actors and repetitions together; do not bootstrap individual action rows. If
too few repositories are available for reliable cluster inference, widen recruitment or limit
the target claim and use a prespecified small-cluster/randomization analysis.

Keep assigned arms for all trials even when review delivery fails. Reports must show assigned,
attempted, completed, graded and unknown counts for every cell. An ungraded infrastructure
failure has an unknown repair outcome. Report per-cell bounds `resolved / assigned` through
`(resolved + unknown) / assigned`, with contrast bounds formed by subtracting the relevant cell
extremes; the interaction uses the corresponding four signed terms. Also report conservative
end-to-end success with unknowns counted as zero, clearly labeled as a system metric. Complete
case estimates are sensitivity analyses, not a silent replacement for the assigned population.
Sampling uncertainty and missingness bounds address different problems; report both. Freeze any
additional missing-data model and multiplicity procedure before confirmation.

### Power and sample size

Do not decide sample size from a generic per-cell rule. First run a pilot that estimates:

- baseline SWE task success and expected ceiling/floor;
- variance and task-level correlation across repeated arms;
- repository-level clustering and model-by-treatment heterogeneity;
- verifier call/feedback frequencies, task completion, grader failures, and cost;
- the smallest effect considered scientifically meaningful.

Then power the primary contrast at the task/run assignment unit. Repeated cells on one issue
improve pairing but do not create independent issue clusters. Report whether the design can
distinguish a meaningful effect from zero; a wide null interval is inconclusive.

Stage 0 without grading only estimates clustering of its measured proxies. A cheap actor's
proxy ICC is not the intended actor's repair-success ICC. Stage 1 needs independently graded
outcomes across enough repositories; carry pilot uncertainty into a sensitivity grid over
success rates, repository effects, paired-arm covariance and missingness. Simulate the actual
blocked design and planned estimator, including multiplicity and per-actor reporting. If there
are too few repositories, more repetitions of the same issues do not fix that limitation.

For scale only, an independent, equal-size two-proportion normal approximation at success near
30%, two-sided alpha 0.05 and power 80% gives approximately
`n_per_cell = 2*(1.96+0.84)^2*0.3*0.7 / MDE^2`: about 1,320 per cell for 5 percentage points,
or 330 for 10 points. Pairing, clustering and interaction testing change these numbers. The
suggested 250–600 tasks per cell is a compute scenario, not a validated power result.

Do not gate progression on a statistically significant beneficial process change. Freeze a
manipulation-fidelity rule (prompt received, probability understood/reported with uncertainty)
and a finite development budget for wording iterations. A flat behavioral dose-response is an
informative null or a reason to reconsider measurement, not permission to search indefinitely
until a favorable cue is found. Validate any selected cue on fresh pilot tasks and intended
actors; replacing explicit wording with few-shot cues creates a new treatment/protocol.

### Mechanism and policy analysis

Compute process measures separately for draft and revision. Draft measures precede feedback and
are the clearest evidence of anticipatory behavior. Specify them before inspecting main results:

| Proxy | Operational definition / limit |
|---|---|
| Diff size/scope | Added/deleted lines and changed files against the frozen base, with generated/vendor exclusions fixed in advance. Smaller is not necessarily better. |
| Tests added | New or modified test functions using language-aware extraction, plus a frozen blinded rubric for edge-case/regression intent. A filename count alone is not a “defensive-test count.” |
| Tests run | Tool invocations and identifiable test cases/results; separate repetitions and failed commands. Passing actor tests are not independent repair labels. |
| Hedging | Frozen lexicon/classifier count per eligible actor-authored word; exclude issue text, quotations, code and tool output. Empty language yields missing/undefined, not zero. |
| Confidence | Separate/post-task elicitation with recorded cost; the current actor emits tool JSON and may have no natural confidence statement. Never infer it from a missing phrase. |

Extractor versions and inputs must be hashed. Validate automated intent/language classifications
on a blinded development sample. Do not regress the primary treatment effect on these
post-treatment variables and call the remainder “pure awareness.” These analyses support
associations with possible mechanisms, not causal mediation without further assumptions.

### Stage 6: gate calibration transfer, specified before confirmation

Use a **Commit-Gates-inspired static admission experiment**, not a reproduction claim. The
source's 1.9% observation concerns its own tasks and loss; VERITAS cannot estimate what would
have happened in that study from coding-repair data. Awareness may affect transfer, but does
not automatically break a risk-control method applied within its assumptions.
[Commit Gates, calibration and validity discussion](https://arxiv.org/html/2609.10969)

1. On development repositories, fit or select a fixed patch-risk scorer and candidate threshold
   grid. `X` uses only public final-patch features and a frozen optional review score. Record
   score failures and default them to deferral. The scorer never sees hidden grader labels at
   inference. Score all required candidates after actor completion; record this additional cost.
2. Reserve disjoint gate-calibration repositories before Stage 5. Obtain independent grades for
   every candidate patch, including patches the gate would decline. Define comparisons within
   each fixed feedback assignment `A=a`, or under one preregistered mixture of `A` in every
   population. Mixing different feedback rates would confound disclosure transfer.
3. Select a threshold using `D=0` calibration only, then freeze it. On confirmation, evaluate
   the same gate separately in `D=0` and `D=1`; this is directional transfer `0 -> 1`. Prespecify
   `1 -> 0` too if withdrawal of awareness is the deployment question. Never subtract the
   factorial awareness contrast from a gate's risk as a supposed calibration correction.
4. Compare a pooled gate `g(X)` with a disclosure-aware family `g(X,D)` calibrated on the same
   total calibration data budget, with simultaneous error allocation across strata/candidates.
   The aware gate selects thresholds from its own calibration data, not from confirmation
   performance. Report coverage and resource differences alongside risk; more deferral alone
   can reduce the unconditional loss.

Let `S = g(X)` indicate admission, and `Y` independent repair success. For each disclosure and
feedback population, report:

```text
R(d,a;g) = E[S * (1-Y) | D=d, A=a]        unresolved admitted patches per candidate
K(d,a;g) = E[S | D=d, A=a]                admission coverage
F(d,a;g) = R(d,a;g) / K(d,a;g)            failure conditional on admission, if K>0
R(1,a;g0) - R(0,a;g0)                    transfer shift for the D=0-calibrated gate
R(d,a;g) - alpha                          signed target gap, alpha e.g. 0.05
```

Call this **unresolved-admission risk**, not unsafe tool execution. Report signed differences,
confidence intervals, counts and missingness bounds, whether positive, negative or null. A
point estimate above alpha is different from an interval wholly above alpha. A nominal target
and an empirical upper bound are different from an assumption-free guarantee. For unknown
grades, admit-related loss remains bounded between zero and one; it cannot be silently dropped.
For calibration, conservatively set an admitted unknown outcome's loss to one, or declare the
calibration incomplete under a frozen rule. Never certify using complete cases alone.

Choose one calibration procedure explicitly. Following the finite-family testing approach of
[Learn then Test](https://arxiv.org/abs/2110.01052), the proposed reference uses a simple
Hoeffding/union bound with **repository-level** loss: average `S*(1-Y)` over the fixed sampled
tasks/actors/repetitions within each repository, giving `L_r(g) in [0,1]`. For `m` independent
repositories sampled from the same target distribution, and `K` candidate gates fixed before
calibration, a conservative simultaneous Hoeffding bound is:

```text
U(g) = min(1, mean_r L_r(g) + sqrt(log(K/delta) / (2*m)))
certified candidates = {g : U(g) <= alpha}
```

Select coverage/cost among those candidates; if none qualify, report insufficient calibration
evidence and use the identically defer-all gate (zero admission risk, zero coverage). Allocate
delta over all additional strata/actor/direction families, or include them in `K`. This bound
targets an equal-repository population, deliberately distinct from the task-weighted factorial
mean. Its assumptions and potentially large repository requirement must be stated. Merely
clustering bootstrap intervals is not this guarantee. With fixed, nonrandom repository cohorts,
report a descriptive cohort result instead of claiming population certification. Across a
disclosure distribution shift, the original same-population guarantee does not transfer by fiat.

This transparent reference can later be replaced by a fully specified reproduction of a chosen
published procedure. `calibration.py` currently implements temperature/verifier calibration,
not learn-then-test or CRC. Do not label this Hoeffding construction “CRC,” equate expected-risk
CRC with a high-probability risk bound, or import the external paper's nominal target as evidence.

Offline evaluation is valid here because admission does not revise a frozen patch. Additional
static scorer calls count as deployment gate cost in this analysis even if executed offline for
the experiment; hidden grading remains measurement cost. A gate that instead changes feedback,
attempt budgets or future actions needs a new online randomized policy experiment (or a
separately justified off-policy estimator with recorded support). The current fixed-trace
`replay.py` and shadow verdicts alone cannot establish that causal policy effect.

## 16. Fine-tuning: does the paper need it?

**No actor fine-tuning is required for the main paper.** Keep actor parameters fixed; manipulate
the awareness cue and verifier feedback at inference time. This isolates the behavioral question
and makes the experiment feasible with the existing runtime.

`critic.train_linear()` and `critic.train_lora()` fine-tune/train an auxiliary critic, not the
coding agent. The critic is optional and should not be confused with the actor. If a later
fine-tuning question is added, make the checkpoint/training procedure another factor, keep
training tasks disjoint from evaluation, hash training data and checkpoint, and freeze it before
confirmation. Do not fine-tune on confirmation outcomes.

For model updates, inspect `ModelConfig`/`load_config()` in `config.py`, `collect()` in
`runtime.py`, `LocalModel.complete()` in `models.py`, and model identity functions in
`provenance.py`. Record immutable revisions/checkpoint hashes, not just friendly model names.

## 17. End-to-end pipeline and implementation order

Before Stage 0, implement the planner/ledger and prompt/session seam, then reviewer and grader
adapters, then analysis/reporting. Qualify the task images and model adapters; freeze all four
repository pools, including gate calibration. Pass the section 14 invariants and run the 16
development smoke trajectories. No scientific stage is operational until these paths exist.

| Stage | Experiment / artifact | Progression rule and interpretation |
|---|---|---|
| 0. Manipulation development | Small ungraded dose pilot, inexpensive actor first; matching assignment probabilities and pre-feedback proxies. Confirm selected wording on intended actors. | Verify cue delivery and comprehension with uncertainty. Wording changes are exploratory, bounded and versioned. A behavioral null is retained; it is not proof of implementation failure. |
| 1. Graded pilot and power | Independently grade four-cell trials across multiple repositories using intended settings. Estimate success rates, paired covariance, repository dependence, failures and throughput. | Simulate power for the minimum meaningful primary effect and planned secondary contrasts. Freeze sample size, weights, multiplicity, failures, analysis and spending cap. Stage 0 proxy ICC is not an input substitute. |
| 2. Development factorial | Full `2 × 2`, first actor, fixed `p*=0.5`, frozen reviewer, independent grades and deployed/measurement cost reports. | Report all four means and contrasts. This is developmental evidence if it informs later choices; do not relabel tuned development outcomes as frozen confirmation. |
| 3. Mechanism analysis | Versioned draft/revision diff, test, tool and language measures; optional independently graded draft subset. | Treat process measures as secondary; freeze extractors for confirmation. No causal mediation claim or outcome-based selection of the “best” proxy. |
| 4. Backbone robustness | Repeat all four cells with at least one additional actor family under matched within-actor limits. Optional base/instruct or reasoning-mode comparisons need adapter qualification. | Report per-actor effects and heterogeneity. A different family alone does not isolate training alignment as the cause. Do not select actors by favorable awareness effects. |
| 5. Frozen confirmation | Re-freeze final protocol and analysis after development; run once on untouched repositories for both actors. Gate thresholds are fixed from reserved calibration data before confirmation labels are opened. | Retain all assignments/attempts, independently grade final patches, execute preregistered analysis. Any tuning after opening results requires a fresh confirmation pool. |
| 6. Policy implication | Apply frozen static gates to Stage 5 patches, reporting within/cross-disclosure risk, coverage, costs and gaps versus target. | Uses separate development, calibration and test data; no adaptive fitting on Stage 5. Changing feedback policy requires new online runs. Report null or improved transfer as well as degradation. |

Stages 3 and 4 may overlap operationally, but their decisions must finish before Stage 5 is
unblinded. Stage 6 calibration occurs before confirmation is opened even though its final report
comes last. Publish the protocol, assignment manifest, analysis version, de-identified outcome
ledger and cost definitions alongside the results. No stage above has been claimed completed by
this architecture review.

### Decisions required before Stage 2 spending

| Decision | Required evidence |
|---|---|
| Disclosure | Frozen 50% wording, pre-feedback fidelity check on study actors, and separate definitions for assignment and shadow sampling. |
| Sample size | Graded pilot, repository counts, paired-contrast variance, MDE/power simulation and missingness sensitivity; not a generic per-cell range. |
| Model identities | Two available, capable actor families and one qualified reviewer, with revisions, chat/tool compatibility and measured serving footprint. |
| Gate | Static unresolved-admission loss, frozen scorer/candidate grid, calibration method, direction of transfer and untouched calibration/confirmation repositories. |
| Compute | Measured cost/time by role and cell, all stage/repetition counts, image/grading overhead and a non-outcome-dependent study spending cap. |

## 18. Summary status for readers

| Question | Current answer |
|---|---|
| What is the main paper direction? | Long-horizon LLM problem solving with iterative verification and autonomous repair. |
| What is the primary question? | On independently graded repository repairs, how much does actionable feedback add over an equally costly generic retry? |
| What do current VERITAS numbers show? | User-reported full-suite performance is 1,894/2,240 (84.55%) with 101 recorded repairs. These do not yet isolate feedback benefit because no matched equal-budget retry result is in the supplied summary. |
| What do recent papers show? | Equal-budget feedback/retry, feedback granularity, and long-horizon verification have already been studied. Novelty must lie in the specific repository-level causal result, robustness, and recovery/localization analysis. |
| What needs correction first? | Reconcile the 128-run awareness inventory with the reported 32-run primary zero-resolution cohort and identify exact rows for every statistic. |
| What is the next sequence? | Audit raw records → validate graders and denominators → pilot the matched-budget controls → power and freeze protocol → run untouched confirmation → report task-family effects and costs. |
| What stays separate? | The awareness factorial and dependency pilot remain distinct study lines unless a shared protocol and estimand are explicitly established. |
| What supports a strong submission? | A powered causal contrast, independent grades, controls for retry and total compute, task/model robustness, confidence intervals, calibrated claims, and a reproducible artifact. |

## Project document policy

`docs/ARCHITECTURE.md` is the single detailed project guide. Keep `README.md` as a short entry
point linking here. Keep run-specific results, protocols, and machine-readable configs in their
appropriate artifact/config locations rather than duplicating this guide.
