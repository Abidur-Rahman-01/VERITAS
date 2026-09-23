# Dataset provenance and availability

The default download manifest is `configs/datasets.yaml`. Every revision is an immutable
40-character upstream commit SHA verified on 2026-09-24. Raw JSONL preserves the original
fields; receipt manifests contain row counts and SHA-256 checksums. No task text, gold
patch, answer or trajectory has been synthesized by this project.

| Source | Pinned release rows | Purpose and execution status |
|---|---:|---|
| [SWE-bench train](https://huggingface.co/datasets/princeton-nlp/SWE-bench) | 19,008 | Original GitHub issue corpus; online use needs repository-specific environments absent from the official harness |
| Same release, dev | 225 | Original issue corpus; environment support must be checked per repository |
| Same release, test | 2,294 | Official-harness tasks; declared non-Verified research pool for this experiment |
| [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified) | 500 | Reserved online evaluation; subset overlap removed |
| [SWE-rebench](https://huggingface.co/datasets/nebius/SWE-rebench) | 21,336 | Original issue/PR tasks with installation metadata; uses the authors' execution fork |
| [GSM8K main train](https://huggingface.co/datasets/openai/gsm8k) | 7,473 | Human-written arithmetic questions; natural agent trajectories and numeric-answer grading |
| GSM8K main test | 1,319 | Official held-out arithmetic evaluation |
| [MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | 500 | Published competition-math subset; conservative exact-string metric |
| **Total original rows** | **52,655** | Counts include overlap between releases |
| **Unique prepared tasks** | **50,897** | 41,605 SWE + 8,792 GSM8K + 500 MATH |

The namespaces `SWE-bench/SWE-bench` and `princeton-nlp/SWE-bench` do not currently
have identical available splits. This implementation deliberately pins the latter
because the verified snapshot includes the 19,008-row original training split.

SWE-rebench tasks are mined from real GitHub issues and pull requests. Their authors
used automated/LLM-assisted environment setup and quality filtering; that is not the
same as synthetic issue generation. We preserve the released tasks and do not invent
new faults or questions. It is licensed CC BY 4.0, with underlying repository licenses
also applying. GSM8K's dataset card specifies MIT. SWE-bench and MATH cards do not both
provide a single clear dataset-level license field in the queried metadata; consult
the source repositories/cards and preserve applicable original licenses and citations.
Do not assign this repository's code license to downloaded data.

The delivered research partition contains:

| Partition | Distinct tasks |
|---|---:|
| Development | 4,431 |
| Calibration | 12,148 |
| Validation | 10,842 |
| Test | 18,936 |
| Backbone transfer | 4,540 |

Ratios are approximate because of repository strata and forced official holdouts.
Verified's 500 tasks all remain test tasks. The exact protocol, task assignments and
hashes are recorded in `data/prepared/manifest.json` and `splits.json`.

An additional 6,376-row original `nebius/SWE-bench-extra` release was inspected during
development. Its snapshot was downloaded, but its tasks also require nonstandard
environments. It is not in the default manifest, prepared dataset, or counts above.

References for execution details:

- [Official SWE-bench evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)
- [SWE-rebench's upstream execution fork](https://github.com/SWE-rebench/SWE-bench-fork)
- [SWE-rebench infrastructure description](https://nebius.com/blog/posts/infrastructure-behind-swe-rebench)

Large source corpora do not supply independent per-action labels, calibrated risk
scores or every candidate's verifier outcome. Those artifacts must come from actual
rollouts, audits and adjudication. The supplied tools collect them; none are fabricated.
