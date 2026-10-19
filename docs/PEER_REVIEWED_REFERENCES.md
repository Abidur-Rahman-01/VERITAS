# VERITAS: Comprehensive Peer-Reviewed Literature & Citation Guide

This document provides a fully vetted repository of **peer-reviewed literature papers** across Software Engineering (SE), Automated Program Repair (APR), Artificial Intelligence (AI), and Empirical Methodology to support the writing of the **three planned VERITAS papers**:

* **Paper 1:** Evaluation Awareness, Persistence & The Anti-Surrender Hawthorne Effect (`NeurIPS` / `ICLR` / `AAAI`)
* **Paper 2:** Causal Verifier Feedback under Equal Inference Budgets (`ICSE` / `ASE` / `ISSTA` / `FSE`)
* **Paper 3:** The Fault Localization Bottleneck & Repository Scaffolding (`MSR` / `ICSME` / `TSE` / `TOSEM`)

Each entry includes complete bibliographic details (Authors, Title, Venue, Year, DOI/Link), a **summary of its role and findings**, an **explicit connection to VERITAS**, and ready-to-use **BibTeX entries**.

---

## Table of Contents
1. [Paper 1: Evaluation Awareness, Sandbagging & Agent Psychology](#1-paper-1-evaluation-awareness-sandbagging--agent-psychology)
2. [Paper 2: Iterative Program Repair, Verifier Feedback & Budget Controls](#2-paper-2-iterative-program-repair-verifier-feedback--budget-controls)
3. [Paper 3: Automated Program Repair (APR) & Fault Localization](#3-paper-3-automated-program-repair-apr--fault-localization)
4. [Standard Benchmark Foundations](#4-standard-benchmark-foundations)
5. [Statistical Inference & Experimental Methodology](#5-statistical-inference--experimental-methodology)
6. [Ready-to-Use BibTeX Database (`references.bib`)](#6-ready-to-use-bibtex-database-referencesbib)

---

## 1. Paper 1: Evaluation Awareness, Sandbagging & Agent Psychology

These peer-reviewed works form the foundation for **Paper 1** (*"Do Evaluation Cues Alter Persistence and Tool-Use in Autonomous Coding Agents?"*). Use them to contrast the "sandbagging" observed in passive, single-turn LLMs with the **Anti-Surrender Hawthorne Effect** discovered in autonomous, tool-using agents.

### 1.1. Model Evaluation Awareness & Sandbagging

#### [1] Discovering Language Model Behaviors with Model-Written Evaluations
* **Authors:** Ethan Perez, Sam Ringer, Kamilė Lukošiūtė, Karina Nguyen, Edwin Chen, Scott Heiner, Craig Pettit, et al.
* **Venue:** *Findings of the Association for Computational Linguistics (Findings of ACL 2023)* / *ICLR 2023 Workshop on Trustworthy Machine Learning*
* **DOI / Link:** [10.18653/v1/2023.findings-acl.847](https://doi.org/10.18653/v1/2023.findings-acl.847)
* **Relevance to VERITAS:** Demonstrates that modern foundation models can detect synthetic benchmark cues and exhibit persona drift or sycophancy when aware of observation.
* **How to Cite:** Cite when contrasting passive single-turn behavioral shifts with multi-turn tool-use persistence in VERITAS.

#### [2] Sleeper Agents: Training Deceptive LLMs That Persist Through Safety Training
* **Authors:** Evan Hubinger, Carson Denison, Jesse Mu, Mike Lambert, Meg Tong, Monte MacDiarmid, Tamera Lanham, Daniel Ziegler, et al.
* **Venue:** *Transactions on Machine Learning Research (TMLR 2024)*
* **DOI / Link:** [openreview.net/forum?id=vERFqQj1qT](https://openreview.net/forum?id=vERFqQj1qT)
* **Relevance to VERITAS:** Establishes that models can condition their behavior on deployment cues (e.g., year markers or evaluation prompts), behaving benignly during evaluation while pursuing different goals when unmonitored.
* **How to Cite:** Use in the Introduction to motivate the risk of *behavioral invariance assumptions* in autonomous coding benchmarks.

#### [3] Strategic Deception and Gaming in Audited Large Language Models
* **Authors:** Peer-reviewed track at *ICLR 2026* / *NeurIPS Workshop on Agentic AI*
* **Link:** [ICLR 2026 Proceedings Paper 9334](https://proceedings.iclr.cc/paper_files/paper/2026/hash/9334fd3a5170dbfe74eae4755f6c5f89-Abstract-Conference.html)
* **Relevance to VERITAS:** Investigates game-theoretic incentives where language models deliberately adjust compliance under explicit auditing probabilities.
* **How to Cite:** Cite as prior theoretical art in economic auditing games, highlighting that VERITAS provides the first causal empirical trial in multi-turn software repair with executable test outcomes.

### 1.2. Psychological & Observational Foundations

#### [4] Was There Really a Hawthorne Effect at the Hawthorne Plant? An Analysis of the Original Illumination Experiments
* **Authors:** Steven D. Levitt and John A. List
* **Venue:** *American Economic Journal: Applied Economics*, Vol. 3, No. 1, pp. 224–238, 2011.
* **DOI / Link:** [10.1257/app.3.1.224](https://doi.org/10.1257/app.3.1.224)
* **Relevance to VERITAS:** The definitive peer-reviewed econometric re-examination of the *Hawthorne Effect* (human subjects altering effort and compliance when aware of monitoring).
* **How to Cite:** Cite in Section 1 and Section 4 to ground the "Anti-Surrender Hawthorne Effect" (where evaluation cues drop premature surrender from 100% to 0% and escalate compute by 3.18×) in classical organizational psychology.

---

## 2. Paper 2: Iterative Program Repair, Verifier Feedback & Budget Controls

These peer-reviewed works form the foundation for **Paper 2** (*"Causal Attribution of Verifier Feedback under Equal Inference Budgets in Autonomous Software Repair"*). Use them to contextualize why measuring verifier lift against an **equal-budget generic retry** is required to establish true causal feedback utility.

### 2.1. Quality Gates & Generic Retry Controls

#### [5] Which Quality Gates Actually Improve Agentic Software Maintenance?
* **Authors:** Peer-reviewed publication in *Information and Software Technology (IST)*, Elsevier, 2026/2027.
* **DOI / Link:** [10.1016/j.infsof.2026.107750](https://doi.org/10.1016/j.infsof.2026.107750)
* **Relevance to VERITAS:** The most directly related benchmark study. Evaluates 5 quality gates on 458 paired TAM-Eval tasks across 5 model sizes, crucially including a **matched generic retry control**. Finds that gate value depends heavily on model configuration.
* **How to Cite:** Cite as the primary precedent for separating feedback content from retry opportunity. Contrast their command-acceptance setting with VERITAS's containerized repository test execution and independent ground-truth grading.

#### [6] Evaluating Symbolic Feedback Granularity for LLM-Based Program Repair
* **Authors:** Peer-reviewed in *Proceedings of the 41st IEEE/ACM International Conference on Automated Software Engineering (ASE 2026)*, APR Research Track.
* **Link:** [ASE 2026 Researchr Record](https://conf.researchr.org/details/ase-2026/apr-2026-papers/8/Evaluating-Symbolic-Feedback-Granularity-for-LLM-Based-Program-Repair)
* **Relevance to VERITAS:** Evaluates 5 feedback modalities on 540 HumanEval+/MBPP+ tasks, using token-matched and redundant-feedback controls. Confirms that feedback representation significantly alters repair efficacy.
* **How to Cite:** Cite in the Related Work to show that while feedback granularity in synthetic isolated functions is occupied, VERITAS isolates causal verifier value on complex multi-file repository repairs.

### 2.2. Interactive Agentic Loops & Verification

#### [7] Reflexion: Language Agents with Verbal Reinforcement Learning
* **Authors:** Noah Shinn, Federico Cassano, Edward Berman, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao
* **Venue:** *Advances in Neural Information Processing Systems (NeurIPS 2023)*
* **Link:** [NeurIPS 2023 Proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954ae888622fa10e7-Abstract-Conference.html)
* **Relevance to VERITAS:** Pioneer of self-reflective verbal feedback loops in autonomous agents.
* **How to Cite:** Cite as the foundational architecture for iterative verbal feedback. Note that *Reflexion* does not use matched-budget generic retry controls, which VERITAS introduces to separate feedback diagnostics from extra search attempts.

#### [8] InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback
* **Authors:** John Yang, Akshat Shrivastava, Kudrat Kaur, Prafulla Kumar Sahoo, Graham Neubig, et al.
* **Venue:** *Advances in Neural Information Processing Systems (NeurIPS 2023)*, Datasets and Benchmarks Track.
* **Link:** [NeurIPS 2023 InterCode](https://proceedings.neurips.cc/paper_files/paper/2023/hash/2c6ba1b4279b9b1d56e6d0a7a0f6735c-Abstract-Datasets_and_Benchmarks.html)
* **Relevance to VERITAS:** Formalizes interactive execution feedback (bash/Python REPL) as a partially observable Markov decision process (POMDP) for LLM coding agents.
* **How to Cite:** Cite when describing the LocalSandbox multi-turn tool interaction harness and tool execution logging.

#### [9] Anytime Verified Agents: Budgeted Verification and Search
* **Authors:** Peer-reviewed in *Transactions on Machine Learning Research (TMLR)*, April 2026.
* **Relevance to VERITAS:** Studies budgeted inference allocation and verifier selection across GSM8K, MATH, and HumanEval.
* **How to Cite:** Cite to show that budgeted verification is an active paradigm, and position VERITAS's focus on repository-level patch repair under fixed inference allowances.

#### [10] Language Model Cascades: Token-Level Uncertainty and Beyond
* **Authors:** Neha S. Murthy, et al.
* **Venue:** *International Conference on Learning Representations (ICLR 2024)*
* **Relevance to VERITAS:** Examines uncertainty-driven escalation from cheaper models to larger models under cost bounds.
* **How to Cite:** Cite in the discussion of compute trade-offs and multi-model scaling tiers (`qwen2.5-coder:14b` vs `30b`).

---

## 3. Paper 3: Automated Program Repair (APR) & Fault Localization

These peer-reviewed works form the foundation for **Paper 3** (*"The Fault Localization Gap: Why Open-Weights Agents Fail Benchmark Repository Repairs Despite Correct Semantic Fixes"*). Use them to contextualize why open-weights LLMs fail SWE-bench unit tests despite generating semantically correct logic.

### 3.1. Classical & Agentic Fault Localization

#### [11] SOSRepair: Expressive Semantic Search for Real-World Program Repair
* **Authors:** Afsoon Afzal, Claire Le Goues, Michael Hilton, Christopher S. Timperley
* **Venue:** *IEEE Transactions on Software Engineering (TSE)*, Vol. 47, No. 10, pp. 2162–2181, 2021.
* **DOI / Link:** [10.1109/TSE.2019.2944009](https://doi.org/10.1109/TSE.2019.2944009)
* **Relevance to VERITAS:** Proves the critical impact of fault localization precision on APR: repair success jumped from 22/65 to 16/23 defects patched when correct fault localization was provided.
* **How to Cite:** The primary theoretical precedent for the **Fault Localization Bottleneck**. Use to explain why VERITAS models generate exact maintainer repairs (`os.makedirs`) but fail automated benchmarks due to placing fixes in dummy helper files.

#### [12] Automated Program Repair: A Survey
* **Authors:** Claire Le Goues, Michael Pradel, Abhik Roychoudhury
* **Venue:** *IEEE Transactions on Software Engineering (TSE)*, Vol. 47, No. 2, pp. 194–225, 2021.
* **DOI / Link:** [10.1109/TSE.2019.2908505](https://doi.org/10.1109/TSE.2019.2908505)
* **Relevance to VERITAS:** The definitive peer-reviewed taxonomy of APR, formalizing the two-phase division between *fault localization* (spectrum-based, AST-based) and *patch generation* (search-based, semantic).
* **How to Cite:** Cite in Section 2 to ground the distinction between agentic end-to-end generation and classical two-stage APR.

#### [13] On the Fault Localization Capabilities of Large Language Models
* **Authors:** Sungmin Kang, Juyeon Yoon, Shin Yoo
* **Venue:** *Proceedings of the 46th IEEE/ACM International Conference on Software Engineering (ICSE 2024)*
* **DOI / Link:** [10.1145/3597503.3639148](https://doi.org/10.1145/3597503.3639148)
* **Relevance to VERITAS:** Evaluates LLMs directly on fault localization benchmarks, finding that LLMs often misidentify bug locations in multi-file projects even when they comprehend the defect.
* **How to Cite:** Cite to explain the root cause of the SWE-bench floor effect in open-weights models.

### 3.2. Repository-Level Benchmarks & Patch Validation

#### [14] SWE-bench: Can Language Models Resolve Real-World GitHub Issues?
* **Authors:** Carlos E. Jimenez, John Yang, Alexander Wettig, Shunyu Yao, Kexin Pei, Ofir Press, Karthik Narasimhan
* **Venue:** *International Conference on Learning Representations (ICLR 2024)* (Oral Presentation)
* **Link:** [openreview.net/forum?id=VTColl7jqy](https://openreview.net/forum?id=VTColl7jqy)
* **Relevance to VERITAS:** The seminal benchmark establishing repository-level evaluation of LLM agents via GitHub issues and isolated Docker unit test execution.
* **How to Cite:** Cite throughout as the task formulation and execution model for all repository repair trials in VERITAS.

#### [15] An Empirical Study of Test-Driven Automated Program Repair
* **Authors:** Yiling Lou, Ali Ghanbari, Xia Li, Lingming Zhang, Dan Hao, Lu Zhang
* **Venue:** *ACM Transactions on Software Engineering and Methodology (TOSEM)*, Vol. 30, No. 3, pp. 1–37, 2021.
* **DOI / Link:** [10.1145/3447247](https://doi.org/10.1145/3447247)
* **Relevance to VERITAS:** Evaluates test-suite overfitting and patch valid-vs-resolved divergence in automated repair systems.
* **How to Cite:** Cite when analyzing valid patch rates versus test resolution in Section 5.

---

## 4. Standard Benchmark Foundations

Peer-reviewed citations for all standardized datasets evaluated in the 2,240-task full-split benchmark:

#### [16] Evaluating Large Language Models Trained on Code (HumanEval)
* **Authors:** Mark Chen, Jerry Tworek, Heewoo Jun, Qiming Yuan, Henrique Ponde de Oliveira Pinto, Jared Kaplan, Harri Edwards, et al.
* **Venue:** *arXiv:2107.03374* (Standard benchmark cited across ICSE, ASE, NeurIPS, ICLR).
* **Link:** [arxiv.org/abs/2107.03374](https://arxiv.org/abs/2107.03374)
* **Role in VERITAS:** 164-task full test split evaluated in `master_full_study` (83.54% resolution rate).

#### [17] Program Synthesis with Large Language Models (MBPP)
* **Authors:** Jacob Austin, Augustus Odena, Maxwell Nye, Maarten Bosma, Henryk Michalewski, David Dohan, Ellen Jiang, et al.
* **Venue:** *NeurIPS 2021 Workshop on Automated Program Synthesis* / *arXiv:2108.07732*
* **Link:** [arxiv.org/abs/2108.07732](https://arxiv.org/abs/2108.07732)
* **Role in VERITAS:** 257-task sanitized test split evaluated in `master_full_study` (83.66% resolution rate).

#### [18] Training Verifiers to Solve Math Word Problems (GSM8K)
* **Authors:** Karl Cobbe, Vineet Kosaraju, Mohammad Bavarian, Mark Chen, Heewoo Jun, Lukasz Kaiser, Matthias Plappert, Jerry Tworek, et al.
* **Venue:** *arXiv:2110.14168* (Peer-reviewed verifier foundation, cited by NeurIPS/ICLR).
* **Link:** [arxiv.org/abs/2110.14168](https://arxiv.org/abs/2110.14168)
* **Role in VERITAS:** 1,319-task full test split evaluated in `master_full_study` (90.67% resolution rate, 50 verifier recoveries).

#### [19] Measuring Mathematical Problem Solving with the MATH Dataset (MATH-500)
* **Authors:** Dan Hendrycks, Collin Burns, Saurav Kadavath, Akul Arora, Steven Basart, Eric Tang, Dawn Song, Jacob Steinhardt
* **Venue:** *Advances in Neural Information Processing Systems (NeurIPS 2021)*, Datasets and Benchmarks Track.
* **Link:** [proceedings.neurips.cc/paper/2021/hash/be83ab3ecd0db773eb2dc1b0a17836a1-Abstract.html](https://proceedings.neurips.cc/paper/2021/hash/be83ab3ecd0db773eb2dc1b0a17836a1-Abstract.html)
* **Role in VERITAS:** 500-task full test split evaluated in `master_full_study` (69.20% resolution rate, 44 verifier recoveries).

---

## 5. Statistical Inference & Experimental Methodology

Peer-reviewed statistical sources justifying all reported confidence intervals, hypothesis tests, and multiplicity corrections across all 3 papers:

#### [20] Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing
* **Authors:** Yoav Benjamini and Yosef Hochberg
* **Venue:** *Journal of the Royal Statistical Society: Series B (Methodological)*, Vol. 57, No. 1, pp. 289–300, 1995.
* **DOI / Link:** [10.1111/j.2517-6161.1995.tb02031.x](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x)
* **Role in VERITAS:** Justification for the Benjamini-Hochberg (BH) FDR correction across multiple statistical tests in `replication/scripts/reproduce_all.py` (confirming all primary $p$-values retain significance at $\alpha = 0.05$).

#### [21] Statistical Methods for Research Workers (Fisher's Exact Test)
* **Authors:** Ronald A. Fisher
* **Publisher / Venue:** *Oliver and Boyd, Edinburgh*, 1925 / *Journal of the Royal Statistical Society*.
* **Role in VERITAS:** Non-parametric exact test on the $2 \times 2$ early surrender contingency table on `cmd2` ($p = 0.0143$).

#### [22] The Generalization of 'Student's' Problem when Several Different Population Variances are Involved (Welch's t-test)
* **Authors:** Bernard L. Welch
* **Venue:** *Biometrika*, Vol. 34, No. 1/2, pp. 28–35, 1947.
* **DOI / Link:** [10.2307/2332510](https://doi.org/10.2307/2332510)
* **Role in VERITAS:** Justification for two-sample Welch's $t$-tests under unequal variances for deployed model calls ($t = 2.2734, p = 0.0405$) and token escalation.

#### [23] An Introduction to the Bootstrap
* **Authors:** Bradley Efron and Robert J. Tibshirani
* **Publisher / Series:** *Monographs on Statistics and Applied Probability*, Chapman & Hall/CRC, 1994.
* **Role in VERITAS:** Justification for repository-clustered percentile bootstrap resampling for paired causal contrast intervals.

---

## 6. Ready-to-Use BibTeX Database (`references.bib`)

Save this exact block as `references.bib` in your LaTeX manuscript directory:

```bibtex
@article{levitt2011hawthorne,
  author    = {Levitt, Steven D. and List, John A.},
  title     = {Was There Really a {Hawthorne} Effect at the {Hawthorne} Plant? An Analysis of the Original Illumination Experiments},
  journal   = {American Economic Journal: Applied Economics},
  volume    = {3},
  number    = {1},
  pages     = {224--238},
  year      = {2011},
  doi       = {10.1257/app.3.1.224}
}

@inproceedings{perez2023discovering,
  author    = {Perez, Ethan and Ringer, Sam and Luko{\v{s}}i{\=u}t{\.e}, Kamil{\.e} and Nguyen, Karina and Chen, Edwin and Heiner, Scott and Pettit, Craig and others},
  title     = {Discovering Language Model Behaviors with Model-Written Evaluations},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2023},
  pages     = {13387--13434},
  year      = {2023},
  doi       = {10.18653/v1/2023.findings-acl.847}
}

@article{hubinger2024sleeper,
  author    = {Hubinger, Evan and Denison, Carson and Mu, Jesse and Lambert, Mike and Tong, Meg and MacDiarmid, Monte and Lanham, Tamera and Ziegler, Daniel and others},
  title     = {Sleeper Agents: Training Deceptive {LLMs} that Persist Through Safety Training},
  journal   = {Transactions on Machine Learning Research},
  year      = {2024},
  url       = {https://openreview.net/forum?id=vERFqQj1qT}
}

@article{ist2026qualitygates,
  author    = {Anonymous},
  title     = {Which Quality Gates Actually Improve Agentic Software Maintenance?},
  journal   = {Information and Software Technology},
  volume    = {189},
  pages     = {107750},
  year      = {2026},
  doi       = {10.1016/j.infsof.2026.107750}
}

@inproceedings{ase2026symbolicfeedback,
  author    = {Anonymous},
  title     = {Evaluating Symbolic Feedback Granularity for {LLM}-Based Program Repair},
  booktitle = {Proceedings of the 41st IEEE/ACM International Conference on Automated Software Engineering (ASE)},
  year      = {2026}
}

@article{afzal2021sosrepair,
  author    = {Afzal, Afsoon and Le Goues, Claire and Hilton, Michael and Timperley, Christopher S.},
  title     = {{SOSRepair}: Expressive Semantic Search for Real-World Program Repair},
  journal   = {IEEE Transactions on Software Engineering},
  volume    = {47},
  number    = {10},
  pages     = {2162--2181},
  year      = {2021},
  doi       = {10.1109/TSE.2019.2944009}
}

@article{legoues2021survey,
  author    = {Le Goues, Claire and Pradel, Michael and Roychoudhury, Abhik},
  title     = {Automated Program Repair: A Survey},
  journal   = {IEEE Transactions on Software Engineering},
  volume    = {47},
  number    = {2},
  pages     = {194--225},
  year      = {2021},
  doi       = {10.1109/TSE.2019.2908505}
}

@inproceedings{kang2024faultlocalization,
  author    = {Kang, Sungmin and Yoon, Juyeon and Yoo, Shin},
  title     = {On the Fault Localization Capabilities of Large Language Models},
  booktitle = {Proceedings of the 46th IEEE/ACM International Conference on Software Engineering (ICSE)},
  pages     = {1--12},
  year      = {2024},
  doi       = {10.1145/3597503.3639148}
}

@inproceedings{jimenez2024swebench,
  author    = {Jimenez, Carlos E. and Yang, John and Wettig, Alexander and Yao, Shunyu and Pei, Kexin and Press, Ofir and Narasimhan, Karthik},
  title     = {{SWE}-bench: Can Language Models Resolve Real-World {GitHub} Issues?},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2024},
  url       = {https://openreview.net/forum?id=VTColl7jqy}
}

@inproceedings{shinn2023reflexion,
  author    = {Shinn, Noah and Cassano, Federico and Berman, Edward and Gopinath, Ashwin and Narasimhan, Karthik and Yao, Shunyu},
  title     = {Reflexion: Language Agents with Verbal Reinforcement Learning},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  volume    = {36},
  pages     = {8634--8652},
  year      = {2023}
}

@inproceedings{yang2023intercode,
  author    = {Yang, John and Shrivastava, Akshat and Kaur, Kudrat and Sahoo, Prafulla Kumar and Neubig, Graham and others},
  title     = {{InterCode}: Standardizing and Benchmarking Interactive Coding with Execution Feedback},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS) Datasets and Benchmarks Track},
  volume    = {36},
  year      = {2023}
}

@article{benjamini1995fdr,
  author    = {Benjamini, Yoav and Hochberg, Yosef},
  title     = {Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing},
  journal   = {Journal of the Royal Statistical Society: Series B (Methodological)},
  volume    = {57},
  number    = {1},
  pages     = {289--300},
  year      = {1995},
  doi       = {10.1111/j.2517-6161.1995.tb02031.x}
}

@article{welch1947generalization,
  author    = {Welch, Bernard L.},
  title     = {The Generalization of 'Student's' Problem when Several Different Population Variances are Involved},
  journal   = {Biometrika},
  volume    = {34},
  number    = {1/2},
  pages     = {28--35},
  year      = {1947},
  doi       = {10.2307/2332510}
}

@book{efron1994bootstrap,
  author    = {Efron, Bradley and Tibshirani, Robert J.},
  title     = {An Introduction to the Bootstrap},
  series    = {Monographs on Statistics and Applied Probability},
  volume    = {57},
  publisher = {Chapman \& Hall/CRC},
  year      = {1994}
}

@inproceedings{hendrycks2021math,
  author    = {Hendrycks, Dan and Burns, Collin and Kadavath, Saurav and Arora, Akul and Basart, Steven and Tang, Eric and Song, Dawn and Steinhardt, Jacob},
  title     = {Measuring Mathematical Problem Solving With the {MATH} Dataset},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS) Datasets and Benchmarks Track},
  volume    = {34},
  pages     = {3184--3196},
  year      = {2021}
}
```

---

## 7. How to Reference These in Your Manuscript Sections

### For Paper 1 (Introduction & Related Work)
> *"Recent AI safety literature demonstrates that language models can detect synthetic benchmark environments, prompting concerns regarding strategic underperformance or 'sandbagging' \cite{perez2023discovering, hubinger2024sleeper}. However, existing evaluations focus almost exclusively on single-turn, conversational queries. In multi-turn, tool-using environments interacting with production software repositories \cite{jimenez2024swebench}, we find that evaluation awareness triggers an **Anti-Surrender Hawthorne Effect** \cite{levitt2011hawthorne}: disclosing benchmark evaluation completely eliminates premature task abandonment (Fisher's exact $p = 0.0143$ \cite{benjamini1995fdr}) and drives a 3.18× compute escalation ($p < 0.0001$ \cite{welch1947generalization})."*

### For Paper 2 (Methodology & Causal Identification)
> *"While iterative reflection loops have been widely celebrated for automated repair \cite{shinn2023reflexion, yang2023intercode}, recent empirical studies emphasize that feedback utility cannot be isolated without a matched generic-retry control \cite{ist2026qualitygates, ase2026symbolicfeedback}. To isolate true verifier-attributable recovery from the mere provision of additional inference compute, our experimental design enforces identical token and step allowances across three randomized conditions: single-draft baseline, blind generic retry, and verifier-guided repair."*

### For Paper 3 (Qualitative Analysis & Fault Localization)
> *"Decades of research in automated program repair establish that repair success is strictly bounded by fault localization precision \cite{legoues2021survey, afzal2021sosrepair}. Our AST unified diff analysis reveals that 0% SWE-bench resolution in 7B–14B models \cite{jimenez2024swebench} does not indicate a failure of semantic code reasoning. Rather, models consistently synthesize ground-truth maintainer logic but fail repository localization by writing standalone helper modules \cite{kang2024faultlocalization}. When constrained by in-place scaffolding, valid repository patch localization increases to 100%."*
