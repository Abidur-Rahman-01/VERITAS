# VERITAS Replication Package

This replication package contains all trial-level records, configuration metadata, statistical audit scripts, and publication figures for the paper:

> **Do Evaluation Cues Alter Persistence and Tool-Use in Autonomous Coding Agents? A Factorial Controlled Experiment**

---

## 1. Directory Structure

```
replication/
├── data/
│   ├── study_cmd2_persistence_8.csv            # N = 8 CLI anti-surrender cohort
│   ├── study_llama_multitask_16.csv           # N = 16 Llama 3.1 multi-task factorial cohort
│   ├── study_pilot_confirmatory_32.csv         # N = 32 primary pre-registered causal pilot
│   ├── study_grand_pool_128.csv                # N = 128 grand benchmark inventory
│   └── controlled_localization_comparison.csv  # N = 16 controlled localization experiment
├── scripts/
│   └── reproduce_all.py                        # Master audit and figure generation script
└── figures/
    ├── fig1_compute_escalation.png             # Figure 1: Compute surge and tool calls
    ├── fig2_factorial_interaction.png          # Figure 2: D x A factorial interaction
    └── fig3_persistence_survival.png           # Figure 3: Survival / persistence curves
```

---

## 2. Requirements

- Python 3.9+
- Packages: `pandas`, `numpy`, `scipy`, `matplotlib`

```bash
pip install pandas numpy scipy matplotlib
```

---

## 3. Running Full Reproduction & Statistical Audit

To recalculate every table, effect size, p-value, multiple-testing correction, and figure reported in the paper from the raw data:

```bash
python replication/scripts/reproduce_all.py
```

### Verified Headline Statistics:
1. **Anti-Surrender Fisher's Exact Test:** $p = 0.0143$ ($0/4$ vs $4/4$ surrenders on `cmd2`). Retains significance under Benjamini-Hochberg FDR correction.
2. **Tool Call Escalation on CLI Tasks:** Welch's $t = 15.0570, p < 0.0001$.
3. **Median Compute Escalation:** $25,822 \to 42,620$ tokens ($1.65\times$ surge across pooled inventory; $3.18\times$ surge on CLI cohort).
4. **Controlled Localization Comparison:** Run `python scripts/run_localization_comparison.py` to evaluate the tripartite patch rubric (validity, localization, semantic correctness).

---

## 4. Cryptographic Integrity

All trial assignments and prompt manifests are sealed via deterministic SHA-256 hashes matching the pre-registered study protocol in `docs/ARCHITECTURE.md`.
