# IEEE TSE Overleaf starter

This folder is an Overleaf-importable manuscript starter for the evaluation-disclosure and coding-agent persistence study.

## Import into Overleaf

1. Create a ZIP containing `main.tex`, `references.bib`, and this README (include `figures/` only if you add verified figures).
2. In Overleaf, choose **New Project → Upload Project** and select the ZIP.
3. Set `main.tex` as the main document if Overleaf does not select it automatically.
4. Select the IEEE journal class configuration and compile with pdfLaTeX.

The repository session could not access the browser to create the project directly, so this starter is ready to upload manually.

## Before submission

- Replace all red `TODO` markers with verified protocol and result details.
- Reconcile cohort membership, randomization, overlapping tasks/models, and confirmatory versus exploratory analyses from the machine containing the raw artifacts.
- Recompute all estimates from the trial-level source data; document the analysis code and dependencies.
- Remove the NeurIPS/ICLR conference template if the current official IEEE TSE template requires a different author block or formatting detail.
- Add only figures and tables derived from the verified raw data.
- The file `references.bib` marks the Needham et al. 2025 paper as a preprint, not peer reviewed. Keep or remove it accordingly; all other entries are peer-reviewed conference or journal publications.
- Do not claim that evaluation disclosure improves repair success unless the independently graded outcome supports that claim.

The local `PAPER.md`, results report, and reference guide are not copied verbatim because they contain numerical and bibliographic claims that still need reconciliation against the raw artifacts.
