# VERITAS novelty audit: first-pass literature map

**Audit date:** 2026-10-19  
**Purpose:** Check the paper's candidate contributions against directly related Transactions and A* work and define a defensible next study.  
**Scope:** Targeted first-pass review of IEEE/ACM Transactions outlets and recent ICSE/ASE/ICLR/NeurIPS work found through publisher, conference, and arXiv records. This is not an exhaustive systematic review and cannot support a universal “first” claim. A formal review needs reproducible database queries, inclusion criteria, citation chaining, and ideally a second reviewer.

**Current direction:** [ARCHITECTURE.md](ARCHITECTURE.md) now specifies an evidence-selection
controller evaluated against the strongest fixed feedback policy on matched repository repair
branches. The feedback-versus-generic-retry question below is a prior candidate. This audit's
overlap findings remain relevant, but it has not established novelty for the current controller.
Two distinct 2026 preprints use the name “VeriHarness”: [Structured Feedback Improves Repair in
an LLM Agent Loop](https://arxiv.org/abs/2607.14167) names its prototype VeriHarness, while
[VeriHarness: Scaling Agentic Verification for Long-Horizon Tasks](https://arxiv.org/abs/2610.00972)
is a separate October paper.

## Executive verdict

### Revised answer after checking the cited 2026 papers

No broad question about LLM verification, adaptive verification effort, repository-specific
criteria, test-time scaling, or active test generation is novel on its own. The cited papers already
cover these components: [LLM-as-a-Verifier](https://arxiv.org/abs/2607.05391) supplies continuous,
decomposed verification scores and candidate ranking; [Agentic Rubrics (ACL 2026)](https://aclanthology.org/2026.acl-long.697/)
constructs repository-grounded patch criteria; [EGSS (ACL 2026)](https://aclanthology.org/2026.acl-long.1359/)
uses entropy-guided adaptive search and test-suite augmentation; and [Scaling Agentic Verifier
(ICML 2026)](https://proceedings.mlr.press/v306/ma26av.html) actively searches for discriminative
execution inputs. [SWE-Bench Pro (ICML 2026)](https://proceedings.mlr.press/v306/deng26f.html)
also means a benchmark claim should be about verification outcomes, not merely a larger or harder
repository task set. Benchmark integrity must account for the concerns in [SWE-Bench Pro
Verified](https://arxiv.org/abs/2609.08149).

The earlier primary candidate question was:

> **On independently graded repository-level bug fixes, what is the incremental effect of
> actionable verifier feedback over a generic retry under the same total compute budget, and how
> does that effect vary with initial patch correctness, fault-localization difficulty, model family,
> and task difficulty?**

This was a **defensible candidate gap, not a verified novelty claim**. Its novelty would be the causal
measurement in real repository repairs, including recovery/regression outcomes and prespecified
heterogeneity, if an exhaustive search confirms that this exact population and outcome have not
already been studied. It is more supportable than claiming a new generic evidence-aware adaptive
controller: the named papers already occupy key pieces of that controller, and the local audit found
direct overlap for generic verifier-feedback-versus-retry comparisons. The current architecture
therefore makes evidence selection the primary intervention and requires a held-out randomized
comparison against strong fixed feedback before claiming a policy contribution.

The broad question—whether verifier feedback improves success beyond giving a model another attempt at equal cost—is **not novel as stated**. A close 2026 *Information and Software Technology* paper explicitly separates gate diagnostics from retry opportunity with a matched generic-retry control across 458 paired TAM-Eval tasks and five Qwen2.5-Coder sizes. An ASE APR 2026 paper separately isolates feedback representation on 540 HumanEval+/MBPP+-derived tasks with token-matched and redundant-feedback controls. Other 2026 work directly studies iterative repair and agentic verification over long-horizon tasks.

The narrower question may remain publishable: **does actionable feedback improve independently graded repository-level bug repair beyond an equal-budget retry, and how does that effect vary by model, task, initial correctness, and localization difficulty?** It must be presented as a new population/outcome and heterogeneity study, not as the first feedback-versus-retry test. The current VERITAS suite does not answer that contrast: it lacks the matched no-feedback arm, and the repository's RESULTS.md says the primary 32-run SWE factorial cohort had zero resolved tasks.

The evaluation-disclosure × feedback factorial is the most distinct candidate in the project, but its broad concept overlaps active evaluation-awareness research. Its current small cohorts and SWE floor results do not establish a robust repair-success effect. Keep it separate and exploratory unless a powered replication and systematic review support it.

## Candidate-by-candidate audit

| Candidate claim | Closest prior work found | Novelty assessment | What VERITAS has / lacks |
|---|---|---|---|
| Verifier feedback beats an equally costly extra attempt | [Which quality gates actually improve agentic software maintenance?](https://www.sciencedirect.com/science/article/pii/S0950584926003526), *Information and Software Technology*, available online in 2026 / issue 2027. It uses five quality-gate policies and a matched generic-retry control on 458 paired TAM-Eval tasks; 30,524 model-policy-task observations. | Directly overlaps the broad question. Its abstract says command-content acceptance without repository execution. | 2,240-task suite records 101 reported recoveries but has no matched retry control, so it cannot attribute those gains to feedback. Actual repository patch application and independent grading could still be a distinct extension. |
| Feedback representation affects repair | [Evaluating Symbolic Feedback Granularity for LLM-Based Program Repair](https://conf.researchr.org/details/ase-2026/apr-2026-papers/8/Evaluating-Symbolic-Feedback-Granularity-for-LLM-Based-Program-Repair), ASE APR 2026. Compares five feedback modalities on 540 HumanEval+/MBPP+-derived tasks, including token-matched and redundant-feedback controls. | Feedback format/granularity alone is occupied. | Current reports count repairs but do not isolate feedback contents. Focus instead on repository-level localization and independently graded outcomes. |
| Iterative execution feedback improves code | [Unlocking LLM Code Correction with Iterative Feedback Loops](https://arxiv.org/abs/2606.17514), 2026 preprint, studies compiler/test feedback across models and languages. | Broad iterative code-correction framing is occupied. | Distinguish with repository issue repair, equal-budget causal controls, and robust task/model heterogeneity. |
| Verification helps long-horizon agents | [VeriHarness](https://arxiv.org/abs/2610.00972), 2026 preprint, studies workspace/evidence-tool verification and revision across five long-horizon benchmarks. | “Long-horizon agentic verification” alone is not a novel claim. | A narrower study could test test-driven patch repair and recovery under matched budgets. |
| Evaluation cues alter agent behavior | [Coding audit realism](https://alignment.anthropic.com/2026/coding-audit-realism/), [EvalDetectBench](https://evaldetectbench.com/), and [ICLR 2026 work on evaluation-aware models](https://proceedings.iclr.cc/paper_files/paper/2026/hash/9334fd3a5170dbfe74eae4755f6c5f89-Abstract-Conference.html) show the area is active. These differ from a randomized disclosure × delivered-feedback factorial with independently graded SWE outcomes. | A specific D × A repository-repair experiment may remain a gap, but “first evaluation-awareness study in coding” is not defensible. | Candidate novelty only. Current cue cohorts are small; the reported 32-run primary SWE cohort is at 0% resolution. |
| Awareness causes anti-surrender / compute escalation | Existing awareness research establishes the construct; Anthropic studies coding-audit realism. | The exact persistence response may be a novel observation, not a new general construct. | cmd2 4/4 versus 0/4 is exploratory. Reported Fisher p=.0143 is one-sided; two-sided p is about .0286. Four observations per cell make the effect size uncertain. Avoid “forcing function” and generalization claims. |
| SWE failure is mainly fault localization, not reasoning | [SOSRepair](https://ieeexplore.ieee.org/document/8854217), *IEEE Transactions on Software Engineering* (2021), identifies fault-localization precision as important to repair success. | Fault localization as a repair bottleneck is established. | The cmd2-744 patch is an illustrative trace, not evidence that localization explains most failures. Need a coded sample and held-out randomized localization intervention. |
| Full-split benchmark plus repair counts is novel | Standard code/math benchmarks and iterative repair are established. | Scale and full-split coverage can be valuable empirical evidence but do not alone establish novelty. | Validate every task-level initial/final transition, define whether Pass@1 means one-shot or post-loop, and report costs, regressions, and controls. |
| Cross-dataset cue effects generalize | Multi-domain agent evaluation is established. | The reported small pilot does not establish generality. | Most domains have two tasks. A powered, stratified replication is required. |
| Gate calibration transfers across awareness conditions | Calibration/verification allocation are established directions. | Potentially a contribution only if the proposed held-out transfer stage is actually run and adds measurable value. | The architecture is not a result; do not claim this contribution yet. |

## What the closest papers mean for the proposed question

The *Information and Software Technology* study is the closest match to the equal-cost retry question. Its abstract describes diagnostic feedback policies versus a matched generic retry, on TAM-Eval command-content acceptance without repository execution, across 458 paired tasks and five model sizes. The paper concludes that value varies with model and configuration. This makes the original broad question already answered in an adjacent setting. The viable distinction is the harder outcome: real repository patches graded by isolated tests, with feedback's marginal value measured after controlling for retry budget.

ASE APR 2026 already asks how feedback representation changes code repair and controls for prompt length. VeriHarness already occupies general-purpose long-horizon verification. The TSE fault-localization precedent means a new paper needs agent-specific trajectory evidence and a causal intervention to claim more than “localization matters.”

## VERITAS evidence gaps to resolve before drafting claims

1. Reconcile 128 trials / 12 studies with PAPER.md's 32-run primary and 8-run CLI cohorts, and RESULTS.md's primary 32-run cohort with zero resolved tasks. List the exact rows used for each statistic.
2. Publish the randomization schedule and label every run confirmatory, exploratory, or repeated; identify task/model overlap.
3. Recompute tests from raw rows. State one- or two-sided hypotheses, test family used for BH, clustering/dependence assumptions, adjusted p-values, and effect-size intervals.
4. Validate the 2,240 denominator and all 101 recoveries from per-task initial and final grades. State whether Pass@1 is one-shot or post-loop final success.
5. Treat cryptographic integrity as ledger integrity only. It does not prove randomization, task validity, grading correctness, or causal identification.
6. Document the localization intervention's assignment, sample size, held-out tasks, and independent outcomes before describing it as causal.

## Recommended defensible follow-up

Do not claim novelty for “does verifier feedback beat an equally costly extra attempt?” in general. Test this narrower extension:

> **On independently graded repository-level repairs, what is the incremental effect of actionable verifier feedback over an equal-token retry, and how does it depend on initial correctness, localization difficulty, model family, and task difficulty?**

Use three matched arms: draft-only; equal-budget generic retry; equal-budget actionable verifier feedback. Randomize within issue/model blocks, freeze task and repository splits, and independently grade every final patch. Predefine recovery among initially failing tasks, regressions among initially passing tasks, and compute per additional resolved issue. Add a feedback-format ablation only if powered; ASE APR 2026 already covers broad feedback-granularity comparisons.

If retaining the awareness study, give it a separate narrow question: whether a realistic advance review-probability cue changes pre-feedback persistence and the marginal effect of actual review in repository repair. First obtain non-floor resolution rates, adequate power, and exact cohort accounting. Do not pool all 128 runs as one confirmatory sample without assignment and protocol evidence.

## Search record and limits

Queries on 2026-10-19 covered “LLM coding agent verifier feedback equal budget/retry,” “iterative program repair feedback loop,” “evaluation awareness coding agent disclosure,” “long-horizon agent verification,” and “fault localization LLM repository repair.” Direct related results were followed through publisher/conference/arXiv records. The first pass includes IEEE TSE, ACM TOSEM, *Information and Software Technology*, ASE 2026, ICLR 2026, and relevant 2026 preprints.

This does not cover every Transactions title, every A* venue, every workshop, or every paper/preprint. Before claiming “first,” run reproducible searches in Scopus/Web of Science/IEEE Xplore/ACM Digital Library/OpenAlex/Semantic Scholar, screen references/citations, and preserve the query exports and exclusions. “A*” also depends on the ranking scheme and field; specify the target venue and ranking system.
